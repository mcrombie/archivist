"""Closed, text-free schema for private retrieval diagnostics.

Retrieval traces may contain corpus identifiers, hashes, ranks, counts, and
bounded enum-like diagnostics.  They may never become an accidental side
channel for manuscript, prompt, question, or answer prose.  Keep this contract
shared by trace persistence and evaluation-artifact validation so a trace
cannot be certified under weaker rules than the writer applies.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from datetime import datetime


RETRIEVAL_TRACE_SCHEMA = "archivist.retrieval_trace/12"

_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "chunk",
        "content",
        "excerpt",
        "manuscript_text",
        "metadata",
        "metadatas",
        "passage",
        "prompt",
        "question",
        "raw_query",
        "response",
        "text",
    }
)

_CHUNK_FIELDS = frozenset(
    {
        "chunk_id",
        "document_sha256",
        "paragraph_end",
        "paragraph_start",
    }
)
_CANDIDATE_FIELDS = _CHUNK_FIELDS | frozenset(
    {
        "bigram_hits",
        "bm25_score",
        "distance",
        "lexical_rank",
        "lexical_rrf",
        "matched_term_count",
        "quoted_phrase_hits",
        "rank",
        "retrieval_eligible",
        "rrf_score",
        "selected_primary",
        "semantic_contributed",
        "semantic_distance",
        "semantic_rank",
        "semantic_rrf",
        "within_distance_threshold",
    }
)
_CONTEXT_FIELDS = _CHUNK_FIELDS | frozenset(
    {
        "facet_ids",
        "fused_rank",
        "document_ordinal",
        "origin",
        "parent_primary_chunk_ids",
        "retrieval_source_number",
        "source_number",
    }
)

_OBJECT_FIELDS: dict[tuple[str, ...], frozenset[str]] = {
    (): frozenset(
        {
            "candidates",
            "corpus",
            "created_at",
            "evidence",
            "generation_contract",
            "lanes",
            "parameters",
            "plan",
            "query",
            "retrieval_version",
            "schema",
            "scope",
            "selection",
            "trace_id",
        }
    ),
    ("query",): frozenset(
        {
            "char_count",
            "mode",
            "query_term_count",
            "query_terms_with_zero_document_frequency",
            "quoted_phrase_count",
            "sha256",
        }
    ),
    ("corpus",): frozenset(
        {
            "chunks_sha256",
            "collection_count",
            "collection_name",
            "corpus_manifest_sha256",
            "hnsw_space",
            "project_id",
        }
    ),
    ("parameters",): frozenset(
        {
            "bm25_b",
            "bm25_k1",
            "broad_execution_version",
            "broad_mechanism_candidate_limit",
            "broad_mechanism_lexical_version",
            "broad_transition_lane_version",
            "broad_context_order",
            "diversity_min_score_ratio",
            "facet_embedding",
            "final_context_source_limit",
            "finalizer_max_primary_distance",
            "lane_primary_limit",
            "lane_selection",
            "lexical_candidate_count",
            "lexical_candidate_limit",
            "lexical_coverage_multiplier",
            "lexical_scoring_version",
            "lexical_weight",
            "lineage_stage_contract_version",
            "lineage_transition_capacity_policy",
            "max_primary_per_document",
            "neighbor_expansion",
            "premise_lane_reservation",
            "primary_limit",
            "query_bigram_bonus",
            "quoted_phrase_bonus",
            "rrf_k",
            "semantic_candidate_count",
            "semantic_candidate_limit",
            "semantic_distance_threshold",
            "semantic_fallback_allowed",
            "semantic_weight",
            "stopword_sha256",
            "tie_break",
            "tokenizer_version",
        }
    ),
    ("candidates",): frozenset({"fused", "lexical", "semantic"}),
    ("candidates", "semantic", "[]"): _CANDIDATE_FIELDS,
    ("candidates", "lexical", "[]"): _CANDIDATE_FIELDS,
    ("candidates", "fused", "[]"): _CANDIDATE_FIELDS,
    ("selection",): frozenset(
        {
            "anchor_deferred_count",
            "anchor_requested_count",
            "anchor_source_number_remap",
            "canonical_core_required_count",
            "canonical_core_satisfied_count",
            "canonical_core_shortfall_count",
            "context",
            "discarded",
            "diversity_applied",
            "diversity_deferred_chunk_ids",
            "document_distribution",
            "fusion_pool_fallback_used",
            "generation_context",
            "pre_anchor_context",
            "primary_chunk_ids",
            "protected_source_count",
            "protected_source_shortfall_count",
            "raw_primary_fallback_detected",
            "raw_primary_fallback_used",
            "retrieval_context",
            "source_number_remap",
            "stage_coverage_required_count",
            "stage_coverage_satisfied_count",
            "stage_coverage_shortfall_count",
            "stage_capacity_shortfall_count",
            "transition_candidate_shortfall_count",
            "transition_capacity_limited_count",
            "transition_coverage_required_count",
            "transition_coverage_satisfied_count",
            "transition_coverage_shortfall_count",
            "transition_extra_source_capacity_count",
            "transition_new_source_satisfied_count",
            "transition_reuse_satisfied_count",
            "transition_selection_shortfall_count",
        }
    ),
    ("selection", "discarded", "[]"): _CHUNK_FIELDS
    | frozenset({"displacement_cause", "reason", "stage"}),
    ("selection", "document_distribution"): frozenset(
        {"context", "lexical", "selected_primary", "semantic"}
    ),
    ("selection", "context", "[]"): _CONTEXT_FIELDS,
    ("selection", "pre_anchor_context", "[]"): _CONTEXT_FIELDS,
    ("selection", "retrieval_context", "[]"): _CONTEXT_FIELDS,
    ("selection", "generation_context", "[]"): _CONTEXT_FIELDS,
    ("selection", "source_number_remap", "[]"): frozenset(
        {"generation_source_number", "retrieval_source_number"}
    ),
    ("selection", "anchor_source_number_remap", "[]"): frozenset(
        {"post_anchor_source_number", "pre_anchor_source_number"}
    ),
    ("scope",): frozenset({"conversation_id", "project_id", "turn_id"}),
    ("plan",): frozenset(
        {
            "anchor_promoted_count",
            "facet_count",
            "fallback_reason",
            "planner_call",
            "document_role_profile_version",
            "planner_model",
            "planner_prompt_sha256",
            "planner_prompt_version",
            "planner_reasoning_effort",
            "planner_schema_sha256",
            "planner_used",
            "planner_verbosity",
            "policy_version",
            "requirement_count",
            "schema",
            "traits",
            "lineage_stage_planned_count",
            "lineage_stage_required_count",
            "lineage_stage_source_capacity_count",
        }
    ),
    ("plan", "planner_call"): frozenset(
        {
            "exception_class_sha256",
            "exception_code",
            "failure_code",
            "planner_validation_code",
            "schema",
            "status",
        }
    ),
    ("lanes", "[]"): frozenset(
        {
            "candidate_chunk_ids",
            "canonical_candidate_chunk_ids",
            "canonical_core_selected_chunk_ids",
            "canonical_query_char_count",
            "canonical_query_sha256",
            "chronology_band",
            "chronology_max_document_ordinal",
            "chronology_min_document_ordinal",
            "document_hint_sha256s",
            "facet_id",
            "mechanism_candidate_chunk_ids",
            "mechanism_query_char_counts",
            "mechanism_query_sha256s",
            "provider_query_char_count",
            "provider_query_sha256",
            "query_char_count",
            "query_sha256",
            "raw_primary_fallback_detected",
            "role",
            "selected_chunk_ids",
            "semantic_fallback_used",
            "stage_anchor_consensus_candidates",
            "stage_anchor_selected_chunk_ids",
            "stage_distinctive_intent_term_count",
            "stage_intent_query_char_count",
            "stage_intent_query_sha256",
            "stage_intent_term_count",
            "stage_required_distinctive_intent_match_count",
            "transition_candidate_chunk_ids",
            "transition_candidates",
            "transition_document_scope_sha256s",
            "transition_id",
            "transition_predecessor_facet_id",
            "transition_query_char_count",
            "transition_query_sha256",
            "transition_selected_chunk_ids",
        }
    ),
    ("lanes", "[]", "stage_anchor_consensus_candidates", "[]"): frozenset(
        {
            "chunk_id",
            "distinctive_intent_match_count",
            "eligibility",
            "eligible",
            "intent_match_count",
            "pool_hit_count",
            "pool_names",
            "pool_ranks",
            "required_distinctive_intent_match_count",
            "role_signal_score",
        }
    ),
    (
        "lanes",
        "[]",
        "stage_anchor_consensus_candidates",
        "[]",
        "pool_ranks",
    ): frozenset({"canonical", "mechanism", "provider"}),
    ("lanes", "[]", "transition_candidates", "[]"): frozenset(
        {
            "chunk_id",
            "eligibility",
            "eligible",
            "predecessor_intent_match_count",
            "successor_intent_match_count",
            "transition_signal_score",
        }
    ),
    ("evidence",): frozenset(
        {
            "anchor_normalizer_version",
            "broader_related",
            "corpus",
            "decision",
            "lanes",
            "policy_version",
            "schema",
            "targets",
            "weak_match_window_tokens",
        }
    ),
    ("evidence", "corpus"): frozenset(
        {
            "collection_count",
            "expected_collection_count",
            "expected_eligible_chunk_count",
            "expected_manifest_sha256",
            "failure_codes",
            "loaded_eligible_chunk_count",
            "loaded_eligible_chunk_ids_sha256",
            "loaded_manifest_sha256",
            "manifest_eligible_chunk_ids_sha256",
            "passed",
        }
    ),
    ("evidence", "targets", "[]"): frozenset(
        {
            "absence_checkable",
            "anchor_token_count",
            "certified_direct_absence",
            "mechanical_initialism_hit_count",
            "partial_token_collision_count",
            "role",
            "scanned_chunk_count",
            "strong_hit_count",
            "target_character_count",
            "target_id",
            "target_sha256",
            "weak_hit_count",
        }
    ),
    ("evidence", "broader_related"): frozenset(
        {
            "broader_strong_hit_count",
            "broader_target_sha256",
            "qualified_broader_hit_count",
            "qualifying_pair_count",
            "related_probe_sha256",
            "scanned_chunk_ids_sha256",
            "supporting_probe_chunk_count",
        }
    ),
    ("evidence", "lanes", "[]"): frozenset({"chunk_id", "lane", "source_number"}),
    ("evidence", "decision"): frozenset(
        {
            "allowed_source_numbers",
            "certified_direct_absence",
            "premise_correction_required",
            "relationship_chunk_ids",
            "rules_fired",
            "skip_answer_generation",
            "suppressed_source_numbers",
            "value",
        }
    ),
    ("generation_contract",): frozenset(
        {
            "answer_unit_count",
            "answer_units",
            "citation_count",
            "citation_locality_failure",
            "coverage",
            "coverage_status_counts",
            "error_code",
            "generator_model",
            "generator_reasoning_effort",
            "generator_verbosity",
            "instructions_sha256",
            "inspection_scope_count",
            "inspection_scopes",
            "normalizer_version",
            "obligation_count",
            "obligation_coverage",
            "obligation_scopes",
            "premise_count",
            "premise_decisions",
            "premise_ids",
            "premise_source_scopes",
            "premise_status_counts",
            "prompt_version",
            "request_schema",
            "renderer_version",
            "repair_applied",
            "repair_codes",
            "requirement_count",
            "requirement_ids",
            "schema",
            "schema_sha256",
            "source_count",
            "status",
            "structured_generation_called",
            "style_prompt_sha256",
            "validation_result",
        }
    ),
    ("generation_contract", "coverage_status_counts"): frozenset(
        {"conflicting", "partial", "supported", "unsupported"}
    ),
    ("generation_contract", "premise_status_counts"): frozenset(
        {"contradicted", "not_applicable", "supported", "unresolved"}
    ),
    ("generation_contract", "inspection_scopes", "[]"): frozenset(
        {
            "allowed_requirement_ids",
            "focus",
            "inspection_id",
            "paragraph_end",
            "paragraph_start",
            "source_number",
        }
    ),
    ("generation_contract", "coverage", "[]"): frozenset(
        {
            "gap_reason",
            "requirement_id",
            "source_numbers",
            "status",
            "unit_ids",
        }
    ),
    ("generation_contract", "premise_decisions", "[]"): frozenset(
        {
            "correction_unit_id",
            "premise_id",
            "source_numbers",
            "status",
        }
    ),
    ("generation_contract", "premise_source_scopes", "[]"): frozenset(
        {
            "counter_source_numbers",
            "framing_source_numbers",
            "premise_id",
            "support_source_numbers",
        }
    ),
    ("generation_contract", "citation_locality_failure"): frozenset(
        {
            "code",
            "unit_id",
            "unit_ordinal",
        }
    ),
    ("generation_contract", "obligation_scopes", "[]"): frozenset(
        {
            "allowed_requirement_ids",
            "dimension_ids",
            "focus",
            "kind",
            "obligation_id",
            "paragraph_end",
            "paragraph_start",
            "predecessor_source_number",
            "required_for_requirement_status",
            "source_number",
        }
    ),
    ("generation_contract", "obligation_coverage", "[]"): frozenset(
        {
            "dimensions",
            "obligation_id",
        }
    ),
    (
        "generation_contract",
        "obligation_coverage",
        "[]",
        "dimensions",
        "[]",
    ): frozenset(
        {
            "dimension",
            "gap_reason",
            "source_numbers",
            "status",
            "unit_ids",
        }
    ),
    ("generation_contract", "answer_units", "[]"): frozenset(
        {
            "obligation_links",
            "paragraph",
            "requirement_ids",
            "role",
            "source_numbers",
            "unit_id",
        }
    ),
    (
        "generation_contract",
        "answer_units",
        "[]",
        "obligation_links",
        "[]",
    ): frozenset(
        {
            "dimension",
            "obligation_id",
        }
    ),
}

_DOCUMENT_DISTRIBUTION_PATHS = frozenset(
    {
        ("selection", "document_distribution", "context"),
        ("selection", "document_distribution", "lexical"),
        ("selection", "document_distribution", "selected_primary"),
        ("selection", "document_distribution", "semantic"),
    }
)

_ARRAY_PATHS = frozenset(
    {
        ("candidates", "fused"),
        ("candidates", "lexical"),
        ("candidates", "semantic"),
        ("evidence", "corpus", "failure_codes"),
        ("evidence", "decision", "allowed_source_numbers"),
        ("evidence", "decision", "relationship_chunk_ids"),
        ("evidence", "decision", "rules_fired"),
        ("evidence", "decision", "suppressed_source_numbers"),
        ("evidence", "lanes"),
        ("evidence", "targets"),
        ("evidence", "broader_related", "related_probe_sha256"),
        ("generation_contract", "answer_units"),
        ("generation_contract", "answer_units", "[]", "obligation_links"),
        ("generation_contract", "answer_units", "[]", "requirement_ids"),
        ("generation_contract", "answer_units", "[]", "source_numbers"),
        ("generation_contract", "coverage"),
        ("generation_contract", "coverage", "[]", "source_numbers"),
        ("generation_contract", "coverage", "[]", "unit_ids"),
        ("generation_contract", "obligation_coverage"),
        ("generation_contract", "obligation_coverage", "[]", "dimensions"),
        (
            "generation_contract",
            "obligation_coverage",
            "[]",
            "dimensions",
            "[]",
            "source_numbers",
        ),
        (
            "generation_contract",
            "obligation_coverage",
            "[]",
            "dimensions",
            "[]",
            "unit_ids",
        ),
        ("generation_contract", "obligation_scopes"),
        ("generation_contract", "inspection_scopes"),
        (
            "generation_contract",
            "inspection_scopes",
            "[]",
            "allowed_requirement_ids",
        ),
        (
            "generation_contract",
            "obligation_scopes",
            "[]",
            "allowed_requirement_ids",
        ),
        (
            "generation_contract",
            "obligation_scopes",
            "[]",
            "dimension_ids",
        ),
        ("generation_contract", "premise_decisions"),
        ("generation_contract", "premise_decisions", "[]", "source_numbers"),
        ("generation_contract", "premise_ids"),
        ("generation_contract", "premise_source_scopes"),
        (
            "generation_contract",
            "premise_source_scopes",
            "[]",
            "counter_source_numbers",
        ),
        (
            "generation_contract",
            "premise_source_scopes",
            "[]",
            "framing_source_numbers",
        ),
        (
            "generation_contract",
            "premise_source_scopes",
            "[]",
            "support_source_numbers",
        ),
        ("generation_contract", "repair_codes"),
        ("generation_contract", "requirement_ids"),
        ("lanes",),
        ("lanes", "[]", "candidate_chunk_ids"),
        ("lanes", "[]", "canonical_candidate_chunk_ids"),
        ("lanes", "[]", "canonical_core_selected_chunk_ids"),
        ("lanes", "[]", "document_hint_sha256s"),
        ("lanes", "[]", "mechanism_candidate_chunk_ids"),
        ("lanes", "[]", "mechanism_query_char_counts"),
        ("lanes", "[]", "mechanism_query_sha256s"),
        ("lanes", "[]", "selected_chunk_ids"),
        ("lanes", "[]", "stage_anchor_consensus_candidates"),
        (
            "lanes",
            "[]",
            "stage_anchor_consensus_candidates",
            "[]",
            "pool_names",
        ),
        ("lanes", "[]", "stage_anchor_selected_chunk_ids"),
        ("lanes", "[]", "transition_candidate_chunk_ids"),
        ("lanes", "[]", "transition_candidates"),
        ("lanes", "[]", "transition_document_scope_sha256s"),
        ("lanes", "[]", "transition_selected_chunk_ids"),
        ("plan", "traits"),
        ("selection", "anchor_source_number_remap"),
        ("selection", "context"),
        ("selection", "discarded"),
        ("selection", "diversity_deferred_chunk_ids"),
        ("selection", "generation_context"),
        ("selection", "pre_anchor_context"),
        ("selection", "primary_chunk_ids"),
        ("selection", "retrieval_context"),
        ("selection", "source_number_remap"),
        ("selection", "context", "[]", "facet_ids"),
        ("selection", "context", "[]", "parent_primary_chunk_ids"),
        ("selection", "pre_anchor_context", "[]", "facet_ids"),
        ("selection", "pre_anchor_context", "[]", "parent_primary_chunk_ids"),
        ("selection", "retrieval_context", "[]", "facet_ids"),
        ("selection", "retrieval_context", "[]", "parent_primary_chunk_ids"),
        ("selection", "generation_context", "[]", "facet_ids"),
        ("selection", "generation_context", "[]", "parent_primary_chunk_ids"),
    }
)

_NULLABLE_OBJECT_PATHS = frozenset(
    {
        ("evidence", "broader_related"),
        ("generation_contract", "citation_locality_failure"),
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MODEL_PATTERN = re.compile(r"gpt-[A-Za-z0-9.]+(?:-[A-Za-z0-9.]+)*(?:-[0-9]{4}-[0-9]{2}-[0-9]{2})?")
_HTTP_STATUS_PATTERN = re.compile(r"[1-5][0-9]{2}")
_CHUNK_ID_PATTERN = re.compile(r"[^\r\n\x00-\x1f]{1,500}_[0-9]{3,}")
_IDENTIFIER_FIELDS = frozenset(
    {
        "collection_name",
        "conversation_id",
        "correction_unit_id",
        "facet_id",
        "inspection_id",
        "obligation_id",
        "premise_id",
        "project_id",
        "requirement_id",
        "target_id",
        "transition_id",
        "transition_predecessor_facet_id",
        "turn_id",
        "unit_id",
    }
)
_MODEL_FIELDS = frozenset({"generator_model", "planner_model"})
_IDENTIFIER_ARRAY_FIELDS = frozenset(
    {
        "facet_ids",
        "allowed_requirement_ids",
        "premise_ids",
        "requirement_ids",
        "unit_ids",
    }
)
_COVERAGE_ERROR_CODES = frozenset(
    {
        "citation_locality_invalid",
        "citation_source_mismatch",
        "conflict_requires_multiple_sources",
        "duplicate_obligation_dimension",
        "duplicate_obligation_id",
        "duplicate_premise_id",
        "duplicate_requirement_id",
        "duplicate_source_number",
        "duplicate_unit_obligation_link",
        "duplicate_unit_id",
        "duplicate_unit_reference",
        "generation_refused",
        "invalid_context",
        "invalid_payload",
        "malformed_citation",
        "missing_citation",
        "missing_obligation_dimension",
        "missing_obligation_id",
        "missing_premise_id",
        "missing_requirement_id",
        "missing_unit_obligation_link",
        "missing_unit_requirement_id",
        "obligation_requirement_mismatch",
        "obligation_requirement_status_mismatch",
        "obligation_dimension_capacity_exceeded",
        "obligation_role_mismatch",
        "obligation_source_mapping_mismatch",
        "obligation_source_mismatch",
        "obligation_unit_mapping_mismatch",
        "out_of_order_obligation_dimension",
        "out_of_order_obligation_id",
        "out_of_order_premise_id",
        "out_of_order_requirement_id",
        "out_of_order_unit_obligation_link",
        "out_of_order_unit_requirement_id",
        "premise_correction_invalid",
        "premise_correction_missing",
        "premise_correction_not_first",
        "premise_correction_requirement_mismatch",
        "premise_provenance_mismatch",
        "premise_source_mismatch",
        "premise_status_invalid",
        "source_mapping_mismatch",
        "source_number_out_of_range",
        "status_gap_mismatch",
        "status_unit_mismatch",
        "text_limit_exceeded",
        "unit_mapping_mismatch",
        "unknown_premise_id",
        "unknown_requirement_id",
        "unknown_obligation_dimension",
        "unknown_obligation_id",
        "unknown_unit_id",
        "unknown_unit_obligation_link",
        "unknown_unit_requirement_id",
        "unresolvable_citation",
        "unsupported_obligation_has_unit",
        "unsupported_requirement_has_unit",
    }
)
_CORPUS_FAILURE_CODES = frozenset(
    {
        "broader_scan_scope_mismatch",
        "chunk_text_identity_mismatch",
        "collection_chunk_ids_mismatch",
        "collection_chunk_metadata_mismatch",
        "collection_chunk_metadata_missing",
        "collection_chunks_identity_mismatch",
        "collection_count_mismatch",
        "collection_embedding_model_mismatch",
        "collection_hnsw_space_mismatch",
        "collection_metadata_count_mismatch",
        "collection_metadata_missing",
        "collection_name_mismatch",
        "collection_records_malformed",
        "collection_records_missing",
        "duplicate_loaded_chunk_id",
        "duplicate_manifest_chunk_id",
        "eligible_chunk_ids_mismatch",
        "embedding_model_mismatch",
        "hnsw_space_mismatch",
        "invalid_loaded_chunk",
        "invalid_manifest_chunk_id",
        "loaded_chunk_count_mismatch",
        "manifest_chunk_metadata_mismatch",
        "manifest_chunk_order_mismatch",
        "manifest_collection_count_mismatch",
        "manifest_identity_mismatch",
        "manifest_identity_missing",
        "manifest_text_identity_missing",
        "scan_scope_mismatch",
        "target_scan_scope_mismatch",
    }
)
_RULE_CODES = frozenset(
    {
        "absence_gate_not_applicable",
        "all_subject_targets_direct",
        "certified_direct_absence",
        "compound_named_subject_split",
        "corpus_integrity_failed",
        "direct_absence_not_certifiable",
        "direct_subject_and_facet_evidence",
        "direct_subject_evidence",
        "multiple_targets_require_disambiguation",
        "no_safe_related_material",
        "no_subject_target",
        "premise_evaluation_pending",
        "planner_bounded_related_material",
        "qualified_broader_material",
        "requested_relationship_not_established",
        "source_backed_premise_contradiction",
        "some_subject_targets_direct",
        "structural_stage_shortfall",
        "trusted_related_tail_material",
    }
)
_EXCEPTION_CODES = frozenset(
    {
        "authentication_error",
        "bad_request",
        "connection_error",
        "content_filter",
        "context_length_exceeded",
        "insufficient_quota",
        "internal_server_error",
        "invalid_api_key",
        "invalid_request_error",
        "model_not_found",
        "not_found",
        "permission_denied",
        "rate-limit/429",
        "rate_limit_exceeded",
        "request_timeout",
        "server_error",
        "service_unavailable",
    }
)
_EXACT_STRING_VALUES: dict[str, frozenset[str]] = {
    "anchor_normalizer_version": frozenset({"unicode-nfkc-casefold-anchor-v1"}),
    "broad_execution_version": frozenset(
        {
            "broad-canonical-core-v1",
            "broad-stage-consensus-v1",
            "broad-stage-role-eligibility-v2",
            "broad-stage-role-eligibility-v3",
            "broad-stage-role-eligibility-v4",
            "broad-stage-role-eligibility-v5",
            "broad-stage-narrative-span-v6",
            "broad-stage-narrative-span-v7",
            "broad-stage-narrative-span-v8",
            "not_applicable",
        }
    ),
    "broad_context_order": frozenset({"corpus_ordinal", "selection"}),
    "chronology_band": frozenset({"early", "late", "middle", "none"}),
    "displacement_cause": frozenset({"distance_filtering", "document_filtering", "truncation"}),
    "code": frozenset(
        {
            "empty_claim",
            "internal_sentence_terminator",
            "missing_terminal_punctuation",
            "multiline_claim",
            "multiple_citation_groups",
            "pre_citation_terminal_punctuation",
            "semicolon_in_claim",
            "trailing_content_after_citation",
        }
    ),
    "dimension": frozenset(
        {
            "adjacent_stage_link",
            "action_or_mechanism",
            "cause_or_enabler",
            "consequence",
            "continuity_or_change",
            "institutional_handoff",
            "mechanism",
            "qualification",
            "qualification_or_counterargument",
            "significance_or_consequence",
            "stage_development",
            "subject_or_definition",
        }
    ),
    "dimension_ids": frozenset(
        {
            "adjacent_stage_link",
            "action_or_mechanism",
            "cause_or_enabler",
            "consequence",
            "continuity_or_change",
            "institutional_handoff",
            "mechanism",
            "qualification",
            "qualification_or_counterargument",
            "significance_or_consequence",
            "stage_development",
            "subject_or_definition",
        }
    ),
    "error_code": _COVERAGE_ERROR_CODES,
    "eligibility": frozenset(
        {
            "eligible",
            "missing_chunk",
            "insufficient_distinctive_stage_anchor_match",
            "no_distinctive_stage_anchor",
            "no_handoff_capacity_match",
            "no_institutional_bearer_match",
            "no_institutional_handoff_match",
            "no_predecessor_stage_intent",
            "no_predecessor_stage_intent_match",
            "no_role_signal",
            "no_stage_intent_match",
            "no_successor_stage_intent",
            "no_successor_stage_intent_match",
            "no_transition_signal",
        }
    ),
    "exception_code": _EXCEPTION_CODES,
    "facet_embedding": frozenset({"single_batched_request"}),
    "failure_code": frozenset(
        {
            "cost_limit_exceeded",
            "invalid_planner_output",
            "planner_call_failed",
            "planner_refused_or_unparsed",
        }
    ),
    "failure_codes": _CORPUS_FAILURE_CODES,
    "fallback_reason": frozenset(
        {
            "corpus_integrity_failed",
            "invalid_planner_output",
            "low_budget_headroom",
            "planner_call_failed",
            "planner_refusal",
            "planner_refused_or_unparsed",
            "planner_timeout",
            "planner_unavailable",
        }
    ),
    "focus": frozenset(
        {
            "cross_cutting",
            "endpoint",
            "mechanism",
            "origin",
            "transition",
        }
    ),
    "gap_reason": frozenset({"no_direct_support", "none", "partial_support", "source_conflict"}),
    "generator_reasoning_effort": frozenset({"high", "low", "max", "medium", "none", "xhigh"}),
    "generator_verbosity": frozenset({"high", "low", "medium"}),
    "hnsw_space": frozenset({"", "cosine", "ip", "l2"}),
    "kind": frozenset(
        {"adjacent_stage_link", "requirement_component", "stage"}
    ),
    "lane": frozenset({"analogue", "broader_related", "direct", "generic_semantic"}),
    "lane_selection": frozenset(
        {
            "one_each_then_round_robin",
            "canonical_stage_core_then_global_supplement",
            "consensus_stage_anchor_then_global_supplement",
            "consensus_stage_anchor_then_transition_then_global_supplement",
            "stage_coverage_then_document_diversity",
            "stage_mechanism_coverage_then_document_diversity",
        }
    ),
    "broad_mechanism_lexical_version": frozenset(
        {"not_applicable", "role-scoped-mechanism-lexical-v1"}
    ),
    "broad_transition_lane_version": frozenset(
        {
            "adjacent-pair-transition-v1",
            "adjacent-pair-transition-v2",
            "adjacent-pair-transition-v3",
            "not_applicable",
        }
    ),
    "lineage_stage_contract_version": frozenset(
        {
            "long-institutional-lineage-v1",
            "long-institutional-lineage-v2",
            "not_applicable",
        }
    ),
    "lineage_transition_capacity_policy": frozenset(
        {
            "not_applicable",
            "reuse-selected-stage-source-before-extra-source",
        }
    ),
    "lexical_scoring_version": frozenset({"bm25-nfkd-word-v1"}),
    "mode": frozenset({"broad_synthesis", "planned", "standard"}),
    "neighbor_expansion": frozenset({"primaries_first_then_immediate_neighbors"}),
    "normalizer_version": frozenset(
        {
            "evidence-coverage-normalizer/1",
            "evidence-coverage-normalizer/2",
            "evidence-coverage-normalizer/3",
            "evidence-coverage-normalizer/4",
            "evidence-coverage-normalizer/5",
            "evidence-coverage-normalizer/6",
            "evidence-coverage-normalizer/7",
        }
    ),
    "origin": frozenset({"corpus_anchor", "neighbor", "primary", "retrieval"}),
    "planner_prompt_version": frozenset(
        {
            "query-planner-v2",
            "query-planner-v3",
            "query-planner-v4",
            "query-planner-v5",
            "query-planner-v6",
            "query-planner-v7",
            "query-planner-v8",
            "query-planner-v9",
            "query-planner-v10",
            "query-planner-v11",
        }
    ),
    "planner_validation_code": frozenset(
        {
            "broad_plan_under_decomposed",
            "broad_endpoint_not_terminal",
            "broad_narrative_gap",
            "broad_origin_is_overview",
            "broad_origin_not_preserved",
            "document_role_mismatch",
            "duplicate_query",
            "established_answer_claim",
            "missing_premise_framing",
            "missing_requirement_mapping",
            "original_query_changed",
            "original_query_too_long",
            "lineage_stage_cardinality_mismatch",
            "lineage_handoff_invalid",
            "lineage_handoff_route_mismatch",
            "lineage_stage_role_invalid",
            "plan_structure_invalid",
            "planner_owned_original",
            "premise_route_mismatch",
            "query_drift",
            "too_many_facets",
            "unknown_document_hint",
            "untrusted_target",
            "untrusted_target_classification",
        }
    ),
    "planner_reasoning_effort": frozenset({"high", "low", "max", "medium", "none", "xhigh"}),
    "planner_verbosity": frozenset({"high", "low", "medium"}),
    "policy_version": frozenset(
        {
            "evidence-gate-v1",
            "evidence-gate-v2",
            "evidence-gate-v3",
            "evidence-planned-v4",
            "evidence-planned-v5",
            "evidence-planned-v6",
            "evidence-planned-v7",
            "evidence-planned-v8",
            "evidence-planned-v9",
            "evidence-planned-v10",
            "evidence-planned-v11",
            "evidence-planned-v12",
            "evidence-planned-v13",
            "evidence-planned-v14",
            "evidence-planned-v15",
            "evidence-planned-v16",
            "evidence-planned-v17",
            "evidence-planned-v18",
            "evidence-planned-v19",
            "evidence-planned-v20",
            "evidence-planned-v21",
            "evidence-planned-v22",
            "evidence-planned-v23",
            "evidence-planned-v24",
        }
    ),
    "prompt_version": frozenset(
        {
            "evidence-coverage-v2",
            "evidence-coverage-v3",
            "evidence-coverage-v4",
            "evidence-coverage-v5",
            "evidence-coverage-v6",
            "evidence-coverage-v7",
            "evidence-coverage-v8",
            "evidence-coverage-v9",
        }
    ),
    "pool_names": frozenset({"canonical", "mechanism", "provider"}),
    "request_schema": frozenset(
        {
            "archivist.answer_request/3",
            "archivist.answer_request/4",
            "archivist.answer_request/5",
            "archivist.answer_request/6",
        }
    ),
    "reason": frozenset(
        {
            "distance_threshold",
            "final_source_cap",
            "fusion_primary_cap",
            "missing_disk_chunk",
            "structural_document",
        }
    ),
    "renderer_version": frozenset({"evidence-coverage-renderer/1"}),
    "repair_codes": _COVERAGE_ERROR_CODES,
    "retrieval_version": frozenset(
        {
            "faceted-hybrid-rrf-v2",
            "faceted-hybrid-rrf-v3",
            "faceted-hybrid-rrf-v4",
            "faceted-hybrid-rrf-v5",
            "faceted-hybrid-rrf-v6",
            "faceted-hybrid-rrf-v7",
            "faceted-hybrid-rrf-v8",
            "faceted-hybrid-rrf-v9",
            "faceted-hybrid-rrf-v10",
            "faceted-hybrid-rrf-v11",
            "faceted-hybrid-rrf-v12",
            "faceted-hybrid-rrf-v13",
            "faceted-hybrid-rrf-v14",
            "faceted-hybrid-rrf-v15",
            "hybrid-bm25-rrf-v1",
        }
    ),
    "role": frozenset(
        {
            "broader_related",
            "cause",
            "chronology",
            "consequence",
            "counterargument",
            "definition",
            "endpoint",
            "event",
            "facet",
            "framing",
            "identity",
            "mechanism",
            "original",
            "origin",
            "premise_correction",
            "premise_counter",
            "premise_support",
            "qualification",
            "quantity",
            "subject",
            "transition",
        }
    ),
    "rules_fired": _RULE_CODES,
    "schema": frozenset(
        {
            RETRIEVAL_TRACE_SCHEMA,
            "archivist.evidence_coverage_diagnostics/3",
            "archivist.evidence_coverage_diagnostics/4",
            "archivist.evidence_coverage_diagnostics/5",
            "archivist.evidence_coverage_diagnostics/6",
            "archivist.evidence_coverage_diagnostics/7",
            "archivist.evidence_policy_diagnostics/1",
            "archivist.planner_call_diagnostics/1",
            "archivist.planner_call_diagnostics/2",
            "archivist.question_plan/1",
            "archivist.question_plan/2",
            "archivist.question_plan/3",
        }
    ),
    "stage": frozenset({"context", "fusion", "primary_resolution", "semantic"}),
    "status": frozenset(
        {
            "answered",
            "clean_abstention",
            "conflicting",
            "contradicted",
            "corpus_integrity_failed",
            "failed",
            "generation_contract_failed",
            "insufficient_evidence",
            "not_applicable",
            "not_called",
            "partial",
            "succeeded",
            "supported",
            "unknown",
            "unresolved",
            "unsupported",
        }
    ),
    "tie_break": frozenset({"rrf_desc_semantic_rank_lexical_rank_chunk_id"}),
    "tokenizer_version": frozenset({"nfkd-unicode-word-possessive-v1"}),
    "traits": frozenset(
        {
            "absence_sensitive",
            "broad_synthesis",
            "long_institutional_lineage",
            "multi_part",
            "premise_sensitive",
            "relationship",
        }
    ),
    "document_role_profile_version": frozenset(
        {"document-role-profile-v1"}
    ),
    "validation_result": frozenset({"invalid", "not_run", "valid"}),
    "value": frozenset(
        {
            "clean_abstention",
            "direct_answer",
            "indeterminate",
            "partial_answer",
            "qualified_near_match",
        }
    ),
}
_CHUNK_ID_ARRAY_FIELDS = frozenset(
    {
        "candidate_chunk_ids",
        "canonical_candidate_chunk_ids",
        "canonical_core_selected_chunk_ids",
        "mechanism_candidate_chunk_ids",
        "parent_primary_chunk_ids",
        "primary_chunk_ids",
        "relationship_chunk_ids",
        "selected_chunk_ids",
        "stage_anchor_selected_chunk_ids",
        "transition_candidate_chunk_ids",
        "transition_selected_chunk_ids",
    }
)


def document_identifier_sha256(value: object) -> str:
    """Return the stable trace identifier for a corpus document label."""

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def validate_text_free_retrieval_trace(trace: object) -> None:
    """Reject every trace field outside the closed diagnostic schema."""

    referenced_document_hashes: set[str] = set()
    distributed_document_hashes: set[str] = set()

    def display_path(path: tuple[str, ...]) -> str:
        rendered = "trace"
        for part in path:
            rendered += "[]" if part == "[]" else f".{part}"
        return rendered

    def field_name(path: tuple[str, ...]) -> str:
        return next(
            (part for part in reversed(path) if part != "[]"),
            "",
        )

    def validate_string(item: str, path: tuple[str, ...]) -> None:
        field = field_name(path)
        if field == "trace_id":
            if _TRACE_ID_PATTERN.fullmatch(item) is None:
                raise ValueError("retrieval trace ID must be 32 lowercase hexadecimal characters")
            return
        if field == "sha256" or field.endswith("_sha256") or field.endswith("_sha256s"):
            if _SHA256_PATTERN.fullmatch(item) is None:
                raise ValueError(f"retrieval trace {display_path(path)} must be a SHA-256")
            if field in {"document_sha256", "document_hint_sha256s"}:
                referenced_document_hashes.add(item)
            return
        if field == "created_at":
            try:
                datetime.fromisoformat(item)
            except ValueError as exc:
                raise ValueError(
                    "retrieval trace created_at must be an ISO-8601 timestamp"
                ) from exc
            return
        if field == "chunk_id" or (len(path) >= 2 and path[-2] in _CHUNK_ID_ARRAY_FIELDS):
            if _CHUNK_ID_PATTERN.fullmatch(item) is None:
                raise ValueError(
                    f"retrieval trace {display_path(path)} contains an invalid chunk identifier"
                )
            return
        if field in _IDENTIFIER_FIELDS or (len(path) >= 2 and path[-2] in _IDENTIFIER_ARRAY_FIELDS):
            if _IDENTIFIER_PATTERN.fullmatch(item) is None:
                raise ValueError(
                    f"retrieval trace {display_path(path)} contains an invalid identifier"
                )
            return
        if field in _MODEL_FIELDS:
            if _MODEL_PATTERN.fullmatch(item) is None:
                raise ValueError(
                    f"retrieval trace {display_path(path)} contains an invalid model identifier"
                )
            return
        if field == "exception_code" and _HTTP_STATUS_PATTERN.fullmatch(item):
            return
        allowed_values = _EXACT_STRING_VALUES.get(field)
        if allowed_values is None or item not in allowed_values:
            raise ValueError(
                f"retrieval trace {display_path(path)} contains an unsupported diagnostic value"
            )

    def walk(item: object, path: tuple[str, ...]) -> None:
        if path in _NULLABLE_OBJECT_PATHS and item is None:
            return
        if path in _OBJECT_FIELDS:
            if not isinstance(item, Mapping):
                if path == ("query",):
                    raise ValueError("retrieval trace query must contain only hashed diagnostics")
                raise ValueError(f"retrieval trace {display_path(path)} must be an object")
            allowed = _OBJECT_FIELDS[path]
            for raw_key, nested in item.items():
                if not isinstance(raw_key, str):
                    raise ValueError(f"retrieval trace {display_path(path)} has a non-string field")
                key = raw_key.casefold()
                if key in _FORBIDDEN_FIELDS:
                    raise ValueError(
                        f"retrieval trace contains forbidden field {display_path(path)}.{raw_key}"
                    )
                if raw_key not in allowed:
                    raise ValueError(
                        f"retrieval trace contains unsupported field {display_path(path)}.{raw_key}"
                    )
                walk(nested, (*path, raw_key))
            return

        if path in _DOCUMENT_DISTRIBUTION_PATHS:
            if not isinstance(item, Mapping):
                raise ValueError(f"retrieval trace {display_path(path)} must be an object")
            for document_sha256, count in item.items():
                if (
                    not isinstance(document_sha256, str)
                    or _SHA256_PATTERN.fullmatch(document_sha256) is None
                ):
                    raise ValueError(
                        "retrieval trace document distribution has an invalid document hash"
                    )
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ValueError(
                        "retrieval trace document distribution counts must be non-negative integers"
                    )
                distributed_document_hashes.add(document_sha256)
            return

        if path in _ARRAY_PATHS:
            if not isinstance(item, list):
                raise ValueError(f"retrieval trace {display_path(path)} must be an array")
            for nested in item:
                walk(nested, (*path, "[]"))
            return

        if isinstance(item, Mapping):
            raise ValueError(
                f"retrieval trace contains an unsupported object at {display_path(path)}"
            )
        if isinstance(item, list):
            raise ValueError(
                f"retrieval trace contains an unsupported array at {display_path(path)}"
            )
        if not isinstance(item, (str, int, float, bool, type(None))):
            raise ValueError(f"retrieval trace contains a non-JSON value at {display_path(path)}")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(
                f"retrieval trace contains a non-finite number at {display_path(path)}"
            )
        if isinstance(item, str):
            validate_string(item, path)

    walk(trace, ())
    unbound_documents = distributed_document_hashes - referenced_document_hashes
    if unbound_documents:
        raise ValueError(
            "retrieval trace document distribution contains hashes not "
            "referenced by a trace candidate or context"
        )


__all__ = [
    "RETRIEVAL_TRACE_SCHEMA",
    "document_identifier_sha256",
    "validate_text_free_retrieval_trace",
]
