"""Full-context Answer Mode: the complete eligible corpus, no retrieval step.

This is a sibling of :mod:`rag_pipeline`, not a successor to it. It shares the
corpus-identity preflight, conversation resolution, interpretive settings, cost
ledger, and public-disclosure boundary, and deliberately builds no dependency on
the query planner, retrieval ranking, evidence gate, or stage/obligation
contracts - none of those concepts has a referent once there is nothing to rank
and nothing was filtered out before the model saw it.

Two properties are load-bearing:

* the model cites stable chunk IDs, which local code validates against the exact
  set supplied for that request and then remaps to compact ``[Source N]``
  labels, so a full-context result reaching any caller looks exactly like a
  retrieval result and carries only *cited* chunks; and
* seeing the whole corpus is not evidence of having used it, so an exhaustive
  local scan owns target presence/absence and audits model bindings against it.

Version 2 scope: the reader's lens, voice, and worldview shape the answer's
prose through the shared style block, but the structured interpretive
preface/coda expansion that :mod:`answer_coverage` validates for retrieval
answers is not yet reproduced here. See DEFECTS.md.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any

from answer_progress import (
    AnswerProgressStage,
    CheckedClaimCallback,
    CheckedClaimCandidate,
    IncrementalJSONArrayItems,
    ProgressCallback,
    ProviderStreamMilestoneCallback,
    emit_checked_claim,
    emit_progress,
    validate_progressive_lead,
)
from answer_coverage import AnswerUnitRole, CoverageOutcomeStatus
from costs import (
    CostLimitExceeded,
    TokenUsage,
    calculate_cost_nano_usd,
    enforce_projected_usage_budget,
    tracked_responses_parse,
    tracked_responses_stream,
)
from evidence_policy import CorpusIntegrity, scan_evidence_target
from filters import should_skip_document
from full_context_coverage import (
    FULL_CONTEXT_COVERAGE_PROMPT_VERSION,
    FULL_CONTEXT_COVERAGE_SCHEMA,
    FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA,
    FullContextCoverageAnswer,
    FullContextCoverageResult,
    FullContextValidationErrorCode,
    MAX_TOTAL_CLAIM_TEXT_CHARACTERS,
    TrustedTargetAudit,
    process_full_context_coverage,
    validate_streamable_full_context_claim,
)
from model_config import FULL_CONTEXT_GENERATOR_SETTINGS
from archivist_modes import (
    ArchivistMode,
    archivist_mode_metadata,
    build_archivist_mode_prompt_block,
)
from perspectives import (
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
)
from query_planning import (
    EvidenceTarget,
    ResolvedTurn,
    extract_trusted_targets,
)
from rag_pipeline import (
    AnswerModeResult,
    AnswerStrategy,
    CORPUS_INTEGRITY_FAILED_MESSAGE,
    preflight_answer_corpus,
    without_automatic_retries,
)

__all__ = [
    "FULL_CONTEXT_POLICY",
    "FULL_CONTEXT_POLICY_VERSION",
    "FullContextEvidenceDecision",
    "FullContextPolicy",
    "eligible_full_context_chunks",
    "estimate_full_context_input_tokens",
    "estimate_full_context_request_cost_nano_usd",
    "run_full_context_answer",
    "serialize_full_context_corpus",
]


FULL_CONTEXT_POLICY_VERSION = "full-context-v2"
MAX_FULL_CONTEXT_OUTPUT_TOKENS = 12_000

# Documented maximum input for the GPT-5.6 family. REQUIRES VERIFICATION against
# current OpenAI documentation before it is relied on for a paid run; it is used
# only to fail closed early, never to justify sending a larger request.
DOCUMENTED_MAX_INPUT_TOKENS = 922_000
# Leave room for output, reasoning, and the imprecision of a character-based
# estimate. A cheap conservative check beats an exact one that needs a tokenizer
# this project does not depend on.
CONTEXT_BUDGET_UTILIZATION = 0.85
# Rough English-prose estimator. Deliberately not tokenizer-exact: an
# over-estimate fails a borderline request closed, which is the safe direction.
CHARACTERS_PER_TOKEN = 4


class FullContextEvidenceDecision:
    """Evidence-decision vocabulary, prefixed so it cannot be read as RAG's."""

    ANSWERED = "full_context_answered"
    INSUFFICIENT_EVIDENCE = "full_context_insufficient_evidence"
    INDETERMINATE = "full_context_indeterminate"


@dataclass(frozen=True, slots=True)
class FullContextPolicy:
    version: str = FULL_CONTEXT_POLICY_VERSION


FULL_CONTEXT_POLICY = FullContextPolicy()

FULL_CONTEXT_INSTRUCTIONS = """\
You are Archivist, answering strictly from one supplied manuscript.

You are given the complete searchable manuscript, in its own narrative order, as
a sequence of chunks. Each chunk begins with a "Chunk ID:" line. Nothing else is
available to you: do not use outside knowledge, and do not infer facts the
supplied text does not state.

Evidence and citation rules:
- Support every factual claim with one or more exact Chunk ID values copied
  verbatim from the supplied manuscript into that claim's cited_chunk_ids.
- Never invent, abbreviate, reformat, or guess a Chunk ID. A Chunk ID that does
  not appear in the supplied manuscript invalidates the entire answer.
- Every chunk listed for a claim must independently support that whole claim. If
  different parts of a statement need different chunks, write separate claims.
- Never write a citation, bracket, or source label inside claim text. Citations
  are attached automatically from cited_chunk_ids.

Claim rules:
- Write claims immediately after schema, before premise and absence diagnostics.
- Except for a required premise correction, make the first factual claim a direct
  bottom-line answer to the current question: one concise sentence of no more than
  45 words that names the question's subject. Use later claims to expand the evidence,
  chronology, and qualifications without merely repeating the lead. When a premise
  correction is required, keep it first and put the concise direct answer immediately
  after it.
- Each claim is exactly one complete sentence making one independently checkable
  factual assertion, ending in its only terminal punctuation.
- Spell out or rephrase abbreviations, titles, initials, and decimals that would
  otherwise put a period inside the sentence.
- Group claims into paragraphs with paragraph_group, in reading order.

Answering the whole question:
- Because you can see the entire manuscript, search it thoroughly before
  concluding that something is missing. Absence is a strong claim.
- The application supplies trusted Target IDs copied from the user's question.
  Use an absence_finding only by copying one of those exact IDs. Do not invent,
  paraphrase, or rename a target, and do not write absence prose; the application
  renders any certified evidence boundary itself.
- Do not substitute material about a merely similar subject and present it as an
  answer. Every directly present trusted target must be supported by at least one
  cited chunk that directly contains that target.
- If the manuscript contains none of the trusted targets, return no claims. Add
  absence_findings only for the supplied targets whose absence is checkable. Do
  not add a related example or analogue unless a future application contract
  explicitly authorizes it.
- If the question asserts something the manuscript contradicts, set
  premise_finding.status to contradicted, correct it in the first claim, and
  reference that claim in premise_finding.correction_claim_id.
- Set self_reported_content_outcome honestly: valid_complete only if the
  manuscript let you answer the whole question, valid_partial if you answered
  part of it, insufficient_evidence if you could not answer it at all. This is a
  diagnostic self-report; application validation decides the final outcome.
- If nothing in the manuscript supports an answer, return no claims rather than
  writing an unsupported one.
"""


def eligible_full_context_chunks(
    chunks: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """Return the same eligible corpus the preflight certifies, in corpus order.

    No sort is applied: the loaded chunk order is already canonical document and
    paragraph order, and the preflight has verified it matches the manifest
    chunk-for-chunk.
    """

    return [chunk for chunk in chunks if not should_skip_document(str(chunk.get("document") or ""))]


def serialize_full_context_corpus(
    eligible_chunks: Sequence[Mapping[str, object]],
) -> str:
    """Serialize the whole eligible corpus keyed by stable chunk ID.

    Keyed by identifier rather than by position, because full context has no
    ranking to express and the identifier is what the model must cite back.
    """

    blocks: list[str] = []
    for chunk in eligible_chunks:
        blocks.append(
            f"Chunk ID: {chunk.get('chunk_id', '')}\n"
            f"Document: {chunk.get('document', '')}\n"
            f"Chapter: {chunk.get('chapter_title', '')}\n"
            f"Paragraphs: {chunk.get('paragraph_start', '?')}-{chunk.get('paragraph_end', '?')}\n"
            f"Text:\n{chunk.get('text', '')}"
        )
    return "\n\n".join(blocks)


def estimate_full_context_input_tokens(*parts: str) -> int:
    """Estimate request size from characters, biased high rather than exact."""

    total_characters = sum(len(part) for part in parts)
    return -(-total_characters // CHARACTERS_PER_TOKEN)


def estimate_full_context_request_cost_nano_usd(estimated_input_tokens: int) -> int:
    """Price the most expensive plausible uncached form of one request.

    A first call may be billed either as ordinary uncached input or as a cache
    write. The live v1 measurement observed the latter, so the pre-request guard
    prices both shapes and uses the larger result. Maximum output is included;
    a warm cached read can only be cheaper than this estimate.
    """

    if estimated_input_tokens < 0:
        raise ValueError("estimated_input_tokens must be non-negative")
    total_tokens = estimated_input_tokens + MAX_FULL_CONTEXT_OUTPUT_TOKENS
    possible_costs = (
        calculate_cost_nano_usd(
            FULL_CONTEXT_GENERATOR_SETTINGS.model,
            TokenUsage(
                input_tokens=estimated_input_tokens,
                output_tokens=MAX_FULL_CONTEXT_OUTPUT_TOKENS,
                total_tokens=total_tokens,
            ),
        ),
        calculate_cost_nano_usd(
            FULL_CONTEXT_GENERATOR_SETTINGS.model,
            TokenUsage(
                input_tokens=estimated_input_tokens,
                cache_write_tokens=estimated_input_tokens,
                output_tokens=MAX_FULL_CONTEXT_OUTPUT_TOKENS,
                total_tokens=total_tokens,
            ),
        ),
    )
    priced = tuple(cost for cost in possible_costs if cost is not None)
    if not priced:
        raise RuntimeError(
            "Full-context generation model has no configured local pricing; "
            "the request was not sent."
        )
    return max(priced)


def context_token_ceiling() -> int:
    return int(DOCUMENTED_MAX_INPUT_TOKENS * CONTEXT_BUDGET_UTILIZATION)


def build_full_context_input(
    *,
    corpus_block: str,
    resolved_turn: ResolvedTurn,
    trusted_targets: Sequence[EvidenceTarget] | None = None,
    historiographical_lens: HistoriographicalLens | str = (HistoriographicalLens.EVIDENCE_FIRST),
    voice: AnswerVoice | str = AnswerVoice.SCHOLARLY,
    worldview: Worldview | str = Worldview.NONE,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
) -> str:
    """Assemble the request with the stable corpus prefix ahead of the variable tail.

    Ordering is a cost decision as much as a prompt decision: the corpus prefix
    is identical for every reader and every question, so keeping it first and
    keeping interpretive settings *after* it leaves one cacheable prefix rather
    than one per lens/voice/worldview combination.
    """

    sections = [
        "Manuscript (complete searchable corpus, in narrative order):",
        corpus_block,
    ]
    style = build_archivist_mode_prompt_block(
        historiographical_lens,
        voice,
        worldview,
        archivist_mode=archivist_mode,
    )
    if style:
        sections.append(
            "Interpretive presentation (never alter factual coverage or citations):\n" + style
        )
    if resolved_turn.scope:
        sections.append(f"Requested scope: {resolved_turn.scope}")
    targets = (
        tuple(trusted_targets)
        if trusted_targets is not None
        else extract_trusted_targets(resolved_turn)
    )
    if targets:
        sections.append(
            "Application-issued trusted targets (copy Target ID exactly for any "
            "absence_finding):\n"
            + "\n".join(
                f"Target ID: {target.target_id}\n"
                f"User surface: {target.query_surface_span}\n"
                f"Absence checkable: {str(target.absence_checkable).lower()}"
                for target in targets
            )
        )
    sections.append(f"Question: {resolved_turn.standalone_question}")
    return "\n\n".join(sections)


def _audit_trusted_targets(
    targets: Sequence[EvidenceTarget],
    eligible_chunks: Sequence[Mapping[str, object]],
    integrity: CorpusIntegrity,
) -> tuple[TrustedTargetAudit, ...]:
    """Produce application-owned strong+weak direct-evidence facts."""

    audits: list[TrustedTargetAudit] = []
    for target in targets:
        scan = scan_evidence_target(
            target.target_id,
            target.query_surface_span,
            eligible_chunks,
            absence_checkable=target.absence_checkable,
            corpus_integrity=integrity,
            role=target.role,
        )
        audits.append(
            TrustedTargetAudit(
                target_id=target.target_id,
                query_surface_span=target.query_surface_span,
                direct_chunk_ids=scan.direct_chunk_ids,
                absence_checkable=target.absence_checkable,
                certified_direct_absence=scan.certified_direct_absence,
            )
        )
    return tuple(audits)


def _generation_trace(
    result: FullContextCoverageResult | None,
    *,
    status: str,
    structured_generation_called: bool,
    style_prompt_sha256: str | None = None,
    supplied_chunk_count: int = 0,
    estimated_input_tokens: int | None = None,
    projected_request_cost_nano_usd: int | None = None,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema": FULL_CONTEXT_RUN_DIAGNOSTICS_SCHEMA,
        "prompt_version": FULL_CONTEXT_COVERAGE_PROMPT_VERSION,
        "response_schema": FULL_CONTEXT_COVERAGE_SCHEMA,
        "instructions_sha256": hashlib.sha256(
            FULL_CONTEXT_INSTRUCTIONS.encode("utf-8")
        ).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(
                FullContextCoverageAnswer.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "generator_model": FULL_CONTEXT_GENERATOR_SETTINGS.model,
        "generator_reasoning_effort": FULL_CONTEXT_GENERATOR_SETTINGS.reasoning_effort,
        "generator_verbosity": FULL_CONTEXT_GENERATOR_SETTINGS.verbosity,
        "style_prompt_sha256": style_prompt_sha256,
        "supplied_chunk_count": supplied_chunk_count,
        "estimated_input_tokens": estimated_input_tokens,
        "projected_request_cost_nano_usd": projected_request_cost_nano_usd,
        "structured_generation_called": structured_generation_called,
        "status": status,
    }
    if result is None:
        return contract
    return {**contract, **result.diagnostics}


def run_full_context_answer(
    *,
    resolved_turn: ResolvedTurn,
    chunks: Sequence[Mapping[str, object]],
    client: object,
    collection_handle: object | None = None,
    corpus_trace: Mapping[str, Any] | None = None,
    corpus_manifest: Mapping[str, object] | None = None,
    corpus_manifest_sha256: str | None = None,
    corpus_integrity: CorpusIntegrity | None = None,
    require_store_identity: bool = False,
    historiographical_lens: HistoriographicalLens | str = (HistoriographicalLens.EVIDENCE_FIRST),
    voice: AnswerVoice | str = AnswerVoice.SCHOLARLY,
    worldview: Worldview | str = Worldview.NONE,
    archivist_mode: ArchivistMode | str = ArchivistMode.ESSENTIAL,
    policy: FullContextPolicy = FULL_CONTEXT_POLICY,
    progress_callback: ProgressCallback | None = None,
    checked_claim_callback: CheckedClaimCallback | None = None,
    stream_milestone_callback: ProviderStreamMilestoneCallback | None = None,
) -> AnswerModeResult:
    """Execute one bounded full-context Answer Mode turn.

    ``collection_handle`` is accepted so this is drop-in compatible with
    :func:`rag_pipeline.run_evidence_planned_answer` for callers and tooling, and
    is used only for the shared corpus preflight; full context never queries the
    vector index.
    """

    pipeline_started_ns = perf_counter_ns()
    stage_timings_ms: dict[str, float] = {}

    def elapsed_ms(start_ns: int) -> float:
        return round(max(0, perf_counter_ns() - start_ns) / 1_000_000, 3)

    def result_diagnostics(generation: Mapping[str, Any]) -> dict[str, Any]:
        stage_timings_ms["pipeline_total"] = elapsed_ms(pipeline_started_ns)
        return {
            "full_context_policy_version": policy.version,
            "archivist_mode": archivist_mode_metadata(archivist_mode),
            "corpus": dict(corpus_trace or {}),
            "generation": dict(generation),
            "stage_timings_ms": dict(stage_timings_ms),
        }

    def failed_result(
        *,
        answer: str,
        status: str,
        evidence_decision: str,
        generation: Mapping[str, Any],
    ) -> AnswerModeResult:
        return AnswerModeResult(
            answer=answer,
            final_chunks=[],
            status=status,
            plan=None,
            evidence_decision=evidence_decision,
            diagnostics=result_diagnostics(generation),
            answer_strategy=AnswerStrategy.FULL_CONTEXT.value,
            answer_strategy_version=policy.version,
            resolved_question_text=resolved_turn.standalone_question,
        )

    emit_progress(progress_callback, AnswerProgressStage.CHECKING_CORPUS)
    integrity_started_ns = perf_counter_ns()
    eligible_chunks = eligible_full_context_chunks(chunks)
    integrity = corpus_integrity
    if integrity is None:
        if collection_handle is None:
            raise ValueError("full context requires a collection handle or a preflight result")
        integrity = preflight_answer_corpus(
            collection_handle=collection_handle,
            chunks=eligible_chunks,
            corpus_manifest=corpus_manifest,
            corpus_manifest_sha256=corpus_manifest_sha256,
            require_store_identity=require_store_identity,
        )
    stage_timings_ms["corpus_integrity"] = elapsed_ms(integrity_started_ns)
    if not integrity.passed:
        return failed_result(
            answer=CORPUS_INTEGRITY_FAILED_MESSAGE,
            status="corpus_integrity_failed",
            evidence_decision=FullContextEvidenceDecision.INDETERMINATE,
            generation=_generation_trace(
                None,
                status="corpus_integrity_failed",
                structured_generation_called=False,
                supplied_chunk_count=len(eligible_chunks),
            ),
        )

    emit_progress(progress_callback, AnswerProgressStage.PREPARING_CONTEXT)
    serialization_started_ns = perf_counter_ns()
    trusted_targets = extract_trusted_targets(resolved_turn)
    trusted_target_audits = _audit_trusted_targets(
        trusted_targets,
        eligible_chunks,
        integrity,
    )
    corpus_block = serialize_full_context_corpus(eligible_chunks)
    style_block = build_archivist_mode_prompt_block(
        historiographical_lens,
        voice,
        worldview,
        archivist_mode=archivist_mode,
    )
    style_prompt_sha256 = (
        hashlib.sha256(style_block.encode("utf-8")).hexdigest() if style_block else None
    )
    generation_input = build_full_context_input(
        corpus_block=corpus_block,
        resolved_turn=resolved_turn,
        trusted_targets=trusted_targets,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
        archivist_mode=archivist_mode,
    )
    estimated_input_tokens = estimate_full_context_input_tokens(
        FULL_CONTEXT_INSTRUCTIONS,
        generation_input,
    )
    stage_timings_ms["corpus_serialization"] = elapsed_ms(serialization_started_ns)

    if estimated_input_tokens > context_token_ceiling():
        emit_progress(progress_callback, AnswerProgressStage.VALIDATING_ANSWER)
        # Fail closed rather than truncate. A silently partial corpus would make
        # every absence judgment in the answer unsound while still looking whole.
        coverage = FullContextCoverageResult(
            status=CoverageOutcomeStatus.GENERATION_CONTRACT_FAILED,
            answer=(
                "The full manuscript is too large to send to the answer model in "
                "one request, so I cannot produce a full-book answer."
            ),
            final_chunks=[],
            content_outcome=None,
            error_code=FullContextValidationErrorCode.CONTEXT_BUDGET_EXCEEDED,
            diagnostics={
                "validation_result": "invalid",
                "error_code": FullContextValidationErrorCode.CONTEXT_BUDGET_EXCEEDED.value,
                "content_outcome": None,
            },
        )
        return failed_result(
            answer=coverage.answer,
            status=coverage.status.value,
            evidence_decision=FullContextEvidenceDecision.INDETERMINATE,
            generation=_generation_trace(
                coverage,
                status=coverage.status.value,
                structured_generation_called=False,
                style_prompt_sha256=style_prompt_sha256,
                supplied_chunk_count=len(eligible_chunks),
                estimated_input_tokens=estimated_input_tokens,
            ),
        )

    projected_request_cost_nano_usd = estimate_full_context_request_cost_nano_usd(
        estimated_input_tokens
    )
    enforce_projected_usage_budget(projected_request_cost_nano_usd)
    request_client = without_automatic_retries(client)
    emit_progress(progress_callback, AnswerProgressStage.GENERATING_ANSWER)
    generation_started_ns = perf_counter_ns()
    try:
        generation_request = {
            "instructions": FULL_CONTEXT_INSTRUCTIONS,
            "input": generation_input,
            "text_format": FullContextCoverageAnswer,
            "max_output_tokens": MAX_FULL_CONTEXT_OUTPUT_TOKENS,
            **FULL_CONTEXT_GENERATOR_SETTINGS.responses_create_kwargs(),
        }
        if checked_claim_callback is None:
            response = tracked_responses_parse(
                request_client,
                operation="answer_generation",
                **generation_request,
            )
        else:
            extractor = IncrementalJSONArrayItems("claims")
            seen_claim_ids: list[str] = []
            streamed_factual_claim_count = 0
            prior_cited_chunk_ids: tuple[str, ...] = ()
            previous_paragraph: int | None = None
            streamed_text_characters = 0
            extraction_failed = False

            def observe_structured_delta(delta: str) -> None:
                nonlocal extraction_failed
                nonlocal previous_paragraph
                nonlocal prior_cited_chunk_ids
                nonlocal streamed_factual_claim_count
                nonlocal streamed_text_characters
                if extraction_failed:
                    return
                try:
                    for value in extractor.feed(delta):
                        claim, rendered, source_chunks, ordered_ids = (
                            validate_streamable_full_context_claim(
                                value,
                                eligible_chunks=eligible_chunks,
                                claim_ordinal=len(seen_claim_ids) + 1,
                                seen_claim_ids=seen_claim_ids,
                                previous_paragraph=previous_paragraph,
                                prior_cited_chunk_ids=prior_cited_chunk_ids,
                            )
                        )
                        streamed_text_characters += len(claim.text)
                        if streamed_text_characters > MAX_TOTAL_CLAIM_TEXT_CHARACTERS:
                            raise ValueError("full-context streamed text limit exceeded")
                        # Premise contradiction is a whole-payload finding. A
                        # correction can establish ordering state here, but it
                        # cannot be described to the reader as locally checked
                        # until that finding is validated at the terminal gate.
                        if claim.role is not AnswerUnitRole.PREMISE_CORRECTION:
                            if streamed_factual_claim_count == 0:
                                validate_progressive_lead(
                                    claim.text,
                                    question_anchors=tuple(
                                        target.query_surface_span
                                        for target in trusted_targets
                                    ),
                                )
                            streamed_factual_claim_count += 1
                        seen_claim_ids.append(claim.claim_id)
                        previous_paragraph = claim.paragraph_group
                        prior_cited_chunk_ids = ordered_ids
                        if claim.role is not AnswerUnitRole.PREMISE_CORRECTION:
                            emit_checked_claim(
                                checked_claim_callback,
                                CheckedClaimCandidate(
                                    paragraph=claim.paragraph_group,
                                    text=rendered,
                                    source_chunks=source_chunks,
                                    audit_chunks=tuple(eligible_chunks),
                                ),
                            )
                except (TypeError, ValueError):
                    extraction_failed = True

            response = tracked_responses_stream(
                request_client,
                operation="answer_generation",
                on_text_delta=observe_structured_delta,
                stream_milestone_callback=stream_milestone_callback,
                **generation_request,
            )
        parsed = getattr(response, "output_parsed", None)
        refused = _response_refused(response)
    except CostLimitExceeded:
        raise
    except Exception:
        parsed = None
        refused = True
    stage_timings_ms["answer_generation"] = elapsed_ms(generation_started_ns)

    emit_progress(progress_callback, AnswerProgressStage.VALIDATING_ANSWER)
    validation_started_ns = perf_counter_ns()
    coverage = process_full_context_coverage(
        parsed if isinstance(parsed, FullContextCoverageAnswer) else None,
        eligible_chunks=eligible_chunks,
        trusted_target_audits=trusted_target_audits,
        refused=refused,
    )
    stage_timings_ms["answer_validation"] = elapsed_ms(validation_started_ns)

    if coverage.status is CoverageOutcomeStatus.ANSWERED:
        evidence_decision = FullContextEvidenceDecision.ANSWERED
    elif coverage.status is CoverageOutcomeStatus.INSUFFICIENT_EVIDENCE:
        evidence_decision = FullContextEvidenceDecision.INSUFFICIENT_EVIDENCE
    else:
        evidence_decision = FullContextEvidenceDecision.INDETERMINATE

    generation = _generation_trace(
        coverage,
        status=coverage.status.value,
        structured_generation_called=True,
        style_prompt_sha256=style_prompt_sha256,
        supplied_chunk_count=len(eligible_chunks),
        estimated_input_tokens=estimated_input_tokens,
        projected_request_cost_nano_usd=projected_request_cost_nano_usd,
    )
    return AnswerModeResult(
        answer=coverage.answer,
        final_chunks=coverage.final_chunks,
        status=coverage.status.value,
        plan=None,
        evidence_decision=evidence_decision,
        diagnostics=result_diagnostics(generation),
        answer_strategy=AnswerStrategy.FULL_CONTEXT.value,
        answer_strategy_version=policy.version,
        resolved_question_text=resolved_turn.standalone_question,
    )


def _response_refused(response: object) -> bool:
    for output in getattr(response, "output", ()) or ():
        for content in getattr(output, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return True
    return False
