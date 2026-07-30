"""Versioned evidence-planned Answer Mode shared by CLI and web.

The model may plan searches and phrase an answer. Local code owns routing, trusted
anchors, corpus scans, source admission, schema validation, citation validation,
rendering, tracing, and retry limits.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from time import perf_counter_ns
from typing import Any

from answer_coverage import (
    CoverageContractError,
    CoverageValidationErrorCode,
    DiagnosticValidationResult,
    EVIDENCE_COVERAGE_NORMALIZER_VERSION,
    EvidenceDimension,
    EvidenceCoverageAnswer,
    EvidenceCoverageResult,
    EvidenceObligationFocus,
    EvidenceObligationKind,
    EvidenceObligationScope,
    InterpretiveEvidenceCoverageAnswer,
    InterpretiveMove,
    MAX_ANSWER_UNITS,
    PremiseSourceScope,
    process_evidence_coverage,
    process_interpretive_evidence_coverage,
    validate_evidence_coverage_context,
)
from costs import (
    CostLimitExceeded,
    safe_planner_exception_class,
    safe_planner_exception_code,
    tracked_responses_parse,
)
from evidence_policy import (
    EVIDENCE_DIAGNOSTICS_SCHEMA,
    EVIDENCE_POLICY_VERSION,
    MAX_QUALIFIED_NEAR_MATCH_SOURCES,
    CorpusIntegrity,
    EvidenceDecision,
    EvidenceGateResult,
    EvidenceLane,
    EvidenceLaneAssignment,
    EvidenceTargetScan,
    EvidenceTargetRole as PolicyTargetRole,
    assess_corpus_integrity,
    build_immediate_neighbor_map,
    classify_evidence_lanes,
    decide_evidence,
    decide_multi_subject_evidence,
    evidence_diagnostics,
    relationship_evidence_chunk_ids,
    scan_broader_related,
    scan_evidence_target,
    split_compound_named_anchor,
    tokenize_anchor,
)
from filters import should_skip_document
from model_config import GENERATOR_SETTINGS, QUERY_PLANNER_SETTINGS
from perspectives import (
    AnswerVoice,
    HistoriographicalLens,
    Worldview,
    build_interpretive_prompt_block,
    normalize_historiographical_lens,
    normalize_worldview,
)
from query_planning import (
    BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS,
    LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS,
    MIN_BROAD_STAGE_REQUIREMENTS,
    QUERY_PLANNER_INSTRUCTIONS,
    DocumentCatalogEntry,
    EvidenceTargetRole,
    FacetRole,
    PlannerQuestionPlan,
    QuestionPlan,
    ResolvedTurn,
    RouteTrait,
    build_question_plan,
    normalize_search_query,
    requires_broad_narrative_span,
    requires_planning,
    route_question,
    safe_planner_validation_code,
)
from retrieval import (
    MAX_FINAL_SOURCES,
    PlannedContext,
    build_context,
    emit_retrieval_trace,
    retrieve_plan_from_collection,
)
from retrieval_trace_contract import document_identifier_sha256
from document_roles import (
    DOCUMENT_ROLE_PROFILE_VERSION,
    derive_document_role_terms,
)


RAG_POLICY_VERSION = "evidence-planned-v23"
LEGACY_RAG_POLICY_VERSION = "legacy-answer-v1"
NOT_APPLICABLE_COHORT_VALUE = "not-applicable"
ANSWER_RUN_DIAGNOSTICS_SCHEMA = "archivist.answer_run_diagnostics/2"
PLANNER_CALL_DIAGNOSTICS_SCHEMA = "archivist.planner_call_diagnostics/2"
QUERY_PLANNER_PROMPT_VERSION = "query-planner-v11"
EVIDENCE_COVERAGE_PROMPT_VERSION = "evidence-coverage-v9"
MAX_PLANNER_OUTPUT_TOKENS = 4_000
MAX_COVERAGE_OUTPUT_TOKENS = 12_000
MAX_BROAD_EVIDENCE_OBLIGATIONS = 32
MAX_BROAD_INSPECTION_SCOPES = 32
EMBEDDING_MODEL = "text-embedding-3-small"
ANSWER_STAGE_TIMING_KEYS = frozenset(
    {
        "preflight",
        "conversation_resolution",
        "corpus_integrity",
        "query_planning",
        "retrieval",
        "evidence_gate",
        "context_preparation",
        "answer_generation",
        "answer_validation",
        "pipeline_total",
        "total",
    }
)
CORPUS_INTEGRITY_FAILED_MESSAGE = (
    "The manuscript index could not be verified against its promoted corpus "
    "snapshot. Rebuild or restore the index before asking another question."
)
STRUCTURAL_STAGE_SHORTFALL_MESSAGE = (
    "I could not assemble manuscript evidence from every required historical "
    "stage, so I cannot produce a complete source-grounded answer."
)

INTERPRETIVE_STRUCTURED_OUTPUT_RULES = """\
Structured interpretive frame:
- Keep all requested factual coverage in answer_units under the ordinary evidence contract.
- Return interpretive_moves exactly as ordered in the request contract.
- Write interpretive_preface as one uncited paragraph of two or three sentences before the factual
  answer. It should make a clear but proportionate value judgment through an integrated use of
  every requested move and directly address the current question.
- Write interpretive_coda as one uncited sentence after the factual answer. It should close with a
  clear judgment about the current question in the same frame rather than balancing the
  perspective back to neutrality.
- Name every required_question_anchor in both interpretive_preface and interpretive_coda. Do not
  substitute generic phrases such as "this record," "this account," or "the result" for the
  question's actual subject.
- Use impersonal historical prose throughout the preface and coda. Never use first-person
  pronouns, first-person contractions, or narrator self-reference.
- The preface and coda are editorial framing, not manuscript evidence. Do not place citations in
  them and do not introduce names, dates, events, quantities, quotations, or other historical
  assertions absent from the factual answer.
- Ground every interpretive judgment in a concrete fact that also appears in the factual answer.
  Do not invent an unnamed human cost, moral burden, lost possibility, triumph, or failure merely
  to make a selected setting conspicuous.
- The framing must remain unmistakably recognizable as the selected reading when its setting label
  is hidden. It never satisfies a factual requirement or evidence obligation.
- Treat the preface, factual answer, and coda as consecutive paragraphs in one cohesive response.
  Use natural transitions and do not write headings, labels, or meta-commentary for any part.
"""

_INTERPRETIVE_MOVE_BY_LENS = {
    HistoriographicalLens.TRIUMPHALIST: (
        InterpretiveMove.ACHIEVEMENT_AND_DURABLE_CAPACITY
    ),
    HistoriographicalLens.TRAGIC: (
        InterpretiveMove.TRAGIC_TENSION_AND_CONTINGENCY
    ),
}

_INTERPRETIVE_MOVE_BY_WORLDVIEW = {
    Worldview.PIOUS: InterpretiveMove.FAITH_DUTY_AND_MORAL_CONSEQUENCE,
    Worldview.SECULAR_HUMANIST: (
        InterpretiveMove.HUMAN_DIGNITY_AND_LIVED_CONSEQUENCE
    ),
    Worldview.ENLIGHTENMENT_RATIONALIST: (
        InterpretiveMove.INQUIRY_REFORM_AND_SCRUTINY
    ),
}


def _required_interpretive_moves(
    historiographical_lens: HistoriographicalLens | str,
    worldview: Worldview | str,
) -> tuple[InterpretiveMove, ...]:
    selected_lens = normalize_historiographical_lens(historiographical_lens)
    selected_worldview = normalize_worldview(worldview)
    moves: list[InterpretiveMove] = []
    if selected_lens is not HistoriographicalLens.EVIDENCE_FIRST:
        moves.append(_INTERPRETIVE_MOVE_BY_LENS[selected_lens])
    if selected_worldview is not Worldview.NONE:
        moves.append(_INTERPRETIVE_MOVE_BY_WORLDVIEW[selected_worldview])
    return tuple(moves)


def _interpretive_question_anchors(
    resolved_turn: ResolvedTurn,
    plan: QuestionPlan,
) -> tuple[str, ...]:
    """Return application-owned subject names that framing must address."""

    subject_targets = tuple(
        target.query_surface_span
        for target in plan.targets
        if target.role is EvidenceTargetRole.SUBJECT
    )
    target_candidates = subject_targets or tuple(
        target.query_surface_span for target in plan.targets
    )
    candidates = target_candidates or resolved_turn.entities
    anchors: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_search_query(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        anchors.append(candidate.strip())
    return tuple(anchors)


_RELATED_PROBE_PATTERN = re.compile(
    r"^\s*broader\s*:\s*(?P<broader>[^;]{1,120})\s*;\s*"
    r"related\s*:\s*(?P<related>.+?)\s*$",
    flags=re.IGNORECASE,
)
_TRUSTED_RELATED_TAIL_PATTERN = re.compile(
    r"^\s*,?\s*and\s+(?P<tail>.+?)\s*[?.!]*\s*$",
    flags=re.IGNORECASE,
)
_TRUSTED_RELATED_PREFIX_PATTERNS = (
    re.compile(
        r"^(?:its|their)\s+"
        r"(?:effect|effects|impact|impacts|influence|relationship|role)\s+"
        r"(?:on|upon|in|to|with)\s+",
        flags=re.IGNORECASE,
    ),
    re.compile(r"^(?:the|a|an)\s+", flags=re.IGNORECASE),
)
_MAX_TRUSTED_RELATED_TOKENS = 6

QUERY_PLANNER_ADDITIONAL_INSTRUCTIONS = """\
For a safe broader-class search on an absence-sensitive question, use role
broader_related only when the result would not substitute a peer person or institution.
Format that facet's search_query exactly as:
broader: <one broader class term>; related: <one or more comma-separated relation terms>
The broader facet is discovery only and never proves that the named subject is present.
"""

EVIDENCE_COVERAGE_INSTRUCTIONS = """\
Answer a question about one manuscript using only the numbered sources in the input.
Return the required structured evidence-coverage object; do not return prose outside it.

For every ordered requirement:
- inspect all supplied sources for directly relevant material;
- include each supported requested point exactly once in concise answer units;
- preserve causal links, mechanisms, quantities, chronology, counterarguments, and
  qualifications when the sources support them;
- ignore tangential sources and never use outside knowledge;
- mark unsupported material unsupported rather than inventing connective tissue.

Each answer_unit.text must contain exactly one complete sentence asserting exactly one
independently checkable factual claim, followed by exactly one terminal citation group
and its only ending punctuation. Do not use periods inside abbreviations, titles, initials,
or decimals; spell them out or rephrase the sentence. If prose contains two facts—even
when joined by punctuation or a conjunction—or the facts require different source sets,
split them into separate answer units; they may share a paragraph number. Use
[Source N, Source M] only when every listed source independently supports that same single
claim. Its declared source_numbers must exactly match the one citation group.

Treat every listed premise as a hypothesis. If sources contradict one, the first answer
unit must use role premise_correction, correct it with citations before addressing the
useful underlying question, have no requirement IDs, and be named in correction_unit_id.
Premise adjudication and requested-point coverage are separate: a correction unit never
satisfies an answer requirement. When framing candidate sources are supplied, the correction
must cite at least one and state the manuscript's positive replacement chronology, origin,
identity, or causal frame; a bare denial or merely earlier/later counterexample is insufficient.
Then cover every supported requirement in separate non-correction units. If sources do not
resolve a premise, mark it unresolved with a null correction_unit_id. Do not use not_applicable
for a listed premise. Never validate a premise merely because the question assumes it.

Respect the evidence-boundary decision. A qualified near match must begin by saying the
searchable manuscript does not directly establish the named subject or relationship, and
may then summarize only the explicitly supplied broader material. Do not turn an analogue
into a direct answer.

Neutral output should be compact but must not omit supported requirements. Use one short
paragraph for focused questions or compact ordered paragraphs/bullets for broad questions.

For a broad question, the request separates inspection_passages from
synthesis_obligations. Inspect every inspection passage in order, but do not create an answer
unit merely to prove that a passage was inspected. Ignore tangential inspected material.
The first blank-line-separated text block in a source is its paragraph_start, with later
blocks following in order; a range covering several paragraphs is one fallback scope.

The smaller synthesis_obligations ledger identifies source-bounded material that the answer
must explicitly attempt to cover. Return every obligation_id and every dimension_id exactly
once and in the supplied order. This is a completeness pass, not permission to add claims.

An obligation with kind stage describes one protected historical stage. An obligation with
kind adjacent_stage_link describes the required connection from the immediately preceding
stage to the current one. Its predecessor_source_number identifies the prior stage only for
orientation; the link claim remains bound to the obligation's source_number, which is a
dedicated transition passage that must itself state the connection. An obligation with kind
requirement_component identifies one material layer already detected in a focused question's
candidate sources: subject or definition, action or mechanism, significance or consequence,
or qualification or counterargument.

For a long institutional-lineage stage, the institutional_handoff dimension carries an
orientation_only object with four planner-proposed search fields: bearer, inherited_capacity,
transfer_mechanism, and outgoing_capacity. That object is not manuscript evidence and must never
be copied or asserted merely because it appears in the request. Test all four fields against the
obligation's one source scope. When the source supports them, write one coherent atomic sentence
that names the bearer, says what capacity it inherited, states how that capacity was transferred
or transformed, and identifies what capacity passed to the next stage. When the source does not
support that complete handoff, mark institutional_handoff partial, unsupported, or conflicting
without filling gaps from chronology or planner language.

For each stage obligation dimension:
- mark it supported only when an atomic answer unit states material directly supported by
  that obligation's one source scope;
- otherwise use partial, unsupported, or conflicting honestly and keep unsupported
  dimensions free of unit and source mappings;
- link a broad-answer unit to the exact obligation and dimension only when it realizes that
  synthesis obligation; other directly relevant units may use an empty obligation_links list;
- cite only that obligation's single source in a linked unit, even if another source is
  similar; and
- use only the obligation's allowed requirement IDs on that unit.

For each adjacent_stage_link obligation:
- attempt one atomic sentence that explicitly states a causal or institutional continuation,
  transformation, or departure connecting the two ordered requirements to the user's question;
- use exactly both allowed requirement IDs, in their supplied order, and role cause or mechanism;
- cite only source_number, never predecessor_source_number, because the later source must itself
  state the connection;
- do not infer a link merely because the predecessor and current stages are independently true;
  and
- when the transition source does not directly state the relationship, mark the link unsupported
  with no unit or source mapping rather than inventing connective tissue.

For each requirement_component obligation:
- attempt one concise atomic unit that covers the named component dimension for its one allowed
  requirement using only the obligation's one source scope;
- do not merely repeat another component in different words;
- cite only the obligation's source_number and use only its one allowed requirement ID; and
- mark the component partial, unsupported, or conflicting honestly when the scoped passage does
  not directly support it.

Role compatibility is exact: stage_development uses definition, identity, event, or
chronology; cause_or_enabler and mechanism use cause or mechanism; consequence uses event,
mechanism, consequence, or chronology; continuity_or_change uses mechanism, consequence,
chronology, or qualification; qualification uses counterargument or qualification; and
adjacent_stage_link uses cause or mechanism. Institutional_handoff uses cause, mechanism, event,
or chronology. Subject_or_definition uses definition, identity, event, or chronology;
action_or_mechanism uses cause, mechanism, or event;
significance_or_consequence uses event, mechanism, consequence, or chronology; and
qualification_or_counterargument uses counterargument or qualification. A unit
may realize several dimensions of the same source scope when its one claim genuinely does
so. Premise corrections have no obligation links. When no synthesis_obligations are listed,
return an empty obligation_coverage list and empty obligation_links on every unit.

Mark a coarse requirement supported only when every supplied synthesis obligation dimension
flagged as required for that requirement is supported. If some directly supported
material is present but that completeness condition is not met, mark the requirement partial.
The supplied ledger is bounded so one dedicated supported unit per listed obligation
dimension, plus any premise-correction units, fits within answer_units. Never reference a
unit_id that is absent from answer_units. Share a unit across obligation dimensions only
when its one atomic claim genuinely realizes every linked dimension.
"""


_OBLIGATION_DIMENSIONS_BY_FOCUS: Mapping[
    EvidenceObligationFocus,
    tuple[EvidenceDimension, ...],
] = {
    EvidenceObligationFocus.ORIGIN: (
        EvidenceDimension.CAUSE_OR_ENABLER,
        EvidenceDimension.STAGE_DEVELOPMENT,
    ),
    EvidenceObligationFocus.TRANSITION: (
        EvidenceDimension.MECHANISM,
        EvidenceDimension.CAUSE_OR_ENABLER,
        EvidenceDimension.STAGE_DEVELOPMENT,
        EvidenceDimension.CONSEQUENCE,
    ),
    EvidenceObligationFocus.MECHANISM: (
        EvidenceDimension.MECHANISM,
        EvidenceDimension.CAUSE_OR_ENABLER,
        EvidenceDimension.CONSEQUENCE,
    ),
    EvidenceObligationFocus.ENDPOINT: (
        EvidenceDimension.CONTINUITY_OR_CHANGE,
        EvidenceDimension.CONSEQUENCE,
        EvidenceDimension.QUALIFICATION,
    ),
    EvidenceObligationFocus.CROSS_CUTTING: (
        EvidenceDimension.MECHANISM,
        EvidenceDimension.STAGE_DEVELOPMENT,
        EvidenceDimension.CONSEQUENCE,
    ),
}

_OBLIGATION_FOCUS_BY_FACET_ROLE: Mapping[
    FacetRole,
    EvidenceObligationFocus,
] = {
    FacetRole.ORIGIN: EvidenceObligationFocus.ORIGIN,
    FacetRole.TRANSITION: EvidenceObligationFocus.TRANSITION,
    FacetRole.MECHANISM: EvidenceObligationFocus.MECHANISM,
    FacetRole.ENDPOINT: EvidenceObligationFocus.ENDPOINT,
}

_FOCUSED_COMPONENT_ORDER = (
    EvidenceDimension.SUBJECT_OR_DEFINITION,
    EvidenceDimension.ACTION_OR_MECHANISM,
    EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE,
    EvidenceDimension.QUALIFICATION_OR_COUNTERARGUMENT,
)
_FOCUSED_COMPONENT_SIGNAL_PATTERNS: Mapping[
    EvidenceDimension,
    re.Pattern[str],
] = {
    EvidenceDimension.SUBJECT_OR_DEFINITION: re.compile(
        r"\b(?:is|was|were|served\s+as|known\s+as|defined\s+as|"
        r"consisted\s+of|comprised|represented|became)\b",
        flags=re.IGNORECASE,
    ),
    EvidenceDimension.ACTION_OR_MECHANISM: re.compile(
        r"\b(?:because|by|through|used|ordered|allowed|enabled|required|"
        r"created|organized|implemented|financed|funded|enforced|arranged|"
        r"established|instituted|operated|supplied|provided|demanded)\b",
        flags=re.IGNORECASE,
    ),
    EvidenceDimension.SIGNIFICANCE_OR_CONSEQUENCE: re.compile(
        r"\b(?:thereby|therefore|thus|led\s+to|resulted\s+in|"
        r"gave\s+rise\s+to|helped|made\s+possible|meant|consequence|"
        r"significan\w*|pivotal|expanded|increased|reduced|transformed|"
        r"secured|preserved)\b",
        flags=re.IGNORECASE,
    ),
    EvidenceDimension.QUALIFICATION_OR_COUNTERARGUMENT: re.compile(
        r"\b(?:however|although|though|but|yet|rather|nevertheless|"
        r"nonetheless|despite|while|in\s+practice|even\s+though|"
        r"notwithstanding|except|limited|failed|could\s+not|did\s+not)\b",
        flags=re.IGNORECASE,
    ),
}
_FOCUSED_COMPONENT_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "answer",
        "book",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "manuscript",
        "of",
        "on",
        "question",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceInspectionScope:
    """A source range the model must inspect without an output obligation."""

    inspection_id: str
    source_number: int
    paragraph_start: int
    paragraph_end: int
    allowed_requirement_ids: tuple[str, ...]
    focus: EvidenceObligationFocus


@dataclass(frozen=True, slots=True)
class RagPolicy:
    version: str = RAG_POLICY_VERSION
    decomposition: bool = True
    premise_checking: bool = True
    absence_gate: bool = True


@dataclass(frozen=True, slots=True)
class AnswerModeResult:
    answer: str
    final_chunks: list[dict[str, Any]]
    status: str
    plan: QuestionPlan
    evidence_decision: str
    diagnostics: dict[str, Any]

    @property
    def resolved_question(self) -> str:
        original = next(
            (facet.search_query for facet in self.plan.facets if facet.role is FacetRole.ORIGINAL),
            "",
        )
        return original


def answer_run_diagnostics(result: AnswerModeResult) -> dict[str, Any]:
    """Project internal diagnostics into a stable, passage-free API/ledger record."""

    raw_diagnostics = getattr(result, "diagnostics", {})
    diagnostics = raw_diagnostics if isinstance(raw_diagnostics, Mapping) else {}
    generation = diagnostics.get("generation")
    generation = generation if isinstance(generation, Mapping) else {}
    raw_timings = diagnostics.get("stage_timings_ms")
    raw_timings = raw_timings if isinstance(raw_timings, Mapping) else {}
    raw_planner = diagnostics.get("planner")
    raw_planner = raw_planner if isinstance(raw_planner, Mapping) else {}
    valid_error_codes = {code.value for code in CoverageValidationErrorCode}
    valid_results = {value.value for value in DiagnosticValidationResult}

    validation_result = generation.get("validation_result")
    if validation_result not in valid_results:
        validation_result = DiagnosticValidationResult.NOT_RUN.value
    validation_error_code = generation.get("error_code")
    if validation_error_code not in valid_error_codes:
        validation_error_code = None

    repair_codes = tuple(
        dict.fromkeys(
            code for code in (generation.get("repair_codes") or ()) if code in valid_error_codes
        )
    )
    stage_timings_ms = {
        key: round(float(value), 3)
        for key, value in raw_timings.items()
        if (
            key in ANSWER_STAGE_TIMING_KEYS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0
        )
    }
    planner_status = raw_planner.get("status")
    if planner_status not in {"not_called", "succeeded", "failed"}:
        planner_status = "not_called"
    planner_failure_code = _safe_failure_code(raw_planner.get("failure_code"))
    planner_exception_class = safe_planner_exception_class(raw_planner.get("exception_class"))
    planner_exception_code = safe_planner_exception_code(raw_planner.get("exception_code"))
    planner_validation_code = safe_planner_validation_code(
        raw_planner.get("planner_validation_code")
    )
    if planner_status != "failed":
        planner_failure_code = None
        planner_exception_class = None
        planner_exception_code = None
        planner_validation_code = None
    elif planner_failure_code != "invalid_planner_output":
        planner_validation_code = None
    planner = {
        "schema": PLANNER_CALL_DIAGNOSTICS_SCHEMA,
        "status": planner_status,
        "failure_code": planner_failure_code,
        "planner_validation_code": planner_validation_code,
        "exception_class": planner_exception_class,
        "exception_code": planner_exception_code,
    }
    if result.status == "legacy_answer":
        cohort = {
            "rag_policy_version": LEGACY_RAG_POLICY_VERSION,
            "query_planner_prompt_version": NOT_APPLICABLE_COHORT_VALUE,
            "coverage_prompt_version": NOT_APPLICABLE_COHORT_VALUE,
            "normalizer_version": NOT_APPLICABLE_COHORT_VALUE,
            "coverage_instructions_sha256": NOT_APPLICABLE_COHORT_VALUE,
            "coverage_schema_sha256": NOT_APPLICABLE_COHORT_VALUE,
            "generator_model": GENERATOR_SETTINGS.model,
            "generator_reasoning_effort": GENERATOR_SETTINGS.reasoning_effort,
            "generator_verbosity": GENERATOR_SETTINGS.verbosity,
        }
    else:
        cohort = {
            "rag_policy_version": str(diagnostics.get("rag_policy_version") or RAG_POLICY_VERSION),
            "query_planner_prompt_version": QUERY_PLANNER_PROMPT_VERSION,
            "coverage_prompt_version": str(
                generation.get("prompt_version") or EVIDENCE_COVERAGE_PROMPT_VERSION
            ),
            "normalizer_version": str(
                generation.get("normalizer_version") or EVIDENCE_COVERAGE_NORMALIZER_VERSION
            ),
            "coverage_instructions_sha256": str(
                generation.get("instructions_sha256")
                or hashlib.sha256(EVIDENCE_COVERAGE_INSTRUCTIONS.encode("utf-8")).hexdigest()
            ),
            "coverage_schema_sha256": str(
                generation.get("schema_sha256")
                or hashlib.sha256(
                    json.dumps(
                        EvidenceCoverageAnswer.model_json_schema(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            ),
            "generator_model": str(generation.get("generator_model") or GENERATOR_SETTINGS.model),
            "generator_reasoning_effort": str(
                generation.get("generator_reasoning_effort") or GENERATOR_SETTINGS.reasoning_effort
            ),
            "generator_verbosity": str(
                generation.get("generator_verbosity") or GENERATOR_SETTINGS.verbosity
            ),
        }
    return {
        "schema": ANSWER_RUN_DIAGNOSTICS_SCHEMA,
        "cohort": cohort,
        "answer_status": result.status,
        "evidence_decision": result.evidence_decision,
        "validation_result": validation_result,
        "validation_error_code": validation_error_code,
        "repair_applied": bool(generation.get("repair_applied")) and bool(repair_codes),
        "repair_codes": list(repair_codes),
        "planner": planner,
        "stage_timings_ms": stage_timings_ms,
    }


EVIDENCE_PLANNED_POLICY = RagPolicy()


def _elapsed_ms(start_ns: int) -> float:
    return round(max(0, perf_counter_ns() - start_ns) / 1_000_000, 3)


_SAFE_FAILURE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def _safe_failure_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if _SAFE_FAILURE_CODE.fullmatch(value) is not None else None


def _planner_call_diagnostic(
    status: str,
    *,
    failure_code: str | None = None,
    planner_validation_code: str | None = None,
    error: Exception | None = None,
) -> dict[str, str | None]:
    safe_failure_code = _safe_failure_code(failure_code)
    safe_validation_code = safe_planner_validation_code(planner_validation_code)
    if status != "failed" or safe_failure_code != "invalid_planner_output":
        safe_validation_code = None
    exception_class = None
    exception_code = None
    if error is not None:
        exception_class = safe_planner_exception_class(type(error).__name__)
        for attribute in ("code", "status_code"):
            try:
                exception_code = safe_planner_exception_code(getattr(error, attribute, None))
            except Exception:
                exception_code = None
            if exception_code is not None:
                break
    return {
        "schema": PLANNER_CALL_DIAGNOSTICS_SCHEMA,
        "status": status,
        "failure_code": safe_failure_code,
        "planner_validation_code": safe_validation_code,
        "exception_class": exception_class,
        "exception_code": exception_code,
    }


def _planner_trace_diagnostic(
    diagnostic: Mapping[str, object],
) -> dict[str, object]:
    exception_class = diagnostic.get("exception_class")
    return {
        "schema": diagnostic.get("schema"),
        "status": diagnostic.get("status"),
        "failure_code": diagnostic.get("failure_code"),
        "planner_validation_code": diagnostic.get("planner_validation_code"),
        "exception_class_sha256": (
            hashlib.sha256(exception_class.encode("utf-8")).hexdigest()
            if isinstance(exception_class, str) and exception_class
            else None
        ),
        "exception_code": diagnostic.get("exception_code"),
    }


def _replace_diagnostic(
    target: dict[str, Any] | None,
    diagnostic: Mapping[str, object],
) -> None:
    if target is None:
        return
    target.clear()
    target.update(diagnostic)


def without_automatic_retries(client: object) -> object:
    """Return a no-retry client when the SDK supports scoped options."""
    with_options = getattr(client, "with_options", None)
    if callable(with_options):
        return with_options(max_retries=0)
    return client


def build_document_catalog(
    chunks: Sequence[Mapping[str, object]],
) -> tuple[DocumentCatalogEntry, ...]:
    """Build a passage-free eligible document catalog in corpus order.

    Each entry includes a bounded token profile derived locally from that
    document.  The profile contains no sentence or excerpt and remains search
    orientation rather than evidence.
    """

    role_terms_by_document = derive_document_role_terms(chunks)
    seen: set[str] = set()
    catalog: list[DocumentCatalogEntry] = []
    for ordinal, chunk in enumerate(chunks):
        document = str(chunk.get("document") or "")
        if not document or document in seen or should_skip_document(document):
            continue
        seen.add(document)
        title = str(chunk.get("chapter_title") or "").strip() or document
        catalog.append(
            DocumentCatalogEntry(
                document_id=document,
                chapter_title=title,
                corpus_ordinal=ordinal,
                role_terms=role_terms_by_document.get(document, ()),
            )
        )
    return tuple(catalog)


def build_planner_input(
    resolved_turn: ResolvedTurn,
    document_catalog: Sequence[DocumentCatalogEntry],
) -> str:
    route_traits = route_question(resolved_turn)
    broad_stage_requirement_count = (
        LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS
        if RouteTrait.LONG_INSTITUTIONAL_LINEAGE in route_traits
        else BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS
        if requires_broad_narrative_span(resolved_turn)
        else MIN_BROAD_STAGE_REQUIREMENTS
        if RouteTrait.BROAD_SYNTHESIS in route_traits
        else 0
    )
    payload = {
        "resolved_turn": resolved_turn.model_dump(mode="json", by_alias=True),
        "route_traits": [trait.value for trait in route_traits],
        "broad_stage_requirement_count": broad_stage_requirement_count,
        "document_role_profile_version": DOCUMENT_ROLE_PROFILE_VERSION,
        "eligible_document_catalog": [entry.model_dump(mode="json") for entry in document_catalog],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def plan_question(
    client: object,
    resolved_turn: ResolvedTurn,
    document_catalog: Sequence[DocumentCatalogEntry],
    *,
    policy: RagPolicy = EVIDENCE_PLANNED_POLICY,
    planner_diagnostics: dict[str, Any] | None = None,
) -> QuestionPlan:
    """Run at most one structured planner call, then validate or fall back locally."""
    _replace_diagnostic(
        planner_diagnostics,
        _planner_call_diagnostic("not_called"),
    )
    if not policy.decomposition or not requires_planning(resolved_turn):
        return build_question_plan(resolved_turn)
    try:
        response = tracked_responses_parse(
            without_automatic_retries(client),
            operation="query_planning",
            instructions=(
                QUERY_PLANNER_INSTRUCTIONS + "\n" + QUERY_PLANNER_ADDITIONAL_INSTRUCTIONS
            ),
            input=build_planner_input(resolved_turn, document_catalog),
            text_format=PlannerQuestionPlan,
            max_output_tokens=MAX_PLANNER_OUTPUT_TOKENS,
            **QUERY_PLANNER_SETTINGS.responses_create_kwargs(),
        )
    except CostLimitExceeded as error:
        _replace_diagnostic(
            planner_diagnostics,
            _planner_call_diagnostic(
                "failed",
                failure_code="cost_limit_exceeded",
                error=error,
            ),
        )
        raise
    except Exception as error:
        _replace_diagnostic(
            planner_diagnostics,
            _planner_call_diagnostic(
                "failed",
                failure_code="planner_call_failed",
                error=error,
            ),
        )
        return build_question_plan(
            resolved_turn,
            fallback_reason="planner_call_failed",
        )

    parsed = getattr(response, "output_parsed", None)
    validation_diagnostics: dict[str, str | None] = {}
    plan = build_question_plan(
        resolved_turn,
        parsed,
        document_catalog,
        fallback_reason=(None if parsed is not None else "planner_refused_or_unparsed"),
        validation_diagnostics=validation_diagnostics,
    )
    if plan.planner_used:
        _replace_diagnostic(
            planner_diagnostics,
            _planner_call_diagnostic("succeeded"),
        )
    else:
        _replace_diagnostic(
            planner_diagnostics,
            _planner_call_diagnostic(
                "failed",
                failure_code=plan.fallback_reason or "invalid_planner_output",
                planner_validation_code=validation_diagnostics.get("planner_validation_code"),
            ),
        )
    return plan


def assess_answer_corpus_integrity(
    eligible_chunks: Sequence[Mapping[str, object]],
    collection_count: int,
    corpus_manifest: Mapping[str, object] | None,
    corpus_manifest_sha256: str | None,
    *,
    actual_collection_name: str | None = None,
    actual_hnsw_space: str | None = None,
    collection_metadata: Mapping[str, object] | None = None,
    collection_records: Mapping[str, object] | None = None,
    require_store_identity: bool = False,
) -> CorpusIntegrity:
    manifest_chunks: list[Mapping[str, object]] = []
    expected_collection_count = len(eligible_chunks)
    manifest_store: Mapping[str, object] = {}
    if corpus_manifest is not None:
        raw_chunks = corpus_manifest.get("chunks")
        if isinstance(raw_chunks, list):
            manifest_chunks = [
                chunk
                for chunk in raw_chunks
                if isinstance(chunk, Mapping)
                and not should_skip_document(str(chunk.get("document") or ""))
            ]
        store = corpus_manifest.get("store")
        if isinstance(store, Mapping):
            manifest_store = store
            raw_count = store.get("embedded_chunk_count")
            if isinstance(raw_count, int) and not isinstance(raw_count, bool):
                expected_collection_count = raw_count
    manifest_ids = [str(chunk.get("chunk_id") or "") for chunk in manifest_chunks]
    if not manifest_ids:
        manifest_ids = [str(chunk.get("chunk_id") or "") for chunk in eligible_chunks]
    manifest_hash = corpus_manifest_sha256 or ""
    integrity = assess_corpus_integrity(
        eligible_chunks,
        manifest_eligible_chunk_ids=manifest_ids,
        expected_manifest_sha256=manifest_hash,
        loaded_manifest_sha256=manifest_hash,
        expected_collection_count=expected_collection_count,
        collection_count=collection_count,
    )
    manifest_text_hashes = {
        str(chunk.get("chunk_id") or ""): str(chunk.get("text_sha256") or "").casefold()
        for chunk in manifest_chunks
    }
    if not manifest_chunks or any(
        not re.fullmatch(r"[0-9a-f]{64}", manifest_text_hashes.get(chunk_id, ""))
        for chunk_id in manifest_ids
    ):
        return integrity.with_failure("manifest_text_identity_missing")
    loaded_ids = [str(chunk.get("chunk_id") or "") for chunk in eligible_chunks]
    if loaded_ids != manifest_ids:
        integrity = integrity.with_failure("manifest_chunk_order_mismatch")
    manifest_by_id = {str(chunk.get("chunk_id") or ""): chunk for chunk in manifest_chunks}
    if any(
        (
            str(chunk.get("document") or "")
            != str(manifest_by_id.get(chunk_id, {}).get("document") or "")
            or chunk.get("paragraph_start")
            != manifest_by_id.get(chunk_id, {}).get("paragraph_start")
            or chunk.get("paragraph_end") != manifest_by_id.get(chunk_id, {}).get("paragraph_end")
            or len(str(chunk.get("text") or ""))
            != manifest_by_id.get(chunk_id, {}).get("char_count")
        )
        for chunk, chunk_id in zip(eligible_chunks, loaded_ids)
    ):
        integrity = integrity.with_failure("manifest_chunk_metadata_mismatch")
    if any(
        hashlib.sha256(str(chunk.get("text") or "").encode("utf-8")).hexdigest()
        != manifest_text_hashes.get(str(chunk.get("chunk_id") or ""))
        for chunk in eligible_chunks
    ):
        integrity = integrity.with_failure("chunk_text_identity_mismatch")
    expected_collection_name = str(manifest_store.get("collection_name") or "")
    if expected_collection_name and expected_collection_name != str(actual_collection_name or ""):
        integrity = integrity.with_failure("collection_name_mismatch")
    expected_hnsw_space = str(manifest_store.get("hnsw_space") or "")
    if expected_hnsw_space and expected_hnsw_space != str(actual_hnsw_space or ""):
        integrity = integrity.with_failure("hnsw_space_mismatch")
    expected_embedding_model = str(manifest_store.get("embedding_model") or "")
    if expected_embedding_model and expected_embedding_model != EMBEDDING_MODEL:
        integrity = integrity.with_failure("embedding_model_mismatch")

    if not require_store_identity:
        return integrity

    if not isinstance(collection_metadata, Mapping):
        integrity = integrity.with_failure("collection_metadata_missing")
    else:
        expected_chunks_sha256 = str((corpus_manifest or {}).get("chunks_sha256") or "")
        if (
            not expected_chunks_sha256
            or str(collection_metadata.get("chunks_sha256") or "") != expected_chunks_sha256
        ):
            integrity = integrity.with_failure("collection_chunks_identity_mismatch")
        if (
            expected_embedding_model
            and str(collection_metadata.get("embedding_model") or "") != expected_embedding_model
        ):
            integrity = integrity.with_failure("collection_embedding_model_mismatch")
        if (
            expected_hnsw_space
            and str(collection_metadata.get("hnsw:space") or "") != expected_hnsw_space
        ):
            integrity = integrity.with_failure("collection_hnsw_space_mismatch")

    if not isinstance(collection_records, Mapping):
        return integrity.with_failure("collection_records_missing")
    raw_store_ids = collection_records.get("ids")
    raw_store_metadatas = collection_records.get("metadatas")
    if not isinstance(raw_store_ids, list) or not isinstance(raw_store_metadatas, list):
        return integrity.with_failure("collection_records_malformed")
    store_ids = [str(value) for value in raw_store_ids]
    if len(store_ids) != len(set(store_ids)) or set(store_ids) != set(manifest_ids):
        integrity = integrity.with_failure("collection_chunk_ids_mismatch")
    if len(raw_store_metadatas) != len(store_ids):
        return integrity.with_failure("collection_metadata_count_mismatch")
    store_metadata_by_id = {
        chunk_id: metadata
        for chunk_id, metadata in zip(store_ids, raw_store_metadatas)
        if isinstance(metadata, Mapping)
    }
    if len(store_metadata_by_id) != len(store_ids):
        return integrity.with_failure("collection_chunk_metadata_missing")

    for chunk_id in manifest_ids:
        expected = manifest_by_id.get(chunk_id, {})
        actual = store_metadata_by_id.get(chunk_id)
        if actual is None:
            integrity = integrity.with_failure("collection_chunk_metadata_missing")
            continue
        stored_text = actual.get("text")
        if (
            str(actual.get("chunk_id") or "") != chunk_id
            or str(actual.get("document") or "") != str(expected.get("document") or "")
            or actual.get("paragraph_start") != expected.get("paragraph_start")
            or actual.get("paragraph_end") != expected.get("paragraph_end")
            or not isinstance(stored_text, str)
            or len(stored_text) != expected.get("char_count")
            or hashlib.sha256(str(stored_text).encode("utf-8")).hexdigest()
            != manifest_text_hashes.get(chunk_id)
        ):
            integrity = integrity.with_failure("collection_chunk_metadata_mismatch")
            break
    return integrity


def preflight_answer_corpus(
    *,
    collection_handle: object,
    chunks: Sequence[Mapping[str, object]],
    corpus_manifest: Mapping[str, object] | None,
    corpus_manifest_sha256: str | None,
    require_store_identity: bool,
) -> CorpusIntegrity:
    """Verify local corpus and store identity without an OpenAI operation."""

    eligible_chunks = [
        chunk for chunk in chunks if not should_skip_document(str(chunk.get("document") or ""))
    ]
    collection_count = int(collection_handle.count())
    actual_collection_name = str(getattr(collection_handle, "name", "") or "")
    collection_metadata = getattr(collection_handle, "metadata", None)
    configuration = getattr(collection_handle, "configuration", {})
    actual_hnsw_space: str | None = None
    if isinstance(configuration, Mapping):
        hnsw = configuration.get("hnsw")
        if isinstance(hnsw, Mapping):
            actual_hnsw_space = str(hnsw.get("space") or "")
    if not actual_hnsw_space and isinstance(collection_metadata, Mapping):
        actual_hnsw_space = str(collection_metadata.get("hnsw:space") or "")

    collection_records: Mapping[str, object] | None = None
    if require_store_identity:
        getter = getattr(collection_handle, "get", None)
        if callable(getter):
            try:
                raw_records = getter(include=["metadatas"])
            except Exception:
                raw_records = None
            if isinstance(raw_records, Mapping):
                collection_records = raw_records

    return assess_answer_corpus_integrity(
        eligible_chunks,
        collection_count,
        corpus_manifest,
        corpus_manifest_sha256,
        actual_collection_name=actual_collection_name,
        actual_hnsw_space=actual_hnsw_space,
        collection_metadata=(
            collection_metadata if isinstance(collection_metadata, Mapping) else None
        ),
        collection_records=collection_records,
        require_store_identity=require_store_identity,
    )


def _parse_related_probe(
    plan: QuestionPlan,
    trusted_user_texts: Sequence[str],
) -> tuple[str, tuple[str, ...]] | None:
    normalized_trusted_texts = tuple(
        f" {normalize_search_query(value)} " for value in trusted_user_texts if value.strip()
    )
    if not normalized_trusted_texts:
        return None
    for facet in plan.facets:
        if facet.role is not FacetRole.BROADER_RELATED:
            continue
        match = _RELATED_PROBE_PATTERN.fullmatch(facet.search_query)
        if match is None:
            continue
        broader = match.group("broader").strip()
        related = tuple(
            value.strip() for value in match.group("related").split(",") if value.strip()
        )
        trusted_surfaces = (broader, *related)
        if (
            broader
            and related
            and all(
                any(
                    f" {normalize_search_query(surface)} " in trusted_text
                    for trusted_text in normalized_trusted_texts
                )
                for surface in trusted_surfaces
            )
        ):
            return broader, related
    return None


def _derive_trusted_related_probe(
    plan: QuestionPlan,
    trusted_user_texts: Sequence[str],
) -> tuple[str, tuple[str, ...]] | None:
    """Derive one bounded broader/probe pair from an exact user-message tail."""

    subject_targets = [
        target
        for target in plan.targets
        if target.role.value == PolicyTargetRole.SUBJECT.value and target.absence_checkable
    ]
    if len(subject_targets) != 1:
        return None
    surface = subject_targets[0].query_surface_span
    if len(split_compound_named_anchor(surface)) != 1:
        return None

    for trusted_text in reversed(tuple(trusted_user_texts)):
        target_match = re.search(
            re.escape(surface),
            trusted_text,
            flags=re.IGNORECASE,
        )
        if target_match is None:
            continue
        suffix_match = _TRUSTED_RELATED_TAIL_PATTERN.fullmatch(trusted_text[target_match.end() :])
        if suffix_match is None:
            continue
        tail = suffix_match.group("tail").strip()
        for prefix in _TRUSTED_RELATED_PREFIX_PATTERNS:
            stripped = prefix.sub("", tail, count=1)
            if stripped != tail:
                tail = stripped.strip()
                break
        else:
            continue

        tokens = tokenize_anchor(tail)
        if not 2 <= len(tokens) <= _MAX_TRUSTED_RELATED_TOKENS:
            continue
        return tokens[0], (" ".join(tokens[1:]),)
    return None


_BOUNDED_RELATED_FACET_ROLES = frozenset(
    {
        FacetRole.BROADER_RELATED,
        FacetRole.ENDPOINT,
        FacetRole.MECHANISM,
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
    }
)


def _contains_normalized_surface(query: str, surface: str) -> bool:
    normalized_query = f" {normalize_search_query(query)} "
    normalized_surface = normalize_search_query(surface)
    return bool(
        normalized_surface
        and f" {normalized_surface} " in normalized_query
    )


def _bounded_planner_related_chunk_ids(
    plan: QuestionPlan,
    planned: PlannedContext,
    subject_scan: EvidenceTargetScan,
    related_spec: tuple[str, tuple[str, ...]] | None,
) -> tuple[str, ...]:
    """Return at most two requirement-linked hinted sources for qualified absence.

    The planner may rank related material but cannot establish that the absent
    subject exists. Every admitted facet must preserve the exact trusted subject
    and relation surfaces and remain scoped by an exact validated catalog hint.
    """

    if (
        RouteTrait.ABSENCE_SENSITIVE not in plan.traits
        or not plan.planner_used
        or plan.premises
        or related_spec is None
    ):
        return ()
    subject_surface = next(
        (
            target.query_surface_span
            for target in plan.targets
            if target.target_id == subject_scan.target_id
        ),
        "",
    )
    trusted_surfaces = (
        subject_surface,
        related_spec[0],
        *related_spec[1],
    )
    selected: list[str] = []
    for facet in plan.facets:
        if (
            facet.facet_id == "F0"
            or facet.role not in _BOUNDED_RELATED_FACET_ROLES
            or not facet.requirement_ids
            or not facet.document_hints
            or not all(
                _contains_normalized_surface(facet.search_query, surface)
                for surface in trusted_surfaces
            )
        ):
            continue
        for source_number in planned.facet_source_numbers.get(facet.facet_id, ()):
            if not 1 <= source_number <= len(planned.final_chunks):
                continue
            chunk_id = str(
                planned.final_chunks[source_number - 1].get("chunk_id") or ""
            )
            if chunk_id and chunk_id not in selected:
                selected.append(chunk_id)
            if len(selected) == MAX_QUALIFIED_NEAR_MATCH_SOURCES:
                return tuple(selected)
    return tuple(selected)


def _all_sources_gate(
    planned: PlannedContext,
    integrity: CorpusIntegrity,
    *,
    rule: str,
) -> EvidenceGateResult:
    assignments = tuple(
        EvidenceLaneAssignment(
            source_number=number,
            chunk_id=str(chunk.get("chunk_id") or ""),
            lane=EvidenceLane.GENERIC_SEMANTIC,
        )
        for number, chunk in enumerate(planned.final_chunks, start=1)
    )
    return EvidenceGateResult(
        decision=EvidenceDecision.DIRECT_ANSWER,
        certified_direct_absence=False,
        premise_correction_required=False,
        relationship_chunk_ids=(),
        allowed_source_numbers=tuple(range(1, len(planned.final_chunks) + 1)),
        suppressed_source_numbers=(),
        lane_assignments=assignments,
        rules_fired=(rule,),
        integrity=integrity,
    )


def _promote_direct_anchor_chunks(
    plan: QuestionPlan,
    planned: PlannedContext,
    scans: Sequence[EvidenceTargetScan],
    eligible_chunks: Sequence[Mapping[str, object]],
    *,
    facet_scan: EvidenceTargetScan | None,
    immediate_neighbors: Mapping[str, Sequence[str]],
) -> None:
    """Guarantee corpus-scan hits without erasing planned coverage obligations."""
    lookup = {str(chunk.get("chunk_id") or ""): dict(chunk) for chunk in eligible_chunks}
    requested_anchor_ids: list[str] = []
    if scans and facet_scan is not None:
        requested_anchor_ids.extend(
            relationship_evidence_chunk_ids(
                scans[0],
                facet_scan,
                immediate_neighbors=immediate_neighbors,
            )
        )
    for scan in scans:
        # One certified hit per target is a hard admission obligation.
        # Additional hits remain available through ordinary retrieval.
        requested_anchor_ids.extend(scan.direct_chunk_ids[:1])
    requested_anchor_ids = list(
        dict.fromkeys(
            chunk_id for chunk_id in requested_anchor_ids if chunk_id in lookup
        )
    )
    if not requested_anchor_ids:
        return

    old_chunks = list(planned.final_chunks)
    old_ids = [str(chunk.get("chunk_id") or "") for chunk in old_chunks]
    selection = planned.trace.setdefault("selection", {})
    selection["pre_anchor_context"] = list(selection.get("context", []))
    old_facet_chunk_ids = {
        facet_id: [
            old_ids[source_number - 1]
            for source_number in source_numbers
            if 1 <= source_number <= len(old_ids)
        ]
        for facet_id, source_numbers in planned.facet_source_numbers.items()
    }

    protected_ids: list[str] = []
    protected_facet_ids: set[str] = set()

    def protect_first(facet_id: str) -> None:
        if facet_id in protected_facet_ids:
            return
        protected_facet_ids.add(facet_id)
        stage_anchor_id = planned.broad_stage_anchor_chunk_ids.get(facet_id)
        if stage_anchor_id in old_ids:
            if stage_anchor_id not in protected_ids:
                protected_ids.append(stage_anchor_id)
            return
        for chunk_id in old_facet_chunk_ids.get(facet_id, ()):
            if chunk_id not in protected_ids:
                protected_ids.append(chunk_id)
                return

    # Preserve one dedicated lane for every requested answer component.
    for requirement in plan.requirements:
        for facet in plan.facets:
            if (
                facet.facet_id != "F0"
                and requirement.requirement_id in facet.requirement_ids
                and old_facet_chunk_ids.get(facet.facet_id)
            ):
                protect_first(facet.facet_id)
                break

    # Premise support, counter, and framing remain independent obligations.
    for premise in plan.premises:
        protect_first(premise.support_facet_id)
        protect_first(premise.counter_facet_id)
        if premise.framing_facet_id is not None:
            protect_first(premise.framing_facet_id)

    # Broad plans promise coverage across their live facets, not merely across
    # a shared requirement identifier.
    if RouteTrait.BROAD_SYNTHESIS in plan.traits:
        for facet in plan.facets:
            if facet.facet_id != "F0":
                protect_first(facet.facet_id)

    # Protected retrieval lanes reserve their capacity before a newly promoted
    # corpus anchor can consume it. Anchors already present in a protected lane
    # require no additional slot.
    admitted_anchor_ids: list[str] = []
    mandatory_ids = list(dict.fromkeys(protected_ids))
    for chunk_id in requested_anchor_ids:
        if chunk_id in mandatory_ids:
            admitted_anchor_ids.append(chunk_id)
            continue
        if len(mandatory_ids) + len(
            [value for value in admitted_anchor_ids if value not in mandatory_ids]
        ) >= MAX_FINAL_SOURCES:
            continue
        admitted_anchor_ids.append(chunk_id)
    mandatory_order = list(
        dict.fromkeys((*admitted_anchor_ids, *protected_ids))
    )
    remaining_old_ids = [
        chunk_id for chunk_id in old_ids if chunk_id not in mandatory_order
    ]
    represented_documents = {
        str(lookup[chunk_id].get("document") or "")
        for chunk_id in mandatory_order
        if chunk_id in lookup
    }
    unique_document_fill: list[str] = []
    same_document_fill: list[str] = []
    for chunk_id in remaining_old_ids:
        document = str(lookup[chunk_id].get("document") or "")
        if document not in represented_documents:
            unique_document_fill.append(chunk_id)
            represented_documents.add(document)
        else:
            same_document_fill.append(chunk_id)
    new_ids = [
        *mandatory_order,
        *unique_document_fill,
        *same_document_fill,
    ][:MAX_FINAL_SOURCES]
    if RouteTrait.BROAD_SYNTHESIS in plan.traits:
        corpus_ordinal = {
            str(chunk.get("chunk_id") or ""): ordinal
            for ordinal, chunk in enumerate(eligible_chunks)
        }
        new_ids.sort(
            key=lambda chunk_id: (
                corpus_ordinal.get(chunk_id, 10**9),
                chunk_id,
            )
        )
    selection["anchor_requested_count"] = len(requested_anchor_ids)
    selection["anchor_deferred_count"] = sum(
        chunk_id not in admitted_anchor_ids or chunk_id not in new_ids
        for chunk_id in requested_anchor_ids
    )
    selection["protected_source_count"] = len(protected_ids)
    selection["protected_source_shortfall_count"] = sum(
        chunk_id not in new_ids for chunk_id in protected_ids
    )
    if new_ids == old_ids:
        planned.trace.setdefault("plan", {})["anchor_promoted_count"] = 0
        return

    new_chunks = [lookup[chunk_id] for chunk_id in new_ids if chunk_id in lookup]
    source_number_by_id = {
        str(chunk.get("chunk_id") or ""): source_number
        for source_number, chunk in enumerate(new_chunks, start=1)
    }
    f0_id = next(
        (facet_id for facet_id in planned.facet_source_numbers if facet_id == "F0"),
        None,
    )
    new_facet_sources: dict[str, tuple[int, ...]] = {}
    for facet_id, chunk_ids in old_facet_chunk_ids.items():
        mapped_ids = list(chunk_ids)
        if facet_id == f0_id:
            mapped_ids = list(dict.fromkeys((*admitted_anchor_ids, *mapped_ids)))
        new_facet_sources[facet_id] = tuple(
            source_number_by_id[chunk_id]
            for chunk_id in mapped_ids
            if chunk_id in source_number_by_id
        )

    new_lane_by_id = {chunk_id: planned.lane_by_chunk_id.get(chunk_id, ()) for chunk_id in new_ids}
    if f0_id is not None:
        for chunk_id in admitted_anchor_ids:
            new_lane_by_id[chunk_id] = tuple(
                dict.fromkeys((*new_lane_by_id.get(chunk_id, ()), f0_id))
            )

    planned.final_chunks[:] = new_chunks
    planned.facet_source_numbers.clear()
    planned.facet_source_numbers.update(new_facet_sources)
    planned.lane_by_chunk_id.clear()
    planned.lane_by_chunk_id.update(new_lane_by_id)
    if RouteTrait.BROAD_SYNTHESIS in plan.traits:
        stage_facet_ids = {
            facet.facet_id
            for facet in plan.facets
            if facet.role
            in {
                FacetRole.ORIGIN,
                FacetRole.TRANSITION,
                FacetRole.MECHANISM,
                FacetRole.ENDPOINT,
            }
        }
        satisfied_stage_ids = {
            facet_id
            for facet_id in stage_facet_ids
            if new_facet_sources.get(facet_id)
        }
        selection["stage_coverage_required_count"] = len(stage_facet_ids)
        selection["stage_coverage_satisfied_count"] = len(satisfied_stage_ids)
        selection["stage_coverage_shortfall_count"] = (
            len(stage_facet_ids) - len(satisfied_stage_ids)
        )

    promoted = [chunk_id for chunk_id in admitted_anchor_ids if chunk_id not in old_ids]
    planned.trace.setdefault("plan", {})["anchor_promoted_count"] = len(promoted)
    selection["anchor_source_number_remap"] = [
        {
            "pre_anchor_source_number": (
                old_ids.index(chunk_id) + 1 if chunk_id in old_ids else None
            ),
            "post_anchor_source_number": source_number,
        }
        for source_number, chunk_id in enumerate(new_ids, start=1)
    ]
    distribution: dict[str, int] = defaultdict(int)
    for chunk in new_chunks:
        distribution[document_identifier_sha256(chunk.get("document"))] += 1
    documents = selection.setdefault("document_distribution", {})
    if isinstance(documents, dict):
        documents["context"] = dict(sorted(distribution.items()))
    selection["context"] = [
        {
            "chunk_id": str(chunk.get("chunk_id") or ""),
            "document_sha256": document_identifier_sha256(chunk.get("document")),
            "paragraph_start": chunk.get("paragraph_start"),
            "paragraph_end": chunk.get("paragraph_end"),
            "source_number": source_number,
            "origin": (
                "corpus_anchor" if str(chunk.get("chunk_id") or "") in promoted else "retrieval"
            ),
            "facet_ids": list(new_lane_by_id.get(str(chunk.get("chunk_id") or ""), ())),
        }
        for source_number, chunk in enumerate(new_chunks, start=1)
    ]


def apply_evidence_gate(
    plan: QuestionPlan,
    planned: PlannedContext,
    eligible_chunks: Sequence[Mapping[str, object]],
    *,
    trusted_user_texts: Sequence[str] = (),
    collection_count: int,
    corpus_manifest: Mapping[str, object] | None,
    corpus_manifest_sha256: str | None,
    corpus_integrity: CorpusIntegrity | None = None,
    policy: RagPolicy = EVIDENCE_PLANNED_POLICY,
) -> tuple[EvidenceGateResult, dict[str, Any], str | None]:
    """Run the local corpus gate and return trace-safe diagnostics plus target label."""
    integrity = corpus_integrity or assess_answer_corpus_integrity(
        eligible_chunks,
        collection_count,
        corpus_manifest,
        corpus_manifest_sha256,
    )
    if not policy.absence_gate or not plan.targets:
        gate = _all_sources_gate(planned, integrity, rule="absence_gate_not_applicable")
        return (
            gate,
            {
                "schema": EVIDENCE_DIAGNOSTICS_SCHEMA,
                "policy_version": EVIDENCE_POLICY_VERSION,
                "corpus": integrity.as_diagnostics(),
                "targets": [],
                "decision": {
                    "value": gate.decision.value,
                    "allowed_source_numbers": list(gate.allowed_source_numbers),
                    "suppressed_source_numbers": [],
                    "rules_fired": list(gate.rules_fired),
                },
            },
            None,
        )

    scans: list[EvidenceTargetScan] = []
    compound_subject_split = False
    for target in plan.targets:
        surfaces = (
            split_compound_named_anchor(target.query_surface_span)
            if target.role.value == PolicyTargetRole.SUBJECT.value
            else (target.query_surface_span,)
        )
        compound_subject_split = compound_subject_split or len(surfaces) > 1
        for component_index, surface in enumerate(surfaces, start=1):
            scans.append(
                scan_evidence_target(
                    (
                        target.target_id
                        if len(surfaces) == 1
                        else f"{target.target_id}.{component_index}"
                    ),
                    surface,
                    eligible_chunks,
                    absence_checkable=target.absence_checkable,
                    corpus_integrity=integrity,
                    role=PolicyTargetRole(target.role.value),
                )
            )
    subject_scans = [scan for scan in scans if scan.role is PolicyTargetRole.SUBJECT]
    if not subject_scans:
        gate = _all_sources_gate(planned, integrity, rule="no_subject_target")
        return (
            gate,
            {
                "schema": EVIDENCE_DIAGNOSTICS_SCHEMA,
                "policy_version": EVIDENCE_POLICY_VERSION,
                "corpus": integrity.as_diagnostics(),
                "targets": [scan.as_diagnostics() for scan in scans],
                "decision": {
                    "value": gate.decision.value,
                    "allowed_source_numbers": list(gate.allowed_source_numbers),
                    "suppressed_source_numbers": [],
                    "rules_fired": list(gate.rules_fired),
                },
            },
            None,
        )

    subject_scan = subject_scans[0]
    facet_scans = [scan for scan in scans if scan.role is PolicyTargetRole.FACET]
    facet_scan = facet_scans[0] if facet_scans else None
    neighbors = build_immediate_neighbor_map(eligible_chunks)
    _promote_direct_anchor_chunks(
        plan,
        planned,
        scans,
        eligible_chunks,
        facet_scan=facet_scan,
        immediate_neighbors=neighbors,
    )
    if len(subject_scans) > 1 and not facet_scans:
        assignments = classify_evidence_lanes(
            planned.final_chunks,
            subject_scan=subject_scan,
            additional_subject_scans=subject_scans[1:],
            facet_scan=facet_scan,
            immediate_neighbors=neighbors,
        )
        gate = decide_multi_subject_evidence(
            subject_scans,
            lane_assignments=assignments,
        )
        if compound_subject_split:
            gate = replace(
                gate,
                rules_fired=(
                    *gate.rules_fired,
                    "compound_named_subject_split",
                ),
            )
        diagnostics = evidence_diagnostics(
            gate,
            subject_scan=subject_scan,
            facet_scan=facet_scan,
        )
        diagnostics["targets"] = [scan.as_diagnostics() for scan in scans]
        return gate, diagnostics, None
    if len(subject_scans) > 1 or len(facet_scans) > 1:
        assignments = classify_evidence_lanes(
            planned.final_chunks,
            subject_scan=subject_scan,
            facet_scan=facet_scan,
            immediate_neighbors=neighbors,
        )
        gate = EvidenceGateResult(
            decision=EvidenceDecision.INDETERMINATE,
            certified_direct_absence=False,
            premise_correction_required=False,
            relationship_chunk_ids=(),
            allowed_source_numbers=(),
            suppressed_source_numbers=tuple(range(1, len(planned.final_chunks) + 1)),
            lane_assignments=assignments,
            rules_fired=("multiple_targets_require_disambiguation",),
            integrity=integrity,
        )
        diagnostics = evidence_diagnostics(
            gate,
            subject_scan=subject_scan,
            facet_scan=facet_scan,
        )
        diagnostics["targets"] = [scan.as_diagnostics() for scan in scans]
        return gate, diagnostics, None
    related_spec = _parse_related_probe(plan, trusted_user_texts)
    trusted_tail_related = False
    if related_spec is None:
        related_spec = _derive_trusted_related_probe(
            plan,
            trusted_user_texts,
        )
        trusted_tail_related = related_spec is not None
    broader_scan = (
        scan_broader_related(
            related_spec[0],
            related_spec[1],
            eligible_chunks,
            immediate_neighbors=neighbors,
        )
        if related_spec is not None
        else None
    )
    bounded_planner_related_ids = _bounded_planner_related_chunk_ids(
        plan,
        planned,
        subject_scan,
        related_spec,
    )
    lane_assignments = classify_evidence_lanes(
        planned.final_chunks,
        subject_scan=subject_scan,
        facet_scan=facet_scan,
        broader_related_scan=(
            None if bounded_planner_related_ids else broader_scan
        ),
        qualified_related_chunk_ids=bounded_planner_related_ids,
        immediate_neighbors=neighbors,
    )
    gate = decide_evidence(
        subject_scan,
        facet_scan=facet_scan,
        lane_assignments=lane_assignments,
        broader_related_scan=broader_scan,
        immediate_neighbors=neighbors,
    )
    if (
        bounded_planner_related_ids
        and gate.decision is EvidenceDecision.QUALIFIED_NEAR_MATCH
    ):
        gate = replace(
            gate,
            rules_fired=(
                *gate.rules_fired,
                "planner_bounded_related_material",
            ),
        )
    selected_exact_related_ids = (
        set(broader_scan.qualified_chunk_ids)
        if broader_scan is not None
        else set()
    ).intersection(
        assignment.chunk_id
        for assignment in lane_assignments
        if assignment.lane is EvidenceLane.BROADER_RELATED
    )
    if (
        trusted_tail_related
        and selected_exact_related_ids
        and gate.decision is EvidenceDecision.QUALIFIED_NEAR_MATCH
    ):
        gate = replace(
            gate,
            rules_fired=(
                *gate.rules_fired,
                "trusted_related_tail_material",
            ),
        )

    # Premise status is adjudicated against the sources in the one structured answer
    # call. Do not let a surface-form absence suppress those support/counter lanes first.
    if (
        plan.premises
        and policy.premise_checking
        and RouteTrait.PREMISE_SENSITIVE in plan.traits
    ):
        gate = _all_sources_gate(
            planned,
            gate.integrity,
            rule="premise_evaluation_pending",
        )
    diagnostics = evidence_diagnostics(
        gate,
        subject_scan=subject_scan,
        facet_scan=facet_scan,
        broader_related_scan=broader_scan,
    )
    target_label = next(
        (
            target.query_surface_span
            for target in plan.targets
            if target.target_id == subject_scan.target_id
        ),
        None,
    )
    return gate, diagnostics, target_label


def _filter_context(
    planned: PlannedContext,
    allowed_source_numbers: Sequence[int],
) -> tuple[
    list[dict[str, Any]],
    dict[int, int],
    dict[str, tuple[int, ...]],
    dict[str, int],
    dict[tuple[str, str], int],
]:
    allowed = set(allowed_source_numbers)
    selected_pairs = [
        (old_number, chunk)
        for old_number, chunk in enumerate(planned.final_chunks, start=1)
        if old_number in allowed
    ]
    old_to_new = {
        old_number: new_number
        for new_number, (old_number, _chunk) in enumerate(selected_pairs, start=1)
    }
    remapped_facets = {
        facet_id: tuple(old_to_new[number] for number in source_numbers if number in old_to_new)
        for facet_id, source_numbers in planned.facet_source_numbers.items()
    }
    final_chunks = [chunk for _number, chunk in selected_pairs]
    source_number_by_chunk_id = {
        str(chunk.get("chunk_id") or ""): source_number
        for source_number, chunk in enumerate(final_chunks, start=1)
    }
    remapped_stage_anchors = {
        facet_id: source_number_by_chunk_id[chunk_id]
        for facet_id, chunk_id in planned.broad_stage_anchor_chunk_ids.items()
        if chunk_id in source_number_by_chunk_id
    }
    remapped_transition_sources = {
        pair: source_number_by_chunk_id[chunk_id]
        for pair, chunk_id in planned.broad_transition_chunk_ids.items()
        if chunk_id in source_number_by_chunk_id
    }
    return (
        final_chunks,
        old_to_new,
        remapped_facets,
        remapped_stage_anchors,
        remapped_transition_sources,
    )


def _record_generation_context(
    planned: PlannedContext,
    final_chunks: Sequence[Mapping[str, object]],
    old_to_new: Mapping[int, int],
) -> None:
    """Make post-gate citation numbering mechanically auditable."""
    selection = planned.trace.setdefault("selection", {})
    retrieval_context = list(selection.get("context", []))
    selection["retrieval_context"] = retrieval_context
    new_to_old = {new_number: old_number for old_number, new_number in old_to_new.items()}
    generation_context = [
        {
            "source_number": new_number,
            "retrieval_source_number": new_to_old.get(new_number),
            "chunk_id": str(chunk.get("chunk_id") or ""),
            "document_sha256": document_identifier_sha256(chunk.get("document")),
            "paragraph_start": chunk.get("paragraph_start"),
            "paragraph_end": chunk.get("paragraph_end"),
        }
        for new_number, chunk in enumerate(final_chunks, start=1)
    ]
    selection["source_number_remap"] = [
        {
            "retrieval_source_number": old_number,
            "generation_source_number": new_number,
        }
        for old_number, new_number in sorted(old_to_new.items())
    ]
    selection["generation_context"] = generation_context
    selection["context"] = generation_context


def _requirement_source_map(
    plan: QuestionPlan,
    facet_source_numbers: Mapping[str, Sequence[int]],
) -> dict[str, tuple[int, ...]]:
    result: dict[str, list[int]] = defaultdict(list)
    for facet in plan.facets:
        for requirement_id in facet.requirement_ids:
            for source_number in facet_source_numbers.get(facet.facet_id, ()):
                if source_number not in result[requirement_id]:
                    result[requirement_id].append(source_number)
    return {
        requirement.requirement_id: tuple(result[requirement.requirement_id])
        for requirement in plan.requirements
    }


def _focused_requirement_component_scopes(
    plan: QuestionPlan,
    final_chunks: Sequence[Mapping[str, object]],
    facet_source_numbers: Mapping[str, Sequence[int]],
) -> tuple[EvidenceObligationScope, ...]:
    """Bind material focused-answer components to their strongest source.

    This is deliberately application-owned and lexical. It does not infer facts:
    it only promotes component types that are visibly signalled in already
    admitted candidate passages. At least two distinct components must be found
    for a requirement before either becomes mandatory.
    """

    excluded_traits = {
        RouteTrait.ABSENCE_SENSITIVE,
        RouteTrait.BROAD_SYNTHESIS,
        RouteTrait.PREMISE_SENSITIVE,
    }
    if (
        not final_chunks
        or excluded_traits.intersection(plan.traits)
    ):
        return ()

    original_query = next(
        (
            facet.search_query
            for facet in plan.facets
            if facet.role is FacetRole.ORIGINAL
        ),
        "",
    )
    requirement_sources = _requirement_source_map(
        plan,
        facet_source_numbers,
    )
    proposals: list[
        tuple[
            str,
            EvidenceDimension,
            int,
            tuple[int, int],
        ]
    ] = []
    for requirement in sorted(plan.requirements, key=lambda item: item.order):
        query_terms = {
            term
            for term in normalize_search_query(
                f"{requirement.label} {original_query}"
            ).split()
            if term not in _FOCUSED_COMPONENT_STOPWORDS
        }
        best_by_dimension: dict[
            EvidenceDimension,
            tuple[tuple[int, int, int], int, tuple[int, int]],
        ] = {}
        for source_number in requirement_sources.get(
            requirement.requirement_id,
            (),
        ):
            if not 1 <= source_number <= len(final_chunks):
                continue
            chunk = final_chunks[source_number - 1]
            text = str(chunk.get("text") or "")
            text_terms = set(normalize_search_query(text).split())
            query_match_count = len(query_terms & text_terms)
            if query_terms and query_match_count <= 0:
                continue
            paragraph_ranges = _paragraph_scope_ranges(chunk)
            paragraph_range = (
                paragraph_ranges[0][0],
                paragraph_ranges[-1][1],
            )
            for dimension in _FOCUSED_COMPONENT_ORDER:
                signal_score = len(
                    _FOCUSED_COMPONENT_SIGNAL_PATTERNS[dimension].findall(
                        text
                    )
                )
                if signal_score <= 0:
                    continue
                score = (
                    query_match_count,
                    min(signal_score, 8),
                    -source_number,
                )
                existing = best_by_dimension.get(dimension)
                if existing is None or score > existing[0]:
                    best_by_dimension[dimension] = (
                        score,
                        source_number,
                        paragraph_range,
                    )

        if len(best_by_dimension) < 2:
            continue
        for dimension in _FOCUSED_COMPONENT_ORDER:
            selected = best_by_dimension.get(dimension)
            if selected is None:
                continue
            _score, source_number, paragraph_range = selected
            proposals.append(
                (
                    requirement.requirement_id,
                    dimension,
                    source_number,
                    paragraph_range,
                )
            )

    capacity = MAX_ANSWER_UNITS - len(plan.premises)
    scopes = [
        EvidenceObligationScope(
            obligation_id=f"O{index}",
            kind=EvidenceObligationKind.REQUIREMENT_COMPONENT,
            source_number=source_number,
            paragraph_start=paragraph_range[0],
            paragraph_end=paragraph_range[1],
            allowed_requirement_ids=(requirement_id,),
            focus=EvidenceObligationFocus.CROSS_CUTTING,
            dimension_ids=(dimension,),
            required_for_requirement_status=True,
        )
        for index, (
            requirement_id,
            dimension,
            source_number,
            paragraph_range,
        ) in enumerate(proposals[:capacity], start=1)
    ]
    return tuple(scopes)


def _premise_source_scopes(
    plan: QuestionPlan,
    facet_source_numbers: Mapping[str, Sequence[int]],
) -> tuple[PremiseSourceScope, ...]:
    return tuple(
        PremiseSourceScope(
            premise_id=premise.premise_id,
            support_source_numbers=tuple(
                facet_source_numbers.get(premise.support_facet_id, ())
            ),
            counter_source_numbers=tuple(
                facet_source_numbers.get(premise.counter_facet_id, ())
            ),
            framing_source_numbers=(
                tuple(facet_source_numbers.get(premise.framing_facet_id, ()))
                if premise.framing_facet_id is not None
                else ()
            ),
        )
        for premise in plan.premises
    )


def _paragraph_scope_ranges(
    chunk: Mapping[str, object],
) -> tuple[tuple[int, int], ...]:
    """Return paragraph-exact ranges when chunk metadata and text agree.

    A mismatch falls back to one source-wide range so no passage is silently
    omitted and no paragraph identity is invented.
    """

    raw_start = chunk.get("paragraph_start")
    raw_end = chunk.get("paragraph_end")
    if (
        not isinstance(raw_start, int)
        or isinstance(raw_start, bool)
        or raw_start < 1
        or not isinstance(raw_end, int)
        or isinstance(raw_end, bool)
        or raw_end < raw_start
    ):
        return ((1, 1),)

    text = str(chunk.get("text") or "").strip()
    paragraph_blocks = tuple(
        block
        for block in re.split(r"\r?\n[ \t]*\r?\n", text)
        if block.strip()
    )
    expected_count = raw_end - raw_start + 1
    if len(paragraph_blocks) != expected_count:
        return ((raw_start, raw_end),)
    return tuple(
        (paragraph_number, paragraph_number)
        for paragraph_number in range(raw_start, raw_end + 1)
    )


def _coalesce_paragraph_ranges(
    ranges: Sequence[tuple[int, int]],
    group_count: int,
) -> tuple[tuple[int, int], ...]:
    """Partition ordered paragraph ranges into deterministic contiguous groups."""

    if group_count >= len(ranges):
        return tuple(ranges)
    if group_count <= 1:
        return ((ranges[0][0], ranges[-1][1]),)
    return tuple(
        (
            ranges[(group_index * len(ranges)) // group_count][0],
            ranges[
                (((group_index + 1) * len(ranges)) // group_count) - 1
            ][1],
        )
        for group_index in range(group_count)
    )


def _bounded_inspection_ranges(
    final_chunks: Sequence[Mapping[str, object]],
    *,
    max_scopes: int = MAX_BROAD_INSPECTION_SCOPES,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Cover every retained source within the bounded inspection-input cap."""

    raw_ranges = tuple(_paragraph_scope_ranges(chunk) for chunk in final_chunks)
    scope_limit = min(MAX_BROAD_INSPECTION_SCOPES, max_scopes)
    if scope_limit < len(raw_ranges):
        raise ValueError("inspection cap cannot preserve one scope per retained source")
    if sum(len(ranges) for ranges in raw_ranges) <= scope_limit:
        return raw_ranges

    group_counts = [1 for _ranges in raw_ranges]
    remaining = scope_limit - len(raw_ranges)
    while remaining > 0:
        candidates = [
            index
            for index, ranges in enumerate(raw_ranges)
            if group_counts[index] < len(ranges)
        ]
        if not candidates:
            break
        selected = max(
            candidates,
            key=lambda index: (
                len(raw_ranges[index]) / group_counts[index],
                -index,
            ),
        )
        group_counts[selected] += 1
        remaining -= 1

    return tuple(
        _coalesce_paragraph_ranges(ranges, group_counts[index])
        for index, ranges in enumerate(raw_ranges)
    )


def _bounded_obligation_ranges(
    final_chunks: Sequence[Mapping[str, object]],
    *,
    max_obligations: int = MAX_BROAD_EVIDENCE_OBLIGATIONS,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Backward-compatible name for the bounded passage-inspection ranges."""

    return _bounded_inspection_ranges(
        final_chunks,
        max_scopes=max_obligations,
    )


def _stage_facets_for_source(
    plan: QuestionPlan,
    facet_source_numbers: Mapping[str, Sequence[int]],
    source_number: int,
) -> tuple[Any, ...]:
    return tuple(
        facet
        for facet in plan.facets
        if (
            facet.role in _OBLIGATION_FOCUS_BY_FACET_ROLE
            and source_number in facet_source_numbers.get(facet.facet_id, ())
        )
    )


def _ordered_facet_requirement_ids(
    plan: QuestionPlan,
    facets: Sequence[Any],
) -> tuple[str, ...]:
    facet_requirement_ids = {
        requirement_id
        for facet in facets
        for requirement_id in facet.requirement_ids
    }
    return tuple(
        requirement.requirement_id
        for requirement in sorted(plan.requirements, key=lambda item: item.order)
        if requirement.requirement_id in facet_requirement_ids
    )


def _focus_for_stage_facets(
    plan: QuestionPlan,
    stage_facets: Sequence[Any],
) -> EvidenceObligationFocus:
    if not stage_facets:
        return EvidenceObligationFocus.CROSS_CUTTING
    requirement_order = {
        requirement.requirement_id: requirement.order
        for requirement in plan.requirements
    }
    facet_order = {
        facet.facet_id: index for index, facet in enumerate(plan.facets)
    }
    focus_facet = min(
        stage_facets,
        key=lambda facet: (
            min(
                (
                    requirement_order[requirement_id]
                    for requirement_id in facet.requirement_ids
                    if requirement_id in requirement_order
                ),
                default=len(requirement_order),
            ),
            facet_order[facet.facet_id],
        ),
    )
    return _OBLIGATION_FOCUS_BY_FACET_ROLE[focus_facet.role]


def _evidence_inspection_scopes(
    plan: QuestionPlan,
    final_chunks: Sequence[Mapping[str, object]],
    facet_source_numbers: Mapping[str, Sequence[int]],
) -> tuple[EvidenceInspectionScope, ...]:
    """List every retained broad-answer passage without requiring answer output."""

    if RouteTrait.BROAD_SYNTHESIS not in plan.traits or not final_chunks:
        return ()

    all_requirement_ids = tuple(
        requirement.requirement_id
        for requirement in sorted(plan.requirements, key=lambda item: item.order)
    )
    ranges_by_source = _bounded_inspection_ranges(final_chunks)
    scopes: list[EvidenceInspectionScope] = []
    for source_number, paragraph_ranges in enumerate(ranges_by_source, start=1):
        stage_facets = _stage_facets_for_source(
            plan,
            facet_source_numbers,
            source_number,
        )
        allowed_requirement_ids = (
            _ordered_facet_requirement_ids(plan, stage_facets)
            or all_requirement_ids
        )
        focus = _focus_for_stage_facets(plan, stage_facets)
        for paragraph_start, paragraph_end in paragraph_ranges:
            scopes.append(
                EvidenceInspectionScope(
                    inspection_id=f"I{len(scopes) + 1}",
                    source_number=source_number,
                    paragraph_start=paragraph_start,
                    paragraph_end=paragraph_end,
                    allowed_requirement_ids=allowed_requirement_ids,
                    focus=focus,
                )
            )
    return tuple(scopes)


def _evidence_obligation_scopes(
    plan: QuestionPlan,
    final_chunks: Sequence[Mapping[str, object]],
    stage_anchor_source_numbers: Mapping[str, int],
    transition_source_numbers: Mapping[tuple[str, str], int] | None = None,
) -> tuple[EvidenceObligationScope, ...]:
    """Require synthesis from protected stages and proven transition passages."""

    if RouteTrait.BROAD_SYNTHESIS not in plan.traits or not final_chunks:
        return ()

    transition_sources = transition_source_numbers or {}
    stage_records: list[
        tuple[
            int,
            str,
            int,
            tuple[str, ...],
            EvidenceObligationFocus,
            tuple[int, int],
        ]
    ] = []
    requirement_order = {
        requirement.requirement_id: requirement.order
        for requirement in plan.requirements
    }
    for facet in plan.facets:
        if facet.role not in _OBLIGATION_FOCUS_BY_FACET_ROLE:
            continue
        source_number = stage_anchor_source_numbers.get(facet.facet_id)
        if (
            not isinstance(source_number, int)
            or isinstance(source_number, bool)
            or not 1 <= source_number <= len(final_chunks)
        ):
            continue
        allowed_requirement_ids = _ordered_facet_requirement_ids(plan, (facet,))
        if not allowed_requirement_ids:
            continue
        stage_order = min(
            requirement_order[requirement_id]
            for requirement_id in allowed_requirement_ids
        )
        paragraph_ranges = _paragraph_scope_ranges(
            final_chunks[source_number - 1]
        )
        stage_records.append(
            (
                stage_order,
                facet.facet_id,
                source_number,
                allowed_requirement_ids,
                _OBLIGATION_FOCUS_BY_FACET_ROLE[facet.role],
                (paragraph_ranges[0][0], paragraph_ranges[-1][1]),
            )
        )
    stage_records.sort(key=lambda record: (record[0], record[2]))
    adjacent_stage_pairs = []
    for predecessor, current in zip(
        stage_records,
        stage_records[1:],
        strict=False,
    ):
        if current[0] != predecessor[0] + 1:
            continue
        transition_source_number = transition_sources.get(
            (predecessor[1], current[1])
        )
        if (
            not isinstance(transition_source_number, int)
            or isinstance(transition_source_number, bool)
            or not 1 <= transition_source_number <= len(final_chunks)
        ):
            continue
        transition_ranges = _paragraph_scope_ranges(
            final_chunks[transition_source_number - 1]
        )
        adjacent_stage_pairs.append(
            (
                predecessor,
                current,
                transition_source_number,
                (
                    transition_ranges[0][0],
                    transition_ranges[-1][1],
                ),
            )
        )

    capacity = MAX_ANSWER_UNITS - len(plan.premises)
    required_slots = len(stage_records) + len(adjacent_stage_pairs)
    if required_slots > capacity:
        raise ValueError(
            "answer-unit capacity cannot preserve stages and adjacent links"
        )

    long_lineage = (
        RouteTrait.LONG_INSTITUTIONAL_LINEAGE in plan.traits
    )
    selected_dimensions: list[list[EvidenceDimension]] = [
        (
            [EvidenceDimension.INSTITUTIONAL_HANDOFF]
            if long_lineage
            else [_OBLIGATION_DIMENSIONS_BY_FOCUS[focus][0]]
        )
        for (
            _stage_order,
            _facet_id,
            _source_number,
            _requirement_ids,
            focus,
            _paragraph_range,
        )
        in stage_records
    ]
    remaining_capacity = capacity - required_slots
    dimension_priority = (
        EvidenceDimension.MECHANISM,
        EvidenceDimension.CAUSE_OR_ENABLER,
        EvidenceDimension.STAGE_DEVELOPMENT,
        EvidenceDimension.CONSEQUENCE,
        EvidenceDimension.CONTINUITY_OR_CHANGE,
        EvidenceDimension.QUALIFICATION,
    )
    if not long_lineage:
        for dimension in dimension_priority:
            for index, (
                _stage_order,
                _facet_id,
                _source_number,
                _requirement_ids,
                focus,
                _paragraph_range,
            ) in enumerate(stage_records):
                if remaining_capacity <= 0:
                    break
                desired = _OBLIGATION_DIMENSIONS_BY_FOCUS[focus]
                if (
                    dimension not in desired
                    or dimension in selected_dimensions[index]
                ):
                    continue
                selected_dimensions[index].append(dimension)
                remaining_capacity -= 1
            if remaining_capacity <= 0:
                break

    scopes: list[EvidenceObligationScope] = []
    for index, (
        _stage_order,
        _facet_id,
        source_number,
        allowed_requirement_ids,
        focus,
        paragraph_range,
    ) in enumerate(stage_records):
        selected = set(selected_dimensions[index])
        dimension_ids = (
            (EvidenceDimension.INSTITUTIONAL_HANDOFF,)
            if long_lineage
            else tuple(
                dimension
                for dimension in _OBLIGATION_DIMENSIONS_BY_FOCUS[focus]
                if dimension in selected
            )
        )
        scopes.append(
            EvidenceObligationScope(
                obligation_id=f"O{len(scopes) + 1}",
                kind=EvidenceObligationKind.STAGE,
                source_number=source_number,
                paragraph_start=paragraph_range[0],
                paragraph_end=paragraph_range[1],
                allowed_requirement_ids=allowed_requirement_ids,
                focus=focus,
                dimension_ids=dimension_ids,
                required_for_requirement_status=True,
            )
        )
    for (
        predecessor,
        current,
        transition_source_number,
        transition_paragraph_range,
    ) in adjacent_stage_pairs:
        (
            _predecessor_order,
            _predecessor_facet_id,
            predecessor_source_number,
            predecessor_requirement_ids,
            _predecessor_focus,
            _predecessor_paragraph_range,
        ) = predecessor
        (
            _current_order,
            _current_facet_id,
            _current_source_number,
            current_requirement_ids,
            current_focus,
            _current_paragraph_range,
        ) = current
        scopes.append(
            EvidenceObligationScope(
                obligation_id=f"O{len(scopes) + 1}",
                kind=EvidenceObligationKind.ADJACENT_STAGE_LINK,
                source_number=transition_source_number,
                predecessor_source_number=predecessor_source_number,
                paragraph_start=transition_paragraph_range[0],
                paragraph_end=transition_paragraph_range[1],
                allowed_requirement_ids=(
                    predecessor_requirement_ids[0],
                    current_requirement_ids[0],
                ),
                focus=current_focus,
                dimension_ids=(EvidenceDimension.ADJACENT_STAGE_LINK,),
                required_for_requirement_status=True,
            )
        )
    return tuple(scopes)


def build_coverage_input(
    resolved_turn: ResolvedTurn,
    plan: QuestionPlan,
    final_chunks: list[dict[str, Any]],
    facet_source_numbers: Mapping[str, Sequence[int]],
    premise_source_scopes: Sequence[PremiseSourceScope],
    inspection_scopes: Sequence[EvidenceInspectionScope],
    obligation_scopes: Sequence[EvidenceObligationScope],
    gate: EvidenceGateResult,
    *,
    historiographical_lens: HistoriographicalLens | str,
    voice: AnswerVoice | str,
    worldview: Worldview | str,
) -> str:
    requirement_sources = _requirement_source_map(plan, facet_source_numbers)
    requirement_by_id = {
        requirement.requirement_id: requirement
        for requirement in plan.requirements
    }
    premise_by_id = {premise.premise_id: premise for premise in plan.premises}
    premise_sources = [
        {
            "premise_id": scope.premise_id,
            "proposition": premise_by_id[scope.premise_id].proposition,
            "support_candidate_sources": list(scope.support_source_numbers),
            "counter_candidate_sources": list(scope.counter_source_numbers),
            "framing_candidate_sources": list(scope.framing_source_numbers),
        }
        for scope in premise_source_scopes
    ]
    required_interpretive_moves = _required_interpretive_moves(
        historiographical_lens,
        worldview,
    )
    required_question_anchors = _interpretive_question_anchors(
        resolved_turn,
        plan,
    )
    synthesis_obligations: list[dict[str, Any]] = []
    for scope in obligation_scopes:
        obligation_payload: dict[str, Any] = {
            "obligation_id": scope.obligation_id,
            "kind": scope.kind.value,
            "source_number": scope.source_number,
            "predecessor_source_number": scope.predecessor_source_number,
            "paragraph_start": scope.paragraph_start,
            "paragraph_end": scope.paragraph_end,
            "allowed_requirement_ids": list(
                scope.allowed_requirement_ids
            ),
            "focus": scope.focus.value,
            "dimension_ids": [
                dimension.value for dimension in scope.dimension_ids
            ],
            "required_for_requirement_status": (
                scope.required_for_requirement_status
            ),
        }
        if (
            EvidenceDimension.INSTITUTIONAL_HANDOFF
            in scope.dimension_ids
            and len(scope.allowed_requirement_ids) == 1
        ):
            requirement = requirement_by_id[
                scope.allowed_requirement_ids[0]
            ]
            handoff = requirement.institutional_handoff
            if handoff is not None:
                obligation_payload["orientation_only"] = {
                    "bearer": handoff.bearer,
                    "inherited_capacity": handoff.inherited_capacity,
                    "transfer_mechanism": handoff.transfer_mechanism,
                    "outgoing_capacity": handoff.outgoing_capacity,
                    "evidence_status": (
                        "planner search orientation only; verify every field "
                        "against the scoped manuscript source"
                    ),
                }
        synthesis_obligations.append(obligation_payload)

    control = {
        "schema": "archivist.answer_request/6",
        "question": resolved_turn.standalone_question,
        "conversation_context": {
            "entities": list(resolved_turn.entities),
            "scope": resolved_turn.scope,
            "corrections": list(resolved_turn.corrections),
            "relationship": resolved_turn.relationship,
            "note": (
                "These fields resolve user intent only. Prior assistant answers are not evidence."
            ),
        },
        "requirements": [
            {
                "requirement_id": requirement.requirement_id,
                "label": requirement.label,
                "order": requirement.order,
                "required": requirement.required,
                "candidate_source_numbers": list(requirement_sources[requirement.requirement_id]),
            }
            for requirement in plan.requirements
        ],
        "premises": premise_sources,
        "inspection_passages": [
            {
                "inspection_id": scope.inspection_id,
                "source_number": scope.source_number,
                "paragraph_start": scope.paragraph_start,
                "paragraph_end": scope.paragraph_end,
                "allowed_requirement_ids": list(scope.allowed_requirement_ids),
                "focus": scope.focus.value,
            }
            for scope in inspection_scopes
        ],
        "synthesis_obligations": synthesis_obligations,
        "evidence_boundary": {
            "decision": gate.decision.value,
            "certified_direct_absence": gate.certified_direct_absence,
            "rules_fired": list(gate.rules_fired),
        },
    }
    if required_interpretive_moves:
        control["interpretive_frame"] = {
            "required_moves": [
                move.value for move in required_interpretive_moves
            ],
            "required_question_anchors": list(required_question_anchors),
            "preface_sentence_count": "2-3",
            "coda_sentence_count": 1,
            "citations": "forbidden",
            "historical_facts": "factual answer only",
            "first_person": "forbidden",
            "reader_presentation": "one cohesive answer with no section labels",
        }
    style = build_interpretive_prompt_block(
        historiographical_lens,
        voice,
        worldview,
    )
    interpretive_expansion = bool(required_interpretive_moves)
    sections = [
        "Request contract:\n" + json.dumps(control, ensure_ascii=False, indent=2),
        "Numbered manuscript sources:\n" + build_context(final_chunks),
    ]
    if style:
        sections.append(
            "Interpretive presentation (never alter factual coverage or sources):\n"
            + style
            + (
                "\n"
                + INTERPRETIVE_STRUCTURED_OUTPUT_RULES
                if interpretive_expansion
                else ""
            )
            + "\nDo not add an uncited invitation or follow-up question outside the schema."
        )
    return "\n\n".join(sections)


def _response_refused(response: object) -> bool:
    for output in getattr(response, "output", ()) or ():
        for content in getattr(output, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return True
    return False


def _clean_abstention(target_label: str | None) -> str:
    subject = f" “{target_label}”" if target_label else ""
    return (
        f"I could not find a direct mention of{subject} in the searchable manuscript, "
        "so I cannot describe the book as treating it. I will not substitute material "
        "about a similar subject."
    )


def _deterministic_structural_stage_shortfall_count(
    resolved_turn: ResolvedTurn,
    plan: QuestionPlan,
    planned: PlannedContext,
) -> int:
    """Return the recorded exact-core shortfall for the six-stage fallback."""

    if (
        plan.planner_used
        or RouteTrait.BROAD_SYNTHESIS not in plan.traits
        or RouteTrait.LONG_INSTITUTIONAL_LINEAGE in plan.traits
        or not requires_broad_narrative_span(resolved_turn)
    ):
        return 0
    selection = planned.trace.get("selection")
    if not isinstance(selection, Mapping):
        return 0
    required_count = selection.get("canonical_core_required_count")
    shortfall_count = selection.get("canonical_core_shortfall_count")
    if (
        required_count != BROAD_NARRATIVE_SPAN_STAGE_REQUIREMENTS
        or not isinstance(shortfall_count, int)
        or isinstance(shortfall_count, bool)
    ):
        return 0
    return max(0, shortfall_count)


def _generation_trace(
    coverage: EvidenceCoverageResult | None,
    *,
    status: str,
    inspection_scopes: Sequence[EvidenceInspectionScope] = (),
    style_prompt_sha256: str | None = None,
    response_format: type[EvidenceCoverageAnswer] = EvidenceCoverageAnswer,
    structured_generation_called: bool | None = None,
) -> dict[str, Any]:
    contract = {
        "prompt_version": EVIDENCE_COVERAGE_PROMPT_VERSION,
        "request_schema": "archivist.answer_request/6",
        "instructions_sha256": hashlib.sha256(
            EVIDENCE_COVERAGE_INSTRUCTIONS.encode("utf-8")
        ).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(
                response_format.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "generator_model": GENERATOR_SETTINGS.model,
        "generator_reasoning_effort": GENERATOR_SETTINGS.reasoning_effort,
        "generator_verbosity": GENERATOR_SETTINGS.verbosity,
        "normalizer_version": EVIDENCE_COVERAGE_NORMALIZER_VERSION,
        "style_prompt_sha256": style_prompt_sha256,
        "inspection_scope_count": len(inspection_scopes),
        "inspection_scopes": [
            {
                "inspection_id": scope.inspection_id,
                "source_number": scope.source_number,
                "paragraph_start": scope.paragraph_start,
                "paragraph_end": scope.paragraph_end,
                "allowed_requirement_ids": list(scope.allowed_requirement_ids),
                "focus": scope.focus.value,
            }
            for scope in inspection_scopes
        ],
    }
    if coverage is None:
        return {
            **contract,
            "status": status,
            "structured_generation_called": bool(structured_generation_called),
        }
    diagnostics = coverage.diagnostics.model_dump(mode="json", by_alias=True)
    return {
        **contract,
        "status": coverage.status.value,
        "structured_generation_called": (
            True
            if structured_generation_called is None
            else structured_generation_called
        ),
        **diagnostics,
    }


def run_evidence_planned_answer(
    *,
    resolved_turn: ResolvedTurn,
    collection_handle: object,
    chunks: list[dict[str, Any]],
    client: object,
    n_results: int = 5,
    corpus_trace: Mapping[str, Any] | None = None,
    corpus_manifest: Mapping[str, object] | None = None,
    corpus_manifest_sha256: str | None = None,
    corpus_integrity: CorpusIntegrity | None = None,
    require_store_identity: bool = False,
    historiographical_lens: HistoriographicalLens | str = (HistoriographicalLens.EVIDENCE_FIRST),
    voice: AnswerVoice | str = AnswerVoice.SCHOLARLY,
    worldview: Worldview | str = Worldview.NONE,
    policy: RagPolicy = EVIDENCE_PLANNED_POLICY,
) -> AnswerModeResult:
    """Execute one bounded evidence-planned Answer Mode turn."""
    pipeline_started_ns = perf_counter_ns()
    stage_timings_ms: dict[str, float] = {}
    planner_call_diagnostics: dict[str, Any] = _planner_call_diagnostic("not_called")

    def result_diagnostics(
        evidence: Mapping[str, Any],
        generation: Mapping[str, Any],
    ) -> dict[str, Any]:
        stage_timings_ms["pipeline_total"] = _elapsed_ms(pipeline_started_ns)
        return {
            "rag_policy_version": policy.version,
            "evidence": dict(evidence),
            "generation": dict(generation),
            "planner": dict(planner_call_diagnostics),
            "stage_timings_ms": dict(stage_timings_ms),
        }

    integrity_started_ns = perf_counter_ns()
    eligible_chunks = [
        chunk for chunk in chunks if not should_skip_document(str(chunk.get("document") or ""))
    ]
    collection_count = int(collection_handle.count())
    integrity = corpus_integrity or preflight_answer_corpus(
        collection_handle=collection_handle,
        chunks=eligible_chunks,
        corpus_manifest=corpus_manifest,
        corpus_manifest_sha256=corpus_manifest_sha256,
        require_store_identity=require_store_identity,
    )
    stage_timings_ms["corpus_integrity"] = _elapsed_ms(integrity_started_ns)
    if not integrity.passed:
        plan = build_question_plan(
            resolved_turn,
            fallback_reason="corpus_integrity_failed",
        )
        diagnostics = {
            "rag_policy_version": policy.version,
            "evidence": {
                "schema": "archivist.evidence_policy_diagnostics/1",
                "corpus": integrity.as_diagnostics(),
                "decision": {
                    "value": EvidenceDecision.INDETERMINATE.value,
                    "rules_fired": ["corpus_integrity_failed"],
                },
            },
            "generation": _generation_trace(
                None,
                status="corpus_integrity_failed",
            ),
            "planner": dict(planner_call_diagnostics),
        }
        return AnswerModeResult(
            answer=CORPUS_INTEGRITY_FAILED_MESSAGE,
            final_chunks=[],
            status="corpus_integrity_failed",
            plan=plan,
            evidence_decision=EvidenceDecision.INDETERMINATE.value,
            diagnostics={
                **diagnostics,
                "stage_timings_ms": {
                    **stage_timings_ms,
                    "pipeline_total": _elapsed_ms(pipeline_started_ns),
                },
            },
        )

    catalog = build_document_catalog(eligible_chunks)
    request_client = without_automatic_retries(client)
    planning_started_ns = perf_counter_ns()
    plan = plan_question(
        request_client,
        resolved_turn,
        catalog,
        policy=policy,
        planner_diagnostics=planner_call_diagnostics,
    )
    stage_timings_ms["query_planning"] = _elapsed_ms(planning_started_ns)
    retrieval_started_ns = perf_counter_ns()
    planned = retrieve_plan_from_collection(
        plan,
        collection_handle,
        eligible_chunks,
        n_results=n_results,
        embedding_client=request_client,
        corpus=corpus_trace,
        max_final_sources=MAX_FINAL_SOURCES,
    )
    stage_timings_ms["retrieval"] = _elapsed_ms(retrieval_started_ns)
    planned.trace["plan"].update(
        {
            "policy_version": policy.version,
            "planner_prompt_version": QUERY_PLANNER_PROMPT_VERSION,
            "document_role_profile_version": DOCUMENT_ROLE_PROFILE_VERSION,
            "planner_prompt_sha256": hashlib.sha256(
                (QUERY_PLANNER_INSTRUCTIONS + "\n" + QUERY_PLANNER_ADDITIONAL_INSTRUCTIONS).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "planner_schema_sha256": hashlib.sha256(
                json.dumps(
                    PlannerQuestionPlan.model_json_schema(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "planner_model": QUERY_PLANNER_SETTINGS.model,
            "planner_reasoning_effort": QUERY_PLANNER_SETTINGS.reasoning_effort,
            "planner_verbosity": QUERY_PLANNER_SETTINGS.verbosity,
            "planner_call": _planner_trace_diagnostic(planner_call_diagnostics),
        }
    )
    structural_stage_shortfall_count = (
        _deterministic_structural_stage_shortfall_count(
            resolved_turn,
            plan,
            planned,
        )
    )
    if structural_stage_shortfall_count:
        requirement_ids = tuple(
            requirement.requirement_id
            for requirement in plan.requirements
        )
        coverage = process_evidence_coverage(
            None,
            requirement_ids=requirement_ids,
            source_count=0,
        )
        gate_diagnostics = {
            "schema": EVIDENCE_DIAGNOSTICS_SCHEMA,
            "policy_version": EVIDENCE_POLICY_VERSION,
            "corpus": integrity.as_diagnostics(),
            "targets": [],
            "decision": {
                "value": EvidenceDecision.INDETERMINATE.value,
                "certified_direct_absence": False,
                "premise_correction_required": False,
                "relationship_chunk_ids": [],
                "allowed_source_numbers": [],
                "suppressed_source_numbers": list(
                    range(1, len(planned.final_chunks) + 1)
                ),
                "skip_answer_generation": True,
                "rules_fired": ["structural_stage_shortfall"],
            },
        }
        generation_diagnostics = _generation_trace(
            coverage,
            status=coverage.status.value,
            structured_generation_called=False,
        )
        planned.trace["evidence"] = gate_diagnostics
        planned.trace["generation_contract"] = generation_diagnostics
        emit_retrieval_trace(planned.trace)
        return AnswerModeResult(
            answer=STRUCTURAL_STAGE_SHORTFALL_MESSAGE,
            final_chunks=[],
            status=coverage.status.value,
            plan=plan,
            evidence_decision=EvidenceDecision.INDETERMINATE.value,
            diagnostics=result_diagnostics(
                gate_diagnostics,
                generation_diagnostics,
            ),
        )
    gate_started_ns = perf_counter_ns()
    gate, gate_diagnostics, target_label = apply_evidence_gate(
        plan,
        planned,
        eligible_chunks,
        trusted_user_texts=resolved_turn.trusted_user_texts,
        collection_count=collection_count,
        corpus_manifest=corpus_manifest,
        corpus_manifest_sha256=corpus_manifest_sha256,
        corpus_integrity=integrity,
        policy=policy,
    )
    stage_timings_ms["evidence_gate"] = _elapsed_ms(gate_started_ns)
    planned.trace["evidence"] = gate_diagnostics

    if gate.skip_answer_generation:
        answer = _clean_abstention(target_label)
        planned.trace["generation_contract"] = _generation_trace(
            None,
            status="clean_abstention",
        )
        emit_retrieval_trace(planned.trace)
        return AnswerModeResult(
            answer=answer,
            final_chunks=[],
            status="clean_abstention",
            plan=plan,
            evidence_decision=gate.decision.value,
            diagnostics=result_diagnostics(
                gate_diagnostics,
                planned.trace["generation_contract"],
            ),
        )

    context_started_ns = perf_counter_ns()
    (
        final_chunks,
        old_to_new,
        remapped_facets,
        remapped_stage_anchors,
        remapped_transition_sources,
    ) = _filter_context(
        planned,
        gate.allowed_source_numbers,
    )
    _record_generation_context(planned, final_chunks, old_to_new)
    requirement_ids = tuple(requirement.requirement_id for requirement in plan.requirements)
    premise_ids = tuple(premise.premise_id for premise in plan.premises)
    requirement_labels = {
        requirement.requirement_id: requirement.label for requirement in plan.requirements
    }
    premise_source_scopes = _premise_source_scopes(plan, remapped_facets)
    inspection_scopes = _evidence_inspection_scopes(
        plan,
        final_chunks,
        remapped_facets,
    )
    obligation_scopes = (
        _evidence_obligation_scopes(
            plan,
            final_chunks,
            remapped_stage_anchors,
            remapped_transition_sources,
        )
        if RouteTrait.BROAD_SYNTHESIS in plan.traits
        else _focused_requirement_component_scopes(
            plan,
            final_chunks,
            remapped_facets,
        )
    )
    stage_timings_ms["context_preparation"] = _elapsed_ms(context_started_ns)

    if not final_chunks:
        validation_started_ns = perf_counter_ns()
        coverage = process_evidence_coverage(
            None,
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=premise_source_scopes,
            obligation_scopes=obligation_scopes,
            source_count=0,
            requirement_labels=requirement_labels,
        )
        stage_timings_ms["answer_validation"] = _elapsed_ms(validation_started_ns)
        planned.trace["generation_contract"] = _generation_trace(
            coverage,
            status="insufficient_evidence",
            inspection_scopes=inspection_scopes,
        )
        emit_retrieval_trace(planned.trace)
        return AnswerModeResult(
            answer=coverage.answer,
            final_chunks=[],
            status=coverage.status.value,
            plan=plan,
            evidence_decision=gate.decision.value,
            diagnostics=result_diagnostics(
                gate_diagnostics,
                planned.trace["generation_contract"],
            ),
        )

    style_block = build_interpretive_prompt_block(
        historiographical_lens,
        voice,
        worldview,
    )
    required_interpretive_moves = _required_interpretive_moves(
        historiographical_lens,
        worldview,
    )
    required_question_anchors = _interpretive_question_anchors(
        resolved_turn,
        plan,
    )
    interpretive_expansion = bool(required_interpretive_moves)
    response_format = (
        InterpretiveEvidenceCoverageAnswer
        if interpretive_expansion
        else EvidenceCoverageAnswer
    )
    style_prompt_sha256 = (
        hashlib.sha256(style_block.encode("utf-8")).hexdigest() if style_block else None
    )
    context_validation_started_ns = perf_counter_ns()
    try:
        validate_evidence_coverage_context(
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=premise_source_scopes,
            obligation_scopes=obligation_scopes,
            source_count=len(final_chunks),
        )
    except CoverageContractError:
        coverage = process_evidence_coverage(
            None,
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=premise_source_scopes,
            obligation_scopes=obligation_scopes,
            source_count=len(final_chunks),
            requirement_labels=requirement_labels,
        )
        stage_timings_ms["answer_validation"] = _elapsed_ms(
            context_validation_started_ns
        )
        planned.trace["generation_contract"] = _generation_trace(
            coverage,
            status=coverage.status.value,
            inspection_scopes=inspection_scopes,
            style_prompt_sha256=style_prompt_sha256,
            response_format=response_format,
            structured_generation_called=False,
        )
        emit_retrieval_trace(planned.trace)
        return AnswerModeResult(
            answer=coverage.answer,
            final_chunks=final_chunks,
            status=coverage.status.value,
            plan=plan,
            evidence_decision=gate.decision.value,
            diagnostics=result_diagnostics(
                gate_diagnostics,
                planned.trace["generation_contract"],
            ),
        )
    context_validation_ms = _elapsed_ms(context_validation_started_ns)

    coverage_input = build_coverage_input(
        resolved_turn,
        plan,
        final_chunks,
        remapped_facets,
        premise_source_scopes,
        inspection_scopes,
        obligation_scopes,
        gate,
        historiographical_lens=historiographical_lens,
        voice=voice,
        worldview=worldview,
    )
    generation_started_ns = perf_counter_ns()
    try:
        response = tracked_responses_parse(
            request_client,
            operation="answer_generation",
            instructions=EVIDENCE_COVERAGE_INSTRUCTIONS,
            input=coverage_input,
            text_format=response_format,
            max_output_tokens=MAX_COVERAGE_OUTPUT_TOKENS,
            **GENERATOR_SETTINGS.responses_create_kwargs(),
        )
        parsed = getattr(response, "output_parsed", None)
        refused = _response_refused(response)
    except CostLimitExceeded:
        raise
    except Exception:
        parsed = None
        refused = True
    stage_timings_ms["answer_generation"] = _elapsed_ms(generation_started_ns)

    validation_started_ns = perf_counter_ns()
    if interpretive_expansion:
        coverage = process_interpretive_evidence_coverage(
            parsed,
            required_moves=required_interpretive_moves,
            question_anchors=required_question_anchors,
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=premise_source_scopes,
            obligation_scopes=obligation_scopes,
            source_count=len(final_chunks),
            requirement_labels=requirement_labels,
            refused=refused,
        )
    else:
        coverage = process_evidence_coverage(
            parsed,
            requirement_ids=requirement_ids,
            premise_ids=premise_ids,
            premise_source_scopes=premise_source_scopes,
            obligation_scopes=obligation_scopes,
            source_count=len(final_chunks),
            requirement_labels=requirement_labels,
            refused=refused,
        )
    stage_timings_ms["answer_validation"] = round(
        context_validation_ms + _elapsed_ms(validation_started_ns),
        3,
    )
    planned.trace["generation_contract"] = _generation_trace(
        coverage,
        status=coverage.status.value,
        inspection_scopes=inspection_scopes,
        style_prompt_sha256=style_prompt_sha256,
        response_format=response_format,
    )
    emit_retrieval_trace(planned.trace)
    return AnswerModeResult(
        answer=coverage.answer,
        final_chunks=final_chunks,
        status=coverage.status.value,
        plan=plan,
        evidence_decision=gate.decision.value,
        diagnostics=result_diagnostics(
            gate_diagnostics,
            planned.trace["generation_contract"],
        ),
    )


__all__ = [
    "AnswerModeResult",
    "EVIDENCE_PLANNED_POLICY",
    "EVIDENCE_COVERAGE_INSTRUCTIONS",
    "RAG_POLICY_VERSION",
    "RagPolicy",
    "answer_run_diagnostics",
    "apply_evidence_gate",
    "assess_answer_corpus_integrity",
    "build_coverage_input",
    "build_document_catalog",
    "build_planner_input",
    "plan_question",
    "preflight_answer_corpus",
    "run_evidence_planned_answer",
    "without_automatic_retries",
]
