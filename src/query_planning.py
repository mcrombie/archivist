"""Pure contracts and deterministic policy for evidence-planned queries.

This module deliberately performs no network or model calls.  A caller may parse a
planner response into :class:`QuestionPlan`, then pass it to
``validate_question_plan``.  The validator owns the trusted parts of the plan:
route traits, evidence targets, and the unchanged original ``F0`` facet.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, MutableMapping, Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    ValidationError,
    field_validator,
    model_validator,
)

from document_roles import MAX_DOCUMENT_ROLE_TERMS


QUESTION_PLAN_SCHEMA = "archivist.question_plan/3"
PLANNER_QUESTION_PLAN_SCHEMA = "archivist.planner_question_plan/3"
RESOLVED_TURN_SCHEMA = "archivist.resolved_turn/1"
F0_FACET_ID = "F0"

MAX_ANSWER_REQUIREMENTS = 8
MAX_SEARCH_FACETS = 9
MAX_ADDED_SEARCH_FACETS = MAX_SEARCH_FACETS - 1
MAX_PREMISE_HYPOTHESES = 2
MAX_EVIDENCE_TARGETS = 3
MAX_DOCUMENT_HINTS_PER_FACET = 2
MAX_SEARCH_QUERY_CHARS = 240
MAX_ORIGINAL_QUERY_CHARS = 4_000
MAX_ADDED_QUERY_CHARS = 1_200
MAX_INSTITUTIONAL_HANDOFF_CHARS = 160
MAX_PLANNER_REQUIREMENTS = MAX_ANSWER_REQUIREMENTS
MAX_PLANNER_FACETS = MAX_ADDED_SEARCH_FACETS
MIN_BROAD_STAGE_REQUIREMENTS = 5
LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS = MAX_ANSWER_REQUIREMENTS
PLAN_STRUCTURE_INVALID = "plan_structure_invalid"
PLANNER_SEMANTIC_VALIDATION_CODES = frozenset(
    {
        "broad_plan_under_decomposed",
        "duplicate_query",
        "established_answer_claim",
        "missing_premise_framing",
        "missing_requirement_mapping",
        "original_query_changed",
        "original_query_too_long",
        "lineage_handoff_invalid",
        "lineage_handoff_route_mismatch",
        "lineage_stage_cardinality_mismatch",
        "lineage_stage_role_invalid",
        "document_role_mismatch",
        "broad_origin_not_preserved",
        "planner_owned_original",
        "premise_route_mismatch",
        "query_drift",
        "too_many_facets",
        "unknown_document_hint",
        "untrusted_target",
        "untrusted_target_classification",
    }
)
PLANNER_VALIDATION_CODES = PLANNER_SEMANTIC_VALIDATION_CODES | {PLAN_STRUCTURE_INVALID}

_SAFE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,31}$"
SafePlanId = Annotated[str, Field(pattern=_SAFE_ID_PATTERN)]
DocumentHint = Annotated[str, Field(min_length=1, max_length=300)]


class RouteTrait(StrEnum):
    BROAD_SYNTHESIS = "broad_synthesis"
    LONG_INSTITUTIONAL_LINEAGE = "long_institutional_lineage"
    MULTI_PART = "multi_part"
    RELATIONSHIP = "relationship"
    PREMISE_SENSITIVE = "premise_sensitive"
    ABSENCE_SENSITIVE = "absence_sensitive"


class FacetRole(StrEnum):
    ORIGINAL = "original"
    ORIGIN = "origin"
    TRANSITION = "transition"
    MECHANISM = "mechanism"
    ENDPOINT = "endpoint"
    PREMISE_SUPPORT = "premise_support"
    PREMISE_COUNTER = "premise_counter"
    FRAMING = "framing"
    BROADER_RELATED = "broader_related"


class EvidenceTargetRole(StrEnum):
    SUBJECT = "subject"
    FACET = "facet"


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class ResolvedTurn(_ContractModel):
    """Conversation resolution output consumed by planning.

    The fields other than ``standalone_question`` preserve useful resolution
    structure without making prior assistant prose evidence.
    """

    schema_: Literal["archivist.resolved_turn/1"] = Field(
        default=RESOLVED_TURN_SCHEMA,
        alias="schema",
    )
    standalone_question: str = Field(min_length=1, max_length=4_000)
    entities: tuple[str, ...] = Field(default=(), max_length=16)
    scope: str | None = Field(default=None, max_length=1_000)
    corrections: tuple[str, ...] = Field(default=(), max_length=8)
    relationship: str | None = Field(default=None, max_length=1_000)
    # Application-owned provenance: raw user messages only, never assistant
    # prose. Orchestration overwrites any model-produced value.
    trusted_user_texts: tuple[str, ...] = Field(default=(), max_length=8)

    @property
    def schema(self) -> Literal["archivist.resolved_turn/1"]:
        return self.schema_

    @field_validator("entities", "corrections", "trusted_user_texts")
    @classmethod
    def validate_text_items(
        cls,
        values: tuple[str, ...],
        info: ValidationInfo,
    ) -> tuple[str, ...]:
        cleaned = tuple(value.strip() for value in values)
        if any(not value for value in cleaned):
            raise ValueError("resolved-turn lists cannot contain blank values")
        limit = (
            MAX_ORIGINAL_QUERY_CHARS
            if info.field_name == "trusted_user_texts"
            else MAX_SEARCH_QUERY_CHARS
        )
        if any(len(value) > limit for value in cleaned):
            raise ValueError(f"resolved-turn list values cannot exceed {limit} characters")
        normalized = [normalize_search_query(value) for value in cleaned]
        if len(normalized) != len(set(normalized)):
            raise ValueError("resolved-turn lists cannot contain duplicate values")
        return cleaned


class DocumentCatalogEntry(_ContractModel):
    document_id: str = Field(min_length=1, max_length=300)
    chapter_title: str = Field(min_length=1, max_length=500)
    corpus_ordinal: int = Field(ge=0)
    role_terms: tuple[str, ...] = Field(
        default=(),
        max_length=MAX_DOCUMENT_ROLE_TERMS,
        description=(
            "Bounded, normalized corpus-derived search-orientation tokens; "
            "never evidence or manuscript passages."
        ),
    )

    @field_validator("role_terms")
    @classmethod
    def role_terms_are_bounded_unique_tokens(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("document role terms cannot contain duplicates")
        if any(
            not value
            or value != value.casefold()
            or value != value.strip()
            or len(value) > 48
            or re.search(r"\s", value)
            for value in values
        ):
            raise ValueError(
                "document role terms must be bounded normalized single tokens"
            )
        return values


class InstitutionalHandoff(_ContractModel):
    """Planner orientation for one institutional-lineage stage.

    These fields are search intent, never evidence.  Local validation requires
    adjacent stages to name the same carried capacity so a chronological list
    cannot masquerade as an institutional lineage.
    """

    bearer: str = Field(
        min_length=2,
        max_length=MAX_INSTITUTIONAL_HANDOFF_CHARS,
    )
    inherited_capacity: str = Field(
        min_length=2,
        max_length=MAX_INSTITUTIONAL_HANDOFF_CHARS,
    )
    transfer_mechanism: str = Field(
        min_length=2,
        max_length=MAX_INSTITUTIONAL_HANDOFF_CHARS,
    )
    outgoing_capacity: str = Field(
        min_length=2,
        max_length=MAX_INSTITUTIONAL_HANDOFF_CHARS,
    )


class AnswerRequirement(_ContractModel):
    requirement_id: str = Field(pattern=_SAFE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    order: int = Field(ge=0)
    required: bool = True
    institutional_handoff: InstitutionalHandoff | None = None


class SearchFacet(_ContractModel):
    facet_id: str = Field(pattern=_SAFE_ID_PATTERN)
    requirement_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_ANSWER_REQUIREMENTS,
    )
    role: FacetRole
    # F0 is application-owned and preserves the complete resolved question.
    # Planner-added facets remain subject to MAX_SEARCH_QUERY_CHARS below.
    search_query: str = Field(min_length=1, max_length=MAX_ORIGINAL_QUERY_CHARS)
    document_hints: tuple[str, ...] = Field(
        default=(),
        max_length=MAX_DOCUMENT_HINTS_PER_FACET,
    )

    @field_validator("requirement_ids", "document_hints")
    @classmethod
    def values_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("facet references cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def enforce_added_query_limit(self) -> SearchFacet:
        application_owned_original = (
            self.facet_id == F0_FACET_ID and self.role is FacetRole.ORIGINAL
        )
        if not application_owned_original and len(self.search_query) > MAX_SEARCH_QUERY_CHARS:
            raise ValueError(
                f"planner-added search queries cannot exceed {MAX_SEARCH_QUERY_CHARS} characters"
            )
        return self


class PremiseHypothesis(_ContractModel):
    premise_id: str = Field(pattern=_SAFE_ID_PATTERN)
    proposition: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    support_facet_id: str = Field(pattern=_SAFE_ID_PATTERN)
    counter_facet_id: str = Field(pattern=_SAFE_ID_PATTERN)
    framing_facet_id: str | None = Field(default=None, pattern=_SAFE_ID_PATTERN)


class EvidenceTarget(_ContractModel):
    target_id: str = Field(pattern=_SAFE_ID_PATTERN)
    query_surface_span: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    role: EvidenceTargetRole
    absence_checkable: bool


class QuestionPlan(_ContractModel):
    """Planner-shaped contract plus application provenance.

    Model-produced plans omit ``F0``.  ``validate_question_plan`` performs
    contextual validation and returns another ``QuestionPlan`` with ``F0`` in
    the first position.
    """

    schema_: Literal["archivist.question_plan/3"] = Field(
        default=QUESTION_PLAN_SCHEMA,
        alias="schema",
    )
    traits: tuple[RouteTrait, ...] = Field(default=(), max_length=len(RouteTrait))
    requirements: tuple[AnswerRequirement, ...] = Field(
        min_length=1,
        max_length=MAX_ANSWER_REQUIREMENTS,
    )
    facets: tuple[SearchFacet, ...] = Field(default=(), max_length=MAX_SEARCH_FACETS)
    premises: tuple[PremiseHypothesis, ...] = Field(
        default=(),
        max_length=MAX_PREMISE_HYPOTHESES,
    )
    targets: tuple[EvidenceTarget, ...] = Field(
        default=(),
        max_length=MAX_EVIDENCE_TARGETS,
    )
    planner_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=240)

    @property
    def schema(self) -> Literal["archivist.question_plan/3"]:
        return self.schema_

    @model_validator(mode="after")
    def validate_internal_references(self) -> QuestionPlan:
        _require_unique("route trait", [trait.value for trait in self.traits])
        _require_unique(
            "requirement ID",
            [requirement.requirement_id for requirement in self.requirements],
        )
        _require_unique("facet ID", [facet.facet_id for facet in self.facets])
        _require_unique(
            "premise ID",
            [premise.premise_id for premise in self.premises],
        )
        _require_unique("target ID", [target.target_id for target in self.targets])

        all_ids = [
            *(requirement.requirement_id for requirement in self.requirements),
            *(facet.facet_id for facet in self.facets),
            *(premise.premise_id for premise in self.premises),
            *(target.target_id for target in self.targets),
        ]
        _require_unique("plan ID", all_ids)

        orders = [requirement.order for requirement in self.requirements]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            raise ValueError("requirements must appear in strictly increasing order")

        known_requirements = {requirement.requirement_id for requirement in self.requirements}
        for facet in self.facets:
            unknown = set(facet.requirement_ids) - known_requirements
            if unknown:
                raise ValueError(
                    f"facet {facet.facet_id!r} has unknown requirement IDs: {sorted(unknown)!r}"
                )

        facets_by_id = {facet.facet_id: facet for facet in self.facets}
        for premise in self.premises:
            referenced_ids = [
                premise.support_facet_id,
                premise.counter_facet_id,
                *([premise.framing_facet_id] if premise.framing_facet_id is not None else []),
            ]
            if len(referenced_ids) != len(set(referenced_ids)):
                raise ValueError(f"premise {premise.premise_id!r} must use distinct facet IDs")
            dangling = set(referenced_ids) - facets_by_id.keys()
            if dangling:
                raise ValueError(
                    f"premise {premise.premise_id!r} has dangling facet IDs: {sorted(dangling)!r}"
                )
            if facets_by_id[premise.support_facet_id].role is not FacetRole.PREMISE_SUPPORT:
                raise ValueError("premise support facet must use the premise_support role")
            if facets_by_id[premise.counter_facet_id].role is not FacetRole.PREMISE_COUNTER:
                raise ValueError("premise counter facet must use the premise_counter role")
            if (
                premise.framing_facet_id is not None
                and facets_by_id[premise.framing_facet_id].role is not FacetRole.FRAMING
            ):
                raise ValueError("premise framing facet must use the framing role")

        normalized_queries = [normalize_search_query(facet.search_query) for facet in self.facets]
        if len(normalized_queries) != len(set(normalized_queries)):
            raise ValueError("search queries must be unique after normalization")

        normalized_targets = [
            normalize_search_query(target.query_surface_span) for target in self.targets
        ]
        if len(normalized_targets) != len(set(normalized_targets)):
            raise ValueError("evidence targets must be unique after normalization")

        added_query_chars = sum(
            len(facet.search_query) for facet in self.facets if facet.facet_id != F0_FACET_ID
        )
        if any(
            len(facet.search_query) > MAX_SEARCH_QUERY_CHARS
            for facet in self.facets
            if facet.facet_id != F0_FACET_ID
        ):
            raise ValueError(
                f"planner-added search queries cannot exceed {MAX_SEARCH_QUERY_CHARS} characters"
            )
        if added_query_chars > MAX_ADDED_QUERY_CHARS:
            raise ValueError(f"added search queries exceed {MAX_ADDED_QUERY_CHARS} characters")
        return self


class PlannerAnswerRequirement(_ContractModel):
    """Minimal model-owned requirement shape.

    Ordering and the required/optional decision are application-owned so a
    structured-output response cannot invalidate itself on bookkeeping that
    carries no search meaning.
    """

    requirement_id: SafePlanId
    label: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    institutional_handoff: InstitutionalHandoff | None = None


class PlannerSearchFacet(_ContractModel):
    """Shape-only planner facet parsed before semantic validation."""

    facet_id: SafePlanId
    requirement_ids: tuple[SafePlanId, ...] = Field(
        min_length=1,
        max_length=MAX_ANSWER_REQUIREMENTS,
    )
    role: FacetRole
    search_query: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    document_hints: tuple[DocumentHint, ...] = Field(
        default=(),
        max_length=MAX_DOCUMENT_HINTS_PER_FACET,
    )


class PlannerPremiseHypothesis(_ContractModel):
    """Shape-only premise references parsed before semantic validation."""

    premise_id: SafePlanId
    proposition: str = Field(min_length=1, max_length=MAX_SEARCH_QUERY_CHARS)
    support_facet_id: SafePlanId
    counter_facet_id: SafePlanId
    framing_facet_id: SafePlanId | None = None


class PlannerQuestionPlan(_ContractModel):
    """Compact provider-facing proposal.

    This intentionally excludes local routing traits, trusted evidence targets,
    F0, and execution status.  It also has no cross-field model validator:
    Structured Outputs establishes shape, then ``validate_planner_question_plan``
    performs semantic checks locally and can fall back without misclassifying a
    semantic rejection as an SDK parse failure.
    """

    schema_: Literal["archivist.planner_question_plan/3"] = Field(
        default=PLANNER_QUESTION_PLAN_SCHEMA,
        alias="schema",
    )
    requirements: tuple[PlannerAnswerRequirement, ...] = Field(
        min_length=1,
        max_length=MAX_PLANNER_REQUIREMENTS,
    )
    facets: tuple[PlannerSearchFacet, ...] = Field(
        min_length=1,
        max_length=MAX_PLANNER_FACETS,
    )
    premises: tuple[PlannerPremiseHypothesis, ...] = Field(
        default=(),
        max_length=MAX_PREMISE_HYPOTHESES,
    )

    @property
    def schema(self) -> Literal["archivist.planner_question_plan/3"]:
        return self.schema_


class PlanValidationError(ValueError):
    """Stable local validation failure suitable for fallback diagnostics."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def safe_planner_validation_code(value: object) -> str | None:
    """Return only a finite, text-free planner validation code."""

    return value if isinstance(value, str) and value in PLANNER_VALIDATION_CODES else None


def _record_planner_validation_code(
    diagnostics: MutableMapping[str, str | None] | None,
    value: object,
) -> None:
    if diagnostics is not None:
        diagnostics["planner_validation_code"] = safe_planner_validation_code(value)


def _require_unique(label: str, values: Sequence[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label}s must be unique")


def normalize_search_query(value: str) -> str:
    """Normalize a query for duplicate and surface-form comparisons."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    return " ".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


_MEANINGLESS_QUERY_TOKENS = {
    "a",
    "an",
    "and",
    "answer",
    "about",
    "book",
    "by",
    "did",
    "do",
    "does",
    "evidence",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "manuscript",
    "of",
    "on",
    "or",
    "say",
    "search",
    "show",
    "source",
    "that",
    "the",
    "this",
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


def meaningful_query_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in normalize_search_query(value).split()
        if token not in _MEANINGLESS_QUERY_TOKENS and (len(token) >= 2 or token.isdigit())
    )


_LINEAGE_STAGE_ROLE_GENERIC_TOKENS = frozenset(
    {
        "actor",
        "actors",
        "administrative",
        "after",
        "before",
        "body",
        "change",
        "changed",
        "chronology",
        "consolidation",
        "continuity",
        "development",
        "developments",
        "distinct",
        "early",
        "endpoint",
        "event",
        "events",
        "final",
        "first",
        "function",
        "governing",
        "historical",
        "history",
        "immediate",
        "institution",
        "institutional",
        "institutions",
        "intermediate",
        "late",
        "later",
        "lineage",
        "mechanism",
        "middle",
        "narrative",
        "next",
        "origin",
        "period",
        "regime",
        "role",
        "stage",
        "successor",
        "system",
        "trace",
        "transition",
        "transformation",
    }
)
_LINEAGE_HANDOFF_GENERIC_TOKENS = (
    _LINEAGE_STAGE_ROLE_GENERIC_TOKENS
    | frozenset(
        {
            "authority",
            "capacity",
            "carried",
            "carry",
            "handoff",
            "inherit",
            "inherited",
            "inherits",
            "outgoing",
            "pass",
            "passed",
            "passes",
            "power",
            "powers",
            "transfer",
            "transferred",
            "transfers",
        }
    )
)
_LONG_INSTITUTIONAL_LINEAGE_PATTERNS = (
    re.compile(
        r"\b(?:administrative|civic|corporate|governmental|institutional|"
        r"organizational|political|state)\s+"
        r"(?:evolution|genealogy|lineage|succession|trajectory)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:evolution|genealogy|lineage|succession|trajectory)\b.{0,100}"
        r"\b(?:administration|authority|company|corporation|government|"
        r"institution|organization|regime|state|system)\w*\b",
        re.IGNORECASE,
    ),
)

_CAUSAL_ENGINE_PATTERN = re.compile(
    r"\b(?P<driver>[^?.!,;]{2,100}?)\s+as\s+"
    r"(?:an?\s+)?(?:engine|driver|instrument|source)\s+of\b",
    re.IGNORECASE,
)
_CAUSAL_DRIVER_NOISE_TOKENS = frozenset(
    {
        "account",
        "describe",
        "describes",
        "frame",
        "frames",
        "present",
        "presents",
        "treat",
        "treats",
    }
)
_NUMBERED_NARRATIVE_DOCUMENT_PATTERN = re.compile(
    r"\bchapter[\s_:-]*\d+\b",
    re.IGNORECASE,
)
_MAX_EARLY_ORIGIN_ROLE_MATCHES = 4


_BROAD_PATTERNS = (
    re.compile(
        r"\b(?:change(?:d|s|ing)?|develop(?:ed|ment|ments|ing)?|evolv(?:e|ed|es|ing)|"
        r"trajectory|lineage|history)\b.{0,60}\b(?:over time|through time|across|"
        r"throughout|from|between)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:trace|outline|survey)\b.{0,80}\b(?:change|development|evolution|"
        r"history|lineage|stages?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfrom\b.{1,160}\bto\b", re.IGNORECASE),
    re.compile(r"\bbetween\b.{1,160}\band\b", re.IGNORECASE),
    re.compile(r"\b(?:over time|throughout the|over the course of)\b", re.IGNORECASE),
)

_COORDINATED_INTERROGATIVE = re.compile(
    r"(?:[;?]\s*|,\s*|\s+)(?:and|also)\s+"
    r"(?:what|why|how|when|where|who|which|compare|identify|explain|describe)\b",
    re.IGNORECASE,
)
_ENUMERATED_REQUEST = re.compile(r"(?:^|\n)\s*(?:\d+[\).]|[a-z][\).]|[-*])\s+", re.IGNORECASE)
_PLURAL_REQUEST = re.compile(
    r"\b(?:several|multiple|different|distinct|main|major)\s+"
    r"(?:causes|mechanisms|stages|comparisons|consequences)\b",
    re.IGNORECASE,
)
_MULTIPLE_DIMENSIONS = re.compile(r"\b(?:causes?|mechanisms?|stages?|comparisons?|consequences?)\b")

_ATTRIBUTED_PREMISE = re.compile(
    r"\b(?:why|how)\b.{0,60}\b(?:book|manuscript|author|account)\b.{0,60}"
    r"\b(?:argues?|attributes?|claims?|dates?|describes?|identifies?|places?|says?)\b",
    re.IGNORECASE,
)
_FACTIVE_INTRODUCTION = re.compile(
    r"\b(?:given that|assuming that|because|in light of the fact that|"
    r"according to|on the assumption that)\b",
    re.IGNORECASE,
)
_WHY_PRESUPPOSITION = re.compile(
    r"\bwhy\s+(?:did|does|do|was|were|is|are|has|have|had)\b",
    re.IGNORECASE,
)
_HOW_FACTIVE_PREDICATE = re.compile(
    r"\bhow\s+(?:did|does|do|was|were|is|are|has|have|had)\b.{0,180}"
    r"\b(?:caus(?:e|ed|es|ing)|creat(?:e|ed|es|ing)|found(?:ed|ing)?|"
    r"begin|began|start(?:ed|ing)?|originat(?:e|ed|es|ing)|lead|led|"
    r"prevent(?:ed|ing)?|prov(?:e|ed|es|ing)|first)\b",
    re.IGNORECASE,
)

_ABSENCE_REQUEST = re.compile(
    r"\b(?:(?:does|do|did|how|whether|what)\s+)?"
    r"(?:the\s+)?(?:book|manuscript|text|author|account)\b.{0,80}"
    r"\b(?:address(?:es)?|cover(?:s|ed)?|discuss(?:es|ed)?|mention(?:s|ed)?|"
    r"say(?:s)?\s+about|treat(?:s|ed)?)\b",
    re.IGNORECASE,
)
_ABSENCE_REQUEST_REVERSED = re.compile(
    r"\b(?:what|whether|how)\b.{0,100}\b(?:addressed|covered|discussed|mentioned|"
    r"treated)\b.{0,50}\b(?:book|manuscript|text|account)\b",
    re.IGNORECASE,
)


def route_question(question: str | ResolvedTurn) -> tuple[RouteTrait, ...]:
    """Return deterministic, composable route traits in a stable order."""

    turn = _coerce_resolved_turn(question)
    text = turn.standalone_question
    traits: set[RouteTrait] = set()
    between_relationship_syntax = bool(_BETWEEN_RELATIONSHIP_REQUEST.search(text))
    bounded_between_relationship = _bounded_between_relationship_parts(text) is not None

    if (
        any(pattern.search(text) for pattern in _BROAD_PATTERNS)
        and not bounded_between_relationship
    ):
        traits.add(RouteTrait.BROAD_SYNTHESIS)
        if any(
            pattern.search(text)
            for pattern in _LONG_INSTITUTIONAL_LINEAGE_PATTERNS
        ):
            traits.add(RouteTrait.LONG_INSTITUTIONAL_LINEAGE)

    dimension_matches = _MULTIPLE_DIMENSIONS.findall(text.casefold())
    if (
        _COORDINATED_INTERROGATIVE.search(text)
        or len(re.findall(r"\?", text)) > 1
        or len(_ENUMERATED_REQUEST.findall(text)) > 1
        or _PLURAL_REQUEST.search(text)
        or len({match.rstrip("s") for match in dimension_matches}) > 1
    ):
        traits.add(RouteTrait.MULTI_PART)

    if _RELATIONAL_QUERY.search(text) or between_relationship_syntax:
        traits.add(RouteTrait.RELATIONSHIP)

    neutral_manuscript_request = bool(
        _ABSENCE_REQUEST.search(text) or _ABSENCE_REQUEST_REVERSED.search(text)
    )
    if neutral_manuscript_request:
        # A local absence decision requires a conservative user-supplied target.
        # Without one, "how does the book treat..." is an unbounded thematic
        # synthesis request rather than a named-subject absence request.
        if extract_trusted_targets(turn):
            traits.add(RouteTrait.ABSENCE_SENSITIVE)
        else:
            traits.add(RouteTrait.BROAD_SYNTHESIS)

    if not bounded_between_relationship:
        if (
            _ATTRIBUTED_PREMISE.search(text)
            or _FACTIVE_INTRODUCTION.search(text)
            or _WHY_PRESUPPOSITION.search(text)
            or _HOW_FACTIVE_PREDICATE.search(text)
        ) and not (
            neutral_manuscript_request
            and re.match(
                r"^\s*(?:what|whether|how|does|do|did)\b",
                text,
                flags=re.IGNORECASE,
            )
        ):
            traits.add(RouteTrait.PREMISE_SENSITIVE)

    return tuple(trait for trait in RouteTrait if trait in traits)


def requires_planning(question: str | ResolvedTurn) -> bool:
    """Reserve the paid planner for ambiguity that local decomposition cannot resolve."""

    turn = _coerce_resolved_turn(question)
    traits = route_question(turn)
    if (
        traits == (RouteTrait.RELATIONSHIP,)
        and _relational_parts(turn.standalone_question) is not None
    ):
        return False
    return bool(traits)


_QUOTED_TARGET = re.compile(
    r'"([^"\r\n]{1,240})"|“([^”\r\n]{1,240})”|'
    r"'([^'\r\n]{2,240})'|‘([^’\r\n]{1,240})’"
)
_PROPER_NAME_TARGET = re.compile(
    r"\b[A-Z][^\W_]*(?:[’'][A-Za-z][^\W_]*)?"
    r"(?:\s+(?:(?:of|the|and|de|van|von)\s+)?"
    r"[A-Z][^\W_]*(?:[’'][A-Za-z][^\W_]*)?)+\b"
)
_ACRONYM_TARGET = re.compile(r"\b(?:[A-Z]{2,10}|(?:[A-Z]\.){2,10})\b")
_HYPHENATED_TARGET = re.compile(r"\b[\w]+(?:-[\w]+)+\b", re.UNICODE)
_NAMED_NUMBER_TARGET = re.compile(
    r"\b(?:[A-Z][^\W_]*(?:\s+[A-Z][^\W_]*){0,2})\s+"
    r"(?:No\.?\s*)?\d+[A-Za-z]?\b"
)
_ORDINAL_NAME_TARGET = re.compile(r"\b\d+(?:st|nd|rd|th)\s+[A-Z][^\W_]*\b")
_RELATIONAL_VERB = r"(?:connect(?:s|ed|ing)?|relat(?:e|es|ed|ing)|link(?:s|ed|ing)?)"
_RELATIONAL_QUERY = re.compile(
    rf"\b{_RELATIONAL_VERB}\b[^?.!]{{0,160}}\bto\b",
    re.IGNORECASE,
)
_BETWEEN_RELATIONSHIP_REQUEST = re.compile(
    r"\b(?:relationship|connection|relation)\s+between\b",
    re.IGNORECASE,
)
_BETWEEN_RELATIONSHIP_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:how|what)\s+(?:does|do|did)\s+"
    r"(?:(?:the|this|that)\s+)?(?:manuscript|book|text|author|account)\s+"
    r"(?:describe|frame|present|treat)\s+(?:(?:the|a)\s+)?"
    r"|"
    r"what\s+(?:is|was)\s+(?:(?:the|a)\s+)?"
    r")"
    r"(?P<predicate>relationship|connection|relation)\s+between\s+"
    r"(?P<left>[^?.!,;]{1,120}?)\s+and\s+"
    r"(?P<right>[^?.!,;]{1,120}?)"
    r"(?P<context>\s+(?:as|in)\s+"
    r"(?:shaping|affecting|influencing|changing|forming)"
    r"\b[^?.!,;]{0,150})?"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_DIRECTIONAL_BETWEEN_RELATIONSHIP_PATTERN = re.compile(
    r"^\s*how\s+(?:does|do|did)\s+"
    r"(?:(?:the|a)\s+)?"
    r"(?P<predicate>relationship|connection|relation)\s+between\s+"
    r"(?P<left>[^?.!,;]{1,120}?)\s+and\s+"
    r"(?P<right>[^?.!,;]{1,120}?)"
    r"(?P<context>\s+"
    r"(?:shape|affect|influence|change|form)"
    r"\b[^?.!,;]{1,150})"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_RELATIONSHIP_OPERAND_TAIL = re.compile(
    r"\b(?:as|because|although|though|while|when|where|which|who|whose|"
    r"during|after|before|over|amid|throughout|under|within|across|"
    r"despite|unless|until|given|assuming|according|in|at|by|from|"
    r"through|with|without|among)\b|"
    r"with\s+respect\s+to|in\s+light\s+of\s+the\s+fact\s+that|"
    r"on\s+the\s+assumption\s+that",
    re.IGNORECASE,
)
_BOUNDED_RELATIONSHIP_CONTEXT_PREFIX = re.compile(
    r"^(?:(?:as|in)\s+"
    r"(?:shaping|affecting|influencing|changing|forming)"
    r"|(?:shape|affect|influence|change|form))\b",
    re.IGNORECASE,
)
_AMBIGUOUS_RELATIONSHIP_CONTEXT_TAIL = re.compile(
    r"\b(?:as|because|although|though|while|when|where|which|who|whose|"
    r"despite|unless|until|given|assuming|according)\b|"
    r"in\s+light\s+of\s+the\s+fact\s+that|"
    r"on\s+the\s+assumption\s+that",
    re.IGNORECASE,
)
_RELATIONSHIP_REQUEST = re.compile(
    rf"\b(?:between|compare|comparison|connection|relationship|relation|"
    rf"{_RELATIONAL_VERB}|versus|vs\.?)\b",
    re.IGNORECASE,
)
_DIRECTIONAL_RELATIONSHIP_PREDICATE = re.compile(
    r"\b(?:"
    r"affect(?:s|ed|ing)?|"
    r"impact(?:s|ed|ing)?|"
    r"influenc(?:e|es|ed|ing)|"
    r"shap(?:e|es|ed|ing)|"
    r"alter(?:s|ed|ing)?|"
    r"transform(?:s|ed|ing)?|"
    r"caus(?:e|es|ed|ing)|"
    r"trigger(?:s|ed|ing)?|"
    r"(?:lead(?:s|ing)?|led)\s+to|"
    r"result(?:s|ed|ing)?\s+in|"
    r"contribut(?:e|es|ed|ing)\s+to"
    r")\b",
    re.IGNORECASE,
)
_BETWEEN_NAMED_TARGETS = re.compile(
    r"\bbetween\s+"
    r"(?P<left>[A-Z][^\W_]*(?:\s+[A-Z][^\W_]*)+)\s+and\s+"
    r"(?P<right>[A-Z][^\W_]*(?:\s+[A-Z][^\W_]*)+)"
    r"(?=[\s?.!,;:]|$)",
)

_LEADING_TARGET_NOISE = {
    "a",
    "an",
    "compare",
    "describe",
    "did",
    "do",
    "does",
    "explain",
    "how",
    "identify",
    "is",
    "outline",
    "survey",
    "the",
    "trace",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}


def _trim_target_noise(surface: str) -> str:
    words = surface.split()
    while len(words) > 1 and words[0].casefold().rstrip("?:,") in _LEADING_TARGET_NOISE:
        words.pop(0)
    return " ".join(words).strip(" \t\r\n,;:.?!")


def _is_conservative_target_surface(surface: str) -> bool:
    return bool(
        _PROPER_NAME_TARGET.fullmatch(surface)
        or _ACRONYM_TARGET.fullmatch(surface)
        or _NAMED_NUMBER_TARGET.fullmatch(surface)
        or _ORDINAL_NAME_TARGET.fullmatch(surface)
        or (
            _HYPHENATED_TARGET.fullmatch(surface)
            and (any(character.isdigit() for character in surface) or not surface.islower())
        )
    )


def extract_trusted_targets(
    question: str | ResolvedTurn,
) -> tuple[EvidenceTarget, ...]:
    """Extract only conservative, user-surface evidence targets.

    No synonyms or aliases are generated.  ``ResolvedTurn.entities`` can restore
    conversation structure, but an entity is accepted only when its exact surface
    occurs in the standalone question and is independently conservative.
    """

    turn = _coerce_resolved_turn(question)
    text = turn.standalone_question
    candidates: list[tuple[int, int, str, int]] = []
    relationship_pair = _BETWEEN_NAMED_TARGETS.search(text)
    if relationship_pair is not None:
        for group_name in ("left", "right"):
            candidates.append(
                (
                    relationship_pair.start(group_name),
                    relationship_pair.end(group_name),
                    relationship_pair.group(group_name),
                    0,
                )
            )

    for match in _QUOTED_TARGET.finditer(text):
        surface = next(group for group in match.groups() if group is not None).strip()
        if surface:
            candidates.append((match.start(), match.end(), surface, 0))

    patterns = (
        _PROPER_NAME_TARGET,
        _NAMED_NUMBER_TARGET,
        _ORDINAL_NAME_TARGET,
        _ACRONYM_TARGET,
        _HYPHENATED_TARGET,
    )
    for priority, pattern in enumerate(patterns, start=1):
        for match in pattern.finditer(text):
            if (
                pattern is _PROPER_NAME_TARGET
                and relationship_pair is not None
                and match.start() <= relationship_pair.start("left")
                and match.end() >= relationship_pair.end("right")
            ):
                continue
            surface = _trim_target_noise(match.group(0))
            if not surface:
                continue
            if pattern is _ACRONYM_TARGET and surface.casefold() in _LEADING_TARGET_NOISE:
                continue
            if pattern is _HYPHENATED_TARGET and not (
                any(character.isdigit() for character in surface) or not surface.islower()
            ):
                continue
            candidates.append((match.start(), match.end(), surface, priority))

    folded_text = unicodedata.normalize("NFKC", text).casefold()
    for entity in turn.entities:
        folded_entity = unicodedata.normalize("NFKC", entity).casefold()
        start = folded_text.find(folded_entity)
        if start < 0 or not _is_conservative_target_surface(entity):
            continue
        candidates.append((start, start + len(entity), entity, 0))

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[3]))
    selected: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for start, end, surface, _priority in candidates:
        normalized = normalize_search_query(surface)
        if not normalized or normalized in seen:
            continue
        if any(
            start < selected_end and end > selected_start
            for selected_start, selected_end, _ in selected
        ):
            continue
        seen.add(normalized)
        selected.append((start, end, surface))
        if len(selected) == MAX_EVIDENCE_TARGETS:
            break

    directional_relationship = bool(
        len(selected) >= 2
        and _DIRECTIONAL_RELATIONSHIP_PREDICATE.search(text[selected[0][1] : selected[1][0]])
    )
    relationship_request = bool(
        turn.relationship
        or _RELATIONSHIP_REQUEST.search(turn.standalone_question)
        or directional_relationship
    )
    trusted_user_texts = tuple(
        f" {normalize_search_query(value)} " for value in turn.trusted_user_texts
    )
    return tuple(
        EvidenceTarget(
            target_id=f"T{index}",
            query_surface_span=surface,
            role=(
                EvidenceTargetRole.FACET
                if relationship_request and index > 1
                else EvidenceTargetRole.SUBJECT
            ),
            absence_checkable=any(
                f" {normalize_search_query(surface)} " in trusted_text
                for trusted_text in trusted_user_texts
            ),
        )
        for index, (_start, _end, surface) in enumerate(selected, start=1)
    )


_ESTABLISHED_ANSWER_PATTERNS = (
    re.compile(r"\b(?:the answer is|we know that)\b", re.IGNORECASE),
    re.compile(
        r"\bit is (?:certain|clear|established|proven) that\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sources?|evidence) (?:confirm|confirms|prove|proves|show|shows) that\b",
        re.IGNORECASE,
    ),
    re.compile(r"\[Source\s+\d+\]", re.IGNORECASE),
)


def _contains_established_answer_claim(value: str) -> bool:
    return any(pattern.search(value) for pattern in _ESTABLISHED_ANSWER_PATTERNS)


CatalogInput = (
    Sequence[DocumentCatalogEntry | Mapping[str, object]]
    | Mapping[str, str | Mapping[str, object] | DocumentCatalogEntry]
)


def _coerce_catalog(catalog: CatalogInput) -> tuple[DocumentCatalogEntry, ...]:
    if isinstance(catalog, Mapping):
        entries: list[DocumentCatalogEntry] = []
        for ordinal, (document_id, value) in enumerate(catalog.items()):
            if isinstance(value, DocumentCatalogEntry):
                entry = value
            elif isinstance(value, Mapping):
                payload = dict(value)
                payload.setdefault("document_id", document_id)
                payload.setdefault("corpus_ordinal", ordinal)
                entry = DocumentCatalogEntry.model_validate(payload)
            else:
                entry = DocumentCatalogEntry(
                    document_id=document_id,
                    chapter_title=str(value),
                    corpus_ordinal=ordinal,
                )
            entries.append(entry)
    else:
        entries = [
            (
                value
                if isinstance(value, DocumentCatalogEntry)
                else DocumentCatalogEntry.model_validate(value)
            )
            for value in catalog
        ]
    _require_unique("catalog document ID", [entry.document_id for entry in entries])
    return tuple(entries)


def _coerce_resolved_turn(value: str | ResolvedTurn) -> ResolvedTurn:
    if isinstance(value, ResolvedTurn):
        return ResolvedTurn.model_validate(value.model_dump())
    return ResolvedTurn(
        standalone_question=value,
        trusted_user_texts=(value,),
    )


def _coerce_plan(value: QuestionPlan | Mapping[str, Any]) -> QuestionPlan:
    if isinstance(value, QuestionPlan):
        return QuestionPlan.model_validate(value.model_dump())
    return QuestionPlan.model_validate(value)


def insert_original_facet(
    plan: QuestionPlan | Mapping[str, Any],
    resolved_turn: str | ResolvedTurn,
) -> QuestionPlan:
    """Insert application-owned ``F0`` as the first global retrieval lane."""

    parsed = _coerce_plan(plan)
    turn = _coerce_resolved_turn(resolved_turn)
    if any(
        facet.facet_id == F0_FACET_ID or facet.role is FacetRole.ORIGINAL for facet in parsed.facets
    ):
        raise PlanValidationError(
            "planner_owned_original",
            "planner output must not provide F0 or an original-role facet",
        )
    if len(parsed.facets) > MAX_ADDED_SEARCH_FACETS:
        raise PlanValidationError(
            "too_many_facets",
            f"at most {MAX_ADDED_SEARCH_FACETS} planner-added facets are allowed",
        )
    if len(turn.standalone_question) > MAX_ORIGINAL_QUERY_CHARS:
        raise PlanValidationError(
            "original_query_too_long",
            f"the unchanged F0 query exceeds {MAX_ORIGINAL_QUERY_CHARS} characters",
        )

    original = SearchFacet(
        facet_id=F0_FACET_ID,
        requirement_ids=tuple(requirement.requirement_id for requirement in parsed.requirements),
        role=FacetRole.ORIGINAL,
        search_query=turn.standalone_question,
        document_hints=(),
    )
    payload = parsed.model_dump()
    payload["facets"] = (original, *parsed.facets)
    return QuestionPlan.model_validate(payload)


def _lineage_stage_role_signature(
    question: str,
    requirement: AnswerRequirement,
    facet: SearchFacet,
) -> frozenset[str]:
    """Return the stage-specific vocabulary that distinguishes one lineage role."""

    question_tokens = meaningful_query_tokens(question)
    handoff = requirement.institutional_handoff
    handoff_text = (
        " ".join(
            (
                handoff.bearer,
                handoff.inherited_capacity,
                handoff.transfer_mechanism,
                handoff.outgoing_capacity,
            )
        )
        if handoff is not None
        else ""
    )
    stage_tokens = meaningful_query_tokens(
        f"{requirement.label} {facet.search_query} {handoff_text}"
    )
    return frozenset(
        token
        for token in stage_tokens - question_tokens
        if token not in _LINEAGE_STAGE_ROLE_GENERIC_TOKENS
        and not token.isdigit()
    )


def _lineage_endpoint_tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in meaningful_query_tokens(value)
        if token not in _LINEAGE_STAGE_ROLE_GENERIC_TOKENS
        and not token.isdigit()
    )


def _singular_role_token(value: str) -> str:
    if len(value) > 5 and value.endswith("ies"):
        return f"{value[:-3]}y"
    if len(value) > 5 and value.endswith(("ches", "shes", "sses", "xes", "zes")):
        return value[:-2]
    if len(value) > 4 and value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def _role_token_matches(left: str, right: str) -> bool:
    left_root = _singular_role_token(left)
    right_root = _singular_role_token(right)
    if left_root == right_root:
        return True
    shorter, longer = sorted((left_root, right_root), key=len)
    return len(shorter) >= 5 and longer.startswith(shorter)


def _role_token_overlap(
    intended_tokens: frozenset[str],
    descriptor_tokens: frozenset[str],
) -> frozenset[str]:
    return frozenset(
        intended
        for intended in intended_tokens
        if any(
            _role_token_matches(intended, descriptor)
            for descriptor in descriptor_tokens
        )
    )


def _document_role_tokens(entry: DocumentCatalogEntry) -> frozenset[str]:
    return meaningful_query_tokens(
        " ".join((entry.chapter_title, *entry.role_terms))
    )


def _stage_role_tokens(
    requirement: AnswerRequirement,
    facet: SearchFacet,
) -> frozenset[str]:
    handoff = requirement.institutional_handoff
    handoff_text = (
        " ".join(
            (
                handoff.bearer,
                handoff.inherited_capacity,
                handoff.transfer_mechanism,
                handoff.outgoing_capacity,
            )
        )
        if handoff is not None
        else ""
    )
    generic_tokens = (
        _LINEAGE_HANDOFF_GENERIC_TOKENS
        if handoff is not None
        else _LINEAGE_STAGE_ROLE_GENERIC_TOKENS
    )
    return frozenset(
        token
        for token in meaningful_query_tokens(
            f"{requirement.label} {facet.search_query} {handoff_text}"
        )
        if token not in generic_tokens
        and not token.isdigit()
    )


def _causal_driver_tokens(question: str) -> frozenset[str]:
    match = _CAUSAL_ENGINE_PATTERN.search(question)
    if match is None:
        return frozenset()
    return frozenset(
        token
        for token in meaningful_query_tokens(match.group("driver"))
        if token not in _CAUSAL_DRIVER_NOISE_TOKENS
        and token not in _LINEAGE_STAGE_ROLE_GENERIC_TOKENS
        and not token.isdigit()
    )


def _early_causal_origin_entries(
    turn: ResolvedTurn,
    catalog: Sequence[DocumentCatalogEntry],
) -> tuple[DocumentCatalogEntry, ...]:
    """Return the validator's bounded earliest driver-bearing documents."""

    driver_tokens = _causal_driver_tokens(turn.standalone_question)
    profiled_catalog = tuple(entry for entry in catalog if entry.role_terms)
    if not driver_tokens or not profiled_catalog:
        return ()
    narrative_catalog = tuple(
        entry
        for entry in profiled_catalog
        if _NUMBERED_NARRATIVE_DOCUMENT_PATTERN.search(
            f"{entry.document_id} {entry.chapter_title}"
        )
    )
    return tuple(
        entry
        for entry in sorted(
            narrative_catalog or profiled_catalog,
            key=lambda item: item.corpus_ordinal,
        )
        if _role_token_overlap(driver_tokens, _document_role_tokens(entry))
    )[:_MAX_EARLY_ORIGIN_ROLE_MATCHES]


def _validate_broad_document_roles(
    turn: ResolvedTurn,
    catalog: Sequence[DocumentCatalogEntry],
    ordered_requirements: Sequence[AnswerRequirement],
    dedicated_stage_facets_by_requirement: Mapping[str, Sequence[SearchFacet]],
) -> None:
    """Ground live broad-stage hints in bounded corpus-derived role tokens."""

    profiled_catalog = tuple(entry for entry in catalog if entry.role_terms)
    if not profiled_catalog:
        return
    catalog_by_id = {entry.document_id: entry for entry in profiled_catalog}
    ordered_facets = [
        dedicated_stage_facets_by_requirement[requirement.requirement_id][0]
        for requirement in ordered_requirements
    ]
    for requirement, facet in zip(
        ordered_requirements,
        ordered_facets,
        strict=True,
    ):
        if not facet.document_hints:
            raise PlanValidationError(
                "document_role_mismatch",
                "every live broad stage requires an exact profiled-document hint",
            )
        primary_entry = catalog_by_id.get(facet.document_hints[0])
        if primary_entry is None:
            raise PlanValidationError(
                "document_role_mismatch",
                "a broad stage's primary hint lacks a local role profile",
            )
        intended_tokens = _stage_role_tokens(requirement, facet)
        if not intended_tokens or not _role_token_overlap(
            intended_tokens,
            _document_role_tokens(primary_entry),
        ):
            raise PlanValidationError(
                "document_role_mismatch",
                "a broad stage's primary document does not contain its "
                "proposed actor, institution, mechanism, or period role",
            )

    early_origin_entries = _early_causal_origin_entries(
        turn,
        profiled_catalog,
    )
    if not early_origin_entries:
        return
    early_origin_ids = {
        entry.document_id for entry in early_origin_entries
    }
    if ordered_facets[0].document_hints[0] not in early_origin_ids:
        raise PlanValidationError(
            "broad_origin_not_preserved",
            "a book-spanning causal sequence must ground its origin in the "
            "earliest corpus documents that contain the named driver",
        )


def _repair_broad_origin_plan(
    plan: QuestionPlan | Mapping[str, Any],
    resolved_turn: str | ResolvedTurn,
    document_catalog: CatalogInput,
) -> QuestionPlan | None:
    """Replace only a rejected broad plan's late origin hint.

    The initial validator reaches ``broad_origin_not_preserved`` only after the
    plan's structure, query provenance, requirement mapping, stage roles, and
    document-role matches have passed.  This bounded repair therefore preserves
    every requirement and query, promotes one locally profiled early
    driver-bearing document into the existing origin facet, and leaves the
    complete validator to accept or reject the result.
    """

    parsed = _coerce_plan(plan)
    turn = _coerce_resolved_turn(resolved_turn)
    deterministic_traits = set(route_question(turn))
    if (
        RouteTrait.BROAD_SYNTHESIS not in deterministic_traits
        or RouteTrait.LONG_INSTITUTIONAL_LINEAGE in deterministic_traits
    ):
        return None

    profiled_catalog = tuple(
        entry for entry in _coerce_catalog(document_catalog) if entry.role_terms
    )
    if not profiled_catalog:
        return None

    ordered_requirements = sorted(
        parsed.requirements,
        key=lambda requirement: requirement.order,
    )
    if not ordered_requirements:
        return None
    first_requirement = ordered_requirements[0]
    origin_facets = tuple(
        facet
        for facet in parsed.facets
        if facet.role is FacetRole.ORIGIN
        and facet.requirement_ids == (first_requirement.requirement_id,)
    )
    if len(origin_facets) != 1:
        return None
    origin_facet = origin_facets[0]

    matching_origins = _early_causal_origin_entries(
        turn,
        profiled_catalog,
    )
    stage_tokens = _stage_role_tokens(first_requirement, origin_facet)
    replacement = next(
        (
            entry
            for entry in matching_origins
            if _role_token_overlap(
                stage_tokens,
                _document_role_tokens(entry),
            )
        ),
        None,
    )
    if replacement is None:
        return None

    repaired_hints = (
        replacement.document_id,
        *(
            hint
            for hint in origin_facet.document_hints
            if hint != replacement.document_id
        ),
    )[:MAX_DOCUMENT_HINTS_PER_FACET]
    if repaired_hints == origin_facet.document_hints:
        return None

    repaired_origin = SearchFacet.model_validate(
        {
            **origin_facet.model_dump(),
            "document_hints": repaired_hints,
        }
    )
    return QuestionPlan.model_validate(
        {
            **parsed.model_dump(),
            "facets": tuple(
                repaired_origin if facet.facet_id == origin_facet.facet_id else facet
                for facet in parsed.facets
            ),
        }
    )


def _validate_long_lineage_stage_roles(
    _parsed: QuestionPlan,
    turn: ResolvedTurn,
    catalog: Sequence[DocumentCatalogEntry],
    ordered_requirements: Sequence[AnswerRequirement],
    dedicated_stage_facets_by_requirement: Mapping[str, Sequence[SearchFacet]],
) -> None:
    """Enforce endpoint-bound bearers, carried capacity, and catalog order."""

    ordered_facets = [
        dedicated_stage_facets_by_requirement[requirement.requirement_id][0]
        for requirement in ordered_requirements
    ]
    handoffs = [
        requirement.institutional_handoff
        for requirement in ordered_requirements
    ]
    if any(handoff is None for handoff in handoffs):
        raise PlanValidationError(
            "lineage_handoff_invalid",
            "every institutional-lineage stage must declare its bearer, "
            "inherited capacity, transfer mechanism, and outgoing capacity",
        )
    typed_handoffs = [
        handoff
        for handoff in handoffs
        if handoff is not None
    ]
    normalized_bearers = [
        normalize_search_query(handoff.bearer)
        for handoff in typed_handoffs
    ]
    if len(normalized_bearers) != len(set(normalized_bearers)):
        raise PlanValidationError(
            "lineage_handoff_invalid",
            "each institutional-lineage stage requires a distinct bearer",
        )
    for handoff in typed_handoffs:
        for field_value in (
            handoff.inherited_capacity,
            handoff.transfer_mechanism,
            handoff.outgoing_capacity,
        ):
            if not {
                token
                for token in meaningful_query_tokens(field_value)
                if token not in _LINEAGE_HANDOFF_GENERIC_TOKENS
                and not token.isdigit()
            }:
                raise PlanValidationError(
                    "lineage_handoff_invalid",
                    "institutional capacities and transfer mechanisms must "
                    "name concrete, non-generic historical functions",
                )
    for predecessor, successor in zip(
        typed_handoffs,
        typed_handoffs[1:],
        strict=False,
    ):
        if normalize_search_query(
            predecessor.outgoing_capacity
        ) != normalize_search_query(successor.inherited_capacity):
            raise PlanValidationError(
                "lineage_handoff_invalid",
                "each stage's outgoing capacity must exactly become the next "
                "stage's inherited capacity",
            )

    endpoint_match = _START_END_PATTERN.search(turn.standalone_question)
    if endpoint_match is not None:
        origin_tokens = _lineage_endpoint_tokens(
            endpoint_match.group("start")
        )
        endpoint_tokens = _lineage_endpoint_tokens(
            endpoint_match.group("end")
        )
        first_bearer_tokens = _lineage_endpoint_tokens(
            typed_handoffs[0].bearer
        )
        last_bearer_tokens = _lineage_endpoint_tokens(
            typed_handoffs[-1].bearer
        )
        if (
            not origin_tokens
            or not endpoint_tokens
            or not origin_tokens.intersection(first_bearer_tokens)
            or not endpoint_tokens.intersection(last_bearer_tokens)
        ):
            raise PlanValidationError(
                "lineage_handoff_invalid",
                "the first and last institutional bearers must bind to the "
                "question's stated origin and endpoint",
            )

    signatures = [
        _lineage_stage_role_signature(
            turn.standalone_question,
            requirement,
            facet,
        )
        for requirement, facet in zip(
            ordered_requirements,
            ordered_facets,
            strict=True,
        )
    ]
    for index, signature in enumerate(signatures):
        other_terms = frozenset().union(
            *(
                other_signature
                for other_index, other_signature in enumerate(signatures)
                if other_index != index
            )
        )
        if not signature or not signature - other_terms:
            raise PlanValidationError(
                "lineage_stage_role_invalid",
                "each institutional-lineage stage must name vocabulary unique "
                "to its historical bearer, transfer, regime, or mechanism",
            )

    if not catalog:
        return
    catalog_ordinal_by_id = {
        entry.document_id: entry.corpus_ordinal for entry in catalog
    }
    primary_ordinals: list[int] = []
    for facet in ordered_facets:
        if not facet.document_hints:
            raise PlanValidationError(
                "lineage_stage_role_invalid",
                "each institutional-lineage stage requires at least one exact "
                "eligible-document hint",
            )
        primary_ordinals.append(
            min(catalog_ordinal_by_id[hint] for hint in facet.document_hints)
        )
    if any(
        current <= previous
        for previous, current in zip(
            primary_ordinals,
            primary_ordinals[1:],
            strict=False,
        )
    ):
        raise PlanValidationError(
            "lineage_stage_role_invalid",
            "institutional-lineage stage document hints must advance in "
            "strict corpus order",
        )


def validate_question_plan(
    plan: QuestionPlan | Mapping[str, Any],
    resolved_turn: str | ResolvedTurn,
    document_catalog: CatalogInput = (),
) -> QuestionPlan:
    """Validate planner output and return the application-finalized plan.

    Contextual checks cover catalog identity, query drift, trusted targets,
    requirement coverage, and the application-owned original lane.
    """

    parsed = _coerce_plan(plan)
    turn = _coerce_resolved_turn(resolved_turn)
    catalog = _coerce_catalog(document_catalog)
    deterministic_traits = set(route_question(turn))
    long_lineage = (
        RouteTrait.LONG_INSTITUTIONAL_LINEAGE in deterministic_traits
    )
    if not long_lineage and any(
        requirement.institutional_handoff is not None
        for requirement in parsed.requirements
    ):
        raise PlanValidationError(
            "lineage_handoff_route_mismatch",
            "institutional handoff metadata is allowed only for the "
            "application-owned long-lineage route",
        )

    if parsed.premises and RouteTrait.PREMISE_SENSITIVE not in deterministic_traits:
        raise PlanValidationError(
            "premise_route_mismatch",
            "planner premises require the application-owned premise-sensitive route",
        )
    if any(premise.framing_facet_id is None for premise in parsed.premises):
        raise PlanValidationError(
            "missing_premise_framing",
            "every planner premise requires a distinct framing facet",
        )
    if any(
        facet.facet_id == F0_FACET_ID or facet.role is FacetRole.ORIGINAL for facet in parsed.facets
    ):
        raise PlanValidationError(
            "planner_owned_original",
            "planner output must not provide F0 or an original-role facet",
        )
    if len(parsed.facets) > MAX_ADDED_SEARCH_FACETS:
        raise PlanValidationError(
            "too_many_facets",
            f"at most {MAX_ADDED_SEARCH_FACETS} planner-added facets are allowed",
        )

    mapped_requirements = {
        requirement_id for facet in parsed.facets for requirement_id in facet.requirement_ids
    }
    missing_mappings = [
        requirement.requirement_id
        for requirement in parsed.requirements
        if requirement.requirement_id not in mapped_requirements
    ]
    if missing_mappings:
        raise PlanValidationError(
            "missing_requirement_mapping",
            f"requirements lack planner-added facets: {missing_mappings!r}",
        )

    catalog_by_id = {entry.document_id: entry for entry in catalog}
    question_tokens = meaningful_query_tokens(turn.standalone_question)
    normalized_queries = {normalize_search_query(turn.standalone_question)}
    for facet in parsed.facets:
        unknown_hints = [hint for hint in facet.document_hints if hint not in catalog_by_id]
        if unknown_hints:
            raise PlanValidationError(
                "unknown_document_hint",
                f"facet {facet.facet_id!r} has unknown document hints: {unknown_hints!r}",
            )

        normalized_query = normalize_search_query(facet.search_query)
        if normalized_query in normalized_queries:
            raise PlanValidationError(
                "duplicate_query",
                f"facet {facet.facet_id!r} duplicates another search query",
            )
        normalized_queries.add(normalized_query)

        allowed_tokens = set(question_tokens)
        for hint in facet.document_hints:
            catalog_entry = catalog_by_id[hint]
            allowed_tokens.update(
                meaningful_query_tokens(
                    " ".join(
                        (
                            catalog_entry.chapter_title,
                            *catalog_entry.role_terms,
                        )
                    )
                )
            )
        if not meaningful_query_tokens(facet.search_query) & allowed_tokens:
            raise PlanValidationError(
                "query_drift",
                f"facet {facet.facet_id!r} shares no meaningful token with "
                "the question or a selected catalog title",
            )
        if _contains_established_answer_claim(facet.search_query):
            raise PlanValidationError(
                "established_answer_claim",
                f"facet {facet.facet_id!r} is framed as an established answer",
            )

    local_targets = extract_trusted_targets(turn)
    local_targets_by_surface = {
        normalize_search_query(target.query_surface_span): target for target in local_targets
    }
    for target in parsed.targets:
        trusted = local_targets_by_surface.get(normalize_search_query(target.query_surface_span))
        if trusted is None:
            raise PlanValidationError(
                "untrusted_target",
                f"target {target.target_id!r} is not a trusted question surface",
            )
        if target.role is not trusted.role or target.absence_checkable != trusted.absence_checkable:
            raise PlanValidationError(
                "untrusted_target_classification",
                f"target {target.target_id!r} changes a local trust decision",
            )

    if RouteTrait.BROAD_SYNTHESIS in deterministic_traits:
        requirement_ids = {
            requirement.requirement_id for requirement in parsed.requirements
        }
        dedicated_stage_facets = [
            facet
            for facet in parsed.facets
            if facet.role
            in {
                FacetRole.ORIGIN,
                FacetRole.TRANSITION,
                FacetRole.MECHANISM,
                FacetRole.ENDPOINT,
            }
            and len(facet.requirement_ids) == 1
        ]
        dedicated_stage_facets_by_requirement = {
            requirement_id: [
                facet
                for facet in dedicated_stage_facets
                if facet.requirement_ids == (requirement_id,)
            ]
            for requirement_id in requirement_ids
        }
        ordered_requirements = sorted(
            parsed.requirements,
            key=lambda requirement: requirement.order,
        )
        ordered_stage_roles = [
            dedicated_stage_facets_by_requirement[
                requirement.requirement_id
            ][0].role
            for requirement in ordered_requirements
            if len(
                dedicated_stage_facets_by_requirement[
                    requirement.requirement_id
                ]
            )
            == 1
        ]
        stage_chain_valid = (
            len(ordered_stage_roles) == len(ordered_requirements)
            and ordered_stage_roles[0] is FacetRole.ORIGIN
            and ordered_stage_roles[-1] is FacetRole.ENDPOINT
            and all(
                role in {FacetRole.TRANSITION, FacetRole.MECHANISM}
                for role in ordered_stage_roles[1:-1]
            )
        )
        if long_lineage and (
            len(parsed.requirements)
            != LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS
            or len(dedicated_stage_facets)
            != LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS
            or any(
                len(facets) != 1
                for facets in dedicated_stage_facets_by_requirement.values()
            )
            or not stage_chain_valid
        ):
            raise PlanValidationError(
                "lineage_stage_cardinality_mismatch",
                "a long institutional lineage requires exactly eight "
                "dedicated ordered stages: one origin, six distinct "
                "transition-or-mechanism roles, and one endpoint",
            )
        if (
            len(parsed.requirements) < MIN_BROAD_STAGE_REQUIREMENTS
            or any(
                len(facets) != 1
                for facets in dedicated_stage_facets_by_requirement.values()
            )
            or not stage_chain_valid
        ):
            raise PlanValidationError(
                "broad_plan_under_decomposed",
                "broad synthesis requires at least five dedicated, ordered "
                "narrative-stage requirements: origin, at least three "
                "transition-or-mechanism stages, and endpoint",
            )
        _validate_broad_document_roles(
            turn,
            catalog,
            ordered_requirements,
            dedicated_stage_facets_by_requirement,
        )
        if long_lineage:
            _validate_long_lineage_stage_roles(
                parsed,
                turn,
                catalog,
                ordered_requirements,
                dedicated_stage_facets_by_requirement,
            )

    payload = parsed.model_dump()
    payload.update(
        traits=tuple(trait for trait in RouteTrait if trait in deterministic_traits),
        targets=local_targets,
        planner_used=True,
        fallback_reason=None,
    )
    finalized = insert_original_facet(QuestionPlan.model_validate(payload), turn)
    if finalized.facets[0].search_query != turn.standalone_question:
        raise PlanValidationError(
            "original_query_changed",
            "F0 must preserve the standalone question byte for byte",
        )
    return finalized


def _materialize_planner_question_plan(
    proposal: PlannerQuestionPlan | Mapping[str, Any],
) -> QuestionPlan:
    """Materialize the provider-owned shape before local semantic validation."""

    parsed = (
        PlannerQuestionPlan.model_validate(proposal.model_dump())
        if isinstance(proposal, PlannerQuestionPlan)
        else PlannerQuestionPlan.model_validate(proposal)
    )
    plan = QuestionPlan(
        requirements=tuple(
            AnswerRequirement(
                requirement_id=requirement.requirement_id,
                label=requirement.label,
                order=order,
                required=True,
                institutional_handoff=requirement.institutional_handoff,
            )
            for order, requirement in enumerate(parsed.requirements)
        ),
        facets=tuple(
            SearchFacet(
                facet_id=facet.facet_id,
                requirement_ids=facet.requirement_ids,
                role=facet.role,
                search_query=facet.search_query,
                document_hints=facet.document_hints,
            )
            for facet in parsed.facets
        ),
        premises=tuple(
            PremiseHypothesis(
                premise_id=premise.premise_id,
                proposition=premise.proposition,
                support_facet_id=premise.support_facet_id,
                counter_facet_id=premise.counter_facet_id,
                framing_facet_id=premise.framing_facet_id,
            )
            for premise in parsed.premises
        ),
    )
    return plan


def validate_planner_question_plan(
    proposal: PlannerQuestionPlan | Mapping[str, Any],
    resolved_turn: str | ResolvedTurn,
    document_catalog: CatalogInput = (),
) -> QuestionPlan:
    """Materialize and semantically validate one provider proposal.

    The provider controls search labels, facets, and premise hypotheses.  The
    application derives requirement order and owns routing traits, trusted
    targets, F0, execution status, and fallback state.
    """

    return validate_question_plan(
        _materialize_planner_question_plan(proposal),
        resolved_turn,
        document_catalog,
    )


_START_END_PATTERN = re.compile(
    r"\bfrom\s+(?P<start>.+?)\s+to\s+(?P<end>.+?)(?:[?.!]|$)",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_PATTERN = re.compile(
    r"\s*;\s*|\?\s+(?=\w)|"
    r"\s+(?:and|also)\s+(?=(?:what|why|how|when|where|who|which|"
    r"compare|identify|explain|describe)\b)",
    re.IGNORECASE,
)
_TRANSITIVE_RELATIONSHIP_PATTERN = re.compile(
    r"^\s*(?:(?:how|why|where|when|what)\s+)?"
    r"(?:does|do|did|can|could|would)\s+"
    r"(?:(?:the|this|that)\s+)?(?:manuscript|book|text|author|account)\s+"
    rf"(?P<predicate>{_RELATIONAL_VERB})\s+"
    r"(?P<left>.+?)\s+to\s+(?P<right>.+?)(?:[?.!]|$)",
    re.IGNORECASE,
)
_SUBJECT_RELATIONSHIP_PATTERN = re.compile(
    rf"^\s*(?:(?:how|why|where|when|what)\s+)?"
    r"(?:does|do|did|is|are|was|were|has|have|had|can|could|would)\s+"
    rf"(?P<left>.+?)\s+(?P<predicate>{_RELATIONAL_VERB})\s+to\s+"
    r"(?P<right>.+?)(?:[?.!]|$)",
    re.IGNORECASE,
)

_DIMENSION_ROLE = {
    "cause": FacetRole.MECHANISM,
    "mechanism": FacetRole.MECHANISM,
    "stage": FacetRole.TRANSITION,
    "comparison": FacetRole.BROADER_RELATED,
    "consequence": FacetRole.ENDPOINT,
}


def _bounded_text(value: str, limit: int = MAX_SEARCH_QUERY_CHARS) -> str:
    collapsed = " ".join(value.split()).strip(" ,;")
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip()


def _fallback_requirement(
    index: int,
    label: str,
    *,
    institutional_handoff: InstitutionalHandoff | None = None,
) -> AnswerRequirement:
    return AnswerRequirement(
        requirement_id=f"R{index}",
        label=_bounded_text(label),
        order=index - 1,
        required=True,
        institutional_handoff=institutional_handoff,
    )


def _fallback_facet(
    index: int,
    requirement: AnswerRequirement,
    role: FacetRole,
    query: str,
) -> SearchFacet:
    return SearchFacet(
        facet_id=f"F{index}",
        requirement_ids=(requirement.requirement_id,),
        role=role,
        search_query=_bounded_text(query),
        document_hints=(),
    )


def _coordinated_parts(question: str) -> tuple[str, ...]:
    parts = tuple(
        _bounded_text(part.strip(" ?"))
        for part in _CLAUSE_SPLIT_PATTERN.split(question)
        if part.strip(" ?")
    )
    if len(parts) > 1:
        return parts[:MAX_ADDED_SEARCH_FACETS]

    dimensions: list[str] = []
    for match in _MULTIPLE_DIMENSIONS.finditer(question.casefold()):
        singular = match.group(0).rstrip("s")
        if singular not in dimensions:
            dimensions.append(singular)
    if len(dimensions) > 1:
        return tuple(dimensions[:MAX_ADDED_SEARCH_FACETS])
    return ()


def _bounded_between_relationship_parts(
    question: str,
) -> tuple[str, str, str, str | None] | None:
    match = _BETWEEN_RELATIONSHIP_PATTERN.fullmatch(question)
    if match is None:
        match = _DIRECTIONAL_BETWEEN_RELATIONSHIP_PATTERN.fullmatch(question)
        if match is None:
            return None

    left = _bounded_text(match.group("left").strip(" ,;:?"))
    right = _bounded_text(match.group("right").strip(" ,;:?"))
    predicate = _bounded_text(match.group("predicate"))
    context = _bounded_text((match.group("context") or "").strip()) or None
    if (
        not left
        or not right
        or re.search(r"\band\b", left, flags=re.IGNORECASE)
        or re.search(r"\band\b", right, flags=re.IGNORECASE)
        or _AMBIGUOUS_RELATIONSHIP_OPERAND_TAIL.search(left)
        or _AMBIGUOUS_RELATIONSHIP_OPERAND_TAIL.search(right)
        or normalize_search_query(left) == normalize_search_query(right)
    ):
        return None
    relationship_label = " ".join(
        part
        for part in (
            f"Connection between {left} and {right}",
            context,
        )
        if part
    )
    relationship_query = " ".join(part for part in (left, right, predicate, context) if part)
    context_tail = (
        _BOUNDED_RELATIONSHIP_CONTEXT_PREFIX.sub("", context, count=1)
        if context is not None
        else ""
    )
    if (
        _AMBIGUOUS_RELATIONSHIP_CONTEXT_TAIL.search(context_tail)
        or len(relationship_label) > MAX_SEARCH_QUERY_CHARS
        or len(relationship_query) > MAX_SEARCH_QUERY_CHARS
    ):
        return None
    return left, right, predicate, context


def _relational_parts(
    question: str,
) -> tuple[str, str, str, str | None] | None:
    """Extract two explicit operands, their predicate, and bounded context."""

    bounded_between = _bounded_between_relationship_parts(question)
    if bounded_between is not None:
        return bounded_between
    if (
        _BETWEEN_RELATIONSHIP_PATTERN.fullmatch(question) is not None
        or _DIRECTIONAL_BETWEEN_RELATIONSHIP_PATTERN.fullmatch(question) is not None
    ):
        return None
    if len(re.findall(r"\bto\b", question, flags=re.IGNORECASE)) != 1:
        return None
    match = _TRANSITIVE_RELATIONSHIP_PATTERN.search(question)
    if match is None:
        match = _SUBJECT_RELATIONSHIP_PATTERN.search(question)
    if match is None:
        return None

    left = _bounded_text(match.group("left").strip(" ,;:?"))
    right = _bounded_text(match.group("right").strip(" ,;:?"))
    predicate = _bounded_text(match.group("predicate"))
    if (
        not left
        or not right
        or re.search(r"\band\b", left, flags=re.IGNORECASE)
        or re.search(r"\band\b", right, flags=re.IGNORECASE)
        or normalize_search_query(left) == normalize_search_query(right)
    ):
        return None
    return left, right, predicate, None


def _long_lineage_fallback_stages(
    question: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[tuple[AnswerRequirement, ...], tuple[SearchFacet, ...]]:
    """Build the full capacity-aware lineage shape when the planner is unavailable."""

    start_label = start or "the earliest institutional bearer"
    end_label = end or "the latest institutional system"
    labels_roles_queries_bearers = (
        (
            f"Founding mandate at {start_label}",
            FacetRole.ORIGIN,
            f"founding charter mandate {start_label}",
            start_label,
        ),
        (
            f"First successor after {start_label}",
            FacetRole.TRANSITION,
            f"successor compact inheritance {start_label}",
            f"first successor institution after {start_label}",
        ),
        (
            "Transfer of authority into a new bearer",
            FacetRole.MECHANISM,
            f"authority transfer replacement {start_label} {end_label}",
            "successor public authority",
        ),
        (
            "Fiscal machinery that consolidated the lineage",
            FacetRole.MECHANISM,
            f"fiscal finance revenue machinery {start_label} {end_label}",
            "fiscal administrative institution",
        ),
        (
            "Intermediate political order carrying the inherited powers",
            FacetRole.TRANSITION,
            f"political order inherited powers {start_label} {end_label}",
            "intermediate political order",
        ),
        (
            "Later reorganization of public authority",
            FacetRole.MECHANISM,
            f"public authority reorganization bureaucracy {end_label}",
            "later public administrative body",
        ),
        (
            f"Public-private integration toward {end_label}",
            FacetRole.TRANSITION,
            f"public private integration contracts {end_label}",
            f"public-private predecessor of {end_label}",
        ),
        (
            f"Mature operating structure at {end_label}",
            FacetRole.ENDPOINT,
            f"operating structure persistence legacy {end_label}",
            end_label,
        ),
    )
    capacities = (
        f"founding mandate associated with {start_label}",
        "chartered governing authority",
        "successor public authority",
        "delegated fiscal authority",
        "centralized administrative capacity",
        "reorganized public authority",
        "public-private contracting capacity",
        f"mature operating capacity associated with {end_label}",
        f"continuing institutional capacity at {end_label}",
    )
    transfer_mechanisms = (
        "founding or charter creates the first institutional mandate",
        "succession transfers the founding mandate to a new bearer",
        "legal transfer converts succession into public authority",
        "fiscal machinery consolidates delegated authority",
        "political reorganization centralizes administrative capacity",
        "bureaucratic reorganization preserves authority in a later body",
        "contracting integrates public authority with private operators",
        "the endpoint system consolidates the inherited operating capacity",
    )
    compact_question = (
        ""
        if start is not None or end is not None
        else _bounded_text(question, limit=48)
    )
    requirements = tuple(
        _fallback_requirement(
            index,
            label,
            institutional_handoff=InstitutionalHandoff(
                bearer=_bounded_text(
                    bearer,
                    limit=MAX_INSTITUTIONAL_HANDOFF_CHARS,
                ),
                inherited_capacity=_bounded_text(
                    capacities[index - 1],
                    limit=MAX_INSTITUTIONAL_HANDOFF_CHARS,
                ),
                transfer_mechanism=_bounded_text(
                    transfer_mechanisms[index - 1],
                    limit=MAX_INSTITUTIONAL_HANDOFF_CHARS,
                ),
                outgoing_capacity=_bounded_text(
                    capacities[index],
                    limit=MAX_INSTITUTIONAL_HANDOFF_CHARS,
                ),
            ),
        )
        for index, (label, _role, _query, bearer) in enumerate(
            labels_roles_queries_bearers,
            start=1,
        )
    )
    facets = tuple(
        _fallback_facet(
            index,
            requirements[index - 1],
            role,
            " ".join(part for part in (query, compact_question) if part),
        )
        for index, (_label, role, query, _bearer) in enumerate(
            labels_roles_queries_bearers,
            start=1,
        )
    )
    return requirements, facets


def deterministic_fallback_plan(
    resolved_turn: str | ResolvedTurn,
    *,
    fallback_reason: str | None = None,
) -> QuestionPlan:
    """Build a bounded no-model plan using the design's fixed fallback order."""

    turn = _coerce_resolved_turn(resolved_turn)
    question = turn.standalone_question
    traits = route_question(turn)
    targets = extract_trusted_targets(turn)
    requirements: tuple[AnswerRequirement, ...]
    facets: tuple[SearchFacet, ...]
    premises: tuple[PremiseHypothesis, ...] = ()

    span = _START_END_PATTERN.search(question)
    relational = _relational_parts(question)
    if span:
        start = _bounded_text(span.group("start"))
        end = _bounded_text(span.group("end"))
        context = _bounded_text(question[: span.start()].strip(" ,;:?"))
        relationship = _bounded_text(turn.relationship or f"{start} {end}")
        if RouteTrait.LONG_INSTITUTIONAL_LINEAGE in traits:
            requirements, facets = _long_lineage_fallback_stages(
                question,
                start=start,
                end=end,
            )
        elif RouteTrait.BROAD_SYNTHESIS in traits:
            requirements = (
                _fallback_requirement(1, start),
                _fallback_requirement(2, f"Early development after {start}"),
                _fallback_requirement(3, relationship),
                _fallback_requirement(4, f"Later transformation toward {end}"),
                _fallback_requirement(5, end),
            )
            facets = (
                _fallback_facet(
                    1,
                    requirements[0],
                    FacetRole.ORIGIN,
                    f"origin {context} {start}",
                ),
                _fallback_facet(
                    2,
                    requirements[1],
                    FacetRole.TRANSITION,
                    f"early development {start} {relationship}",
                ),
                _fallback_facet(
                    3,
                    requirements[2],
                    FacetRole.MECHANISM,
                    f"middle mechanism {start} {end} {relationship}",
                ),
                _fallback_facet(
                    4,
                    requirements[3],
                    FacetRole.TRANSITION,
                    f"later transformation {end} {relationship}",
                ),
                _fallback_facet(
                    5,
                    requirements[4],
                    FacetRole.ENDPOINT,
                    f"endpoint {context} {end}",
                ),
            )
        else:
            requirements = (
                _fallback_requirement(1, start),
                _fallback_requirement(2, relationship),
                _fallback_requirement(3, end),
            )
            facets = (
                _fallback_facet(
                    1,
                    requirements[0],
                    FacetRole.ORIGIN,
                    f"origin {context} {start}",
                ),
                _fallback_facet(
                    2,
                    requirements[1],
                    FacetRole.TRANSITION,
                    f"transition {start} {end} {relationship}",
                ),
                _fallback_facet(
                    3,
                    requirements[2],
                    FacetRole.ENDPOINT,
                    f"endpoint {context} {end}",
                ),
            )
    elif relational is not None:
        left, right, predicate, relationship_context = relational
        relationship_label = _bounded_text(
            " ".join(
                part
                for part in (
                    f"Connection between {left} and {right}",
                    relationship_context,
                )
                if part
            )
        )
        requirements = (
            _fallback_requirement(1, f"Context for {left}"),
            _fallback_requirement(2, f"Context for {right}"),
            _fallback_requirement(3, relationship_label),
        )
        facets = (
            _fallback_facet(
                1,
                requirements[0],
                FacetRole.BROADER_RELATED,
                f"{left} context",
            ),
            _fallback_facet(
                2,
                requirements[1],
                FacetRole.BROADER_RELATED,
                f"{right} context",
            ),
            _fallback_facet(
                3,
                requirements[2],
                FacetRole.MECHANISM,
                " ".join(part for part in (left, right, predicate, relationship_context) if part),
            ),
        )
    elif coordinated := _coordinated_parts(question):
        requirements = tuple(
            _fallback_requirement(index, part) for index, part in enumerate(coordinated, start=1)
        )
        facets = tuple(
            _fallback_facet(
                index,
                requirement,
                _DIMENSION_ROLE.get(
                    normalize_search_query(part).split()[0].rstrip("s"),
                    FacetRole.BROADER_RELATED,
                ),
                f"{part} {question}",
            )
            for index, (part, requirement) in enumerate(
                zip(coordinated, requirements, strict=True),
                start=1,
            )
        )
    elif RouteTrait.PREMISE_SENSITIVE in traits:
        requirements = (_fallback_requirement(1, question.strip(" ?")),)
        facets = (
            _fallback_facet(
                1,
                requirements[0],
                FacetRole.PREMISE_SUPPORT,
                f"event role {question}",
            ),
            _fallback_facet(
                2,
                requirements[0],
                FacetRole.PREMISE_COUNTER,
                f"earlier origin {question}",
            ),
            _fallback_facet(
                3,
                requirements[0],
                FacetRole.FRAMING,
                f"chronology framing {question}",
            ),
        )
        premises = (
            PremiseHypothesis(
                premise_id="P1",
                proposition=_bounded_text(question.strip(" ?")),
                support_facet_id="F1",
                counter_facet_id="F2",
                framing_facet_id="F3",
            ),
        )
    elif RouteTrait.LONG_INSTITUTIONAL_LINEAGE in traits:
        requirements, facets = _long_lineage_fallback_stages(question)
    elif RouteTrait.BROAD_SYNTHESIS in traits:
        requirements = (
            _fallback_requirement(1, "Earliest concrete origin"),
            _fallback_requirement(2, "Early institutional development"),
            _fallback_requirement(3, "Middle-period mechanism or consolidation"),
            _fallback_requirement(4, "Later transformation or normalization"),
            _fallback_requirement(5, "Latest consequences and endpoint"),
        )
        facets = (
            _fallback_facet(
                1,
                requirements[0],
                FacetRole.ORIGIN,
                f"earliest concrete origin {question}",
            ),
            _fallback_facet(
                2,
                requirements[1],
                FacetRole.TRANSITION,
                f"early institutional development {question}",
            ),
            _fallback_facet(
                3,
                requirements[2],
                FacetRole.TRANSITION,
                f"middle mechanism consolidation {question}",
            ),
            _fallback_facet(
                4,
                requirements[3],
                FacetRole.TRANSITION,
                f"later transformation normalization {question}",
            ),
            _fallback_facet(
                5,
                requirements[4],
                FacetRole.ENDPOINT,
                f"latest consequence endpoint {question}",
            ),
        )
    else:
        requirements = (_fallback_requirement(1, question.strip(" ?")),)
        facets = ()

    reason = fallback_reason.strip() if fallback_reason else None
    raw = QuestionPlan(
        traits=traits,
        requirements=requirements,
        facets=facets,
        premises=premises,
        targets=targets,
        planner_used=False,
        fallback_reason=reason,
    )
    return insert_original_facet(raw, turn)


def build_question_plan(
    resolved_turn: str | ResolvedTurn,
    planner_output: (PlannerQuestionPlan | QuestionPlan | Mapping[str, Any] | None) = None,
    document_catalog: CatalogInput = (),
    *,
    fallback_reason: str | None = None,
    validation_diagnostics: MutableMapping[str, str | None] | None = None,
) -> QuestionPlan:
    """Finalize one planner result or fall back once without retrying.

    ``fallback_reason`` lets orchestration record refusal, timeout, or low budget
    headroom without this pure layer knowing how those conditions were detected.
    """

    _record_planner_validation_code(validation_diagnostics, None)
    turn = _coerce_resolved_turn(resolved_turn)
    if planner_output is None:
        reason = fallback_reason
        if reason is None and requires_planning(turn):
            reason = "planner_unavailable"
        return deterministic_fallback_plan(turn, fallback_reason=reason)

    try:
        planner_shape = isinstance(planner_output, PlannerQuestionPlan) or (
            isinstance(planner_output, Mapping)
            and (
                planner_output.get("schema") == PLANNER_QUESTION_PLAN_SCHEMA
                or planner_output.get("schema_") == PLANNER_QUESTION_PLAN_SCHEMA
            )
        )
        if planner_shape:
            return validate_planner_question_plan(
                planner_output,
                turn,
                document_catalog,
            )
        return validate_question_plan(planner_output, turn, document_catalog)
    except PlanValidationError as error:
        if error.code == "broad_origin_not_preserved":
            try:
                raw_plan = (
                    _materialize_planner_question_plan(planner_output)
                    if planner_shape
                    else _coerce_plan(planner_output)
                )
                repaired = _repair_broad_origin_plan(
                    raw_plan,
                    turn,
                    document_catalog,
                )
                if repaired is not None:
                    finalized = validate_question_plan(
                        repaired,
                        turn,
                        document_catalog,
                    )
                    _record_planner_validation_code(
                        validation_diagnostics,
                        None,
                    )
                    return finalized
            except (PlanValidationError, ValidationError, ValueError):
                pass
        _record_planner_validation_code(
            validation_diagnostics,
            error.code,
        )
        return deterministic_fallback_plan(
            turn,
            fallback_reason=fallback_reason or "invalid_planner_output",
        )
    except (ValidationError, ValueError):
        _record_planner_validation_code(
            validation_diagnostics,
            PLAN_STRUCTURE_INVALID,
        )
        return deterministic_fallback_plan(
            turn,
            fallback_reason=fallback_reason or "invalid_planner_output",
        )


QUERY_PLANNER_INSTRUCTIONS = """\
Return a compact search proposal for the standalone question without answering it.
Return no F0 facet: the application inserts the unchanged original question.
Return no route traits, evidence targets, requirement order, execution status, or fallback state:
the application owns those fields.
Use only IDs declared in the response, and map every requirement to at least one added facet.
Prefer the smallest sufficient proposal. A single-clause request normally needs one requirement
and one to three facets. Obey the application-owned route_traits supplied in the input. When
broad_synthesis is present without long_institutional_lineage, return exactly five ordered
requirements. When long_institutional_lineage is present, return exactly eight ordered
requirements and exactly eight dedicated stage facets. The eight stages consume the complete
stage-source capacity; do not add a ninth transition facet. Give every requirement exactly one
dedicated narrative-stage facet: first an origin facet, then transition or mechanism facets for
distinct developments in the argument, and finally an endpoint facet. For a long institutional
lineage, populate institutional_handoff on every requirement. Name a distinct historical bearer,
the capacity it inherits, the mechanism that transfers or transforms that capacity, and the
capacity it passes onward. Copy each stage's outgoing_capacity exactly into the next stage's
inherited_capacity. Bind the first bearer to the origin named after "from" in the question and
the last bearer to the endpoint named after "to". The eight stages must form one carried
institutional chain, not eight merely chronological topics. A stage may describe a governing
regime, fiscal or administrative mechanism, public-private arrangement, or endpoint system only
when it also states that explicit handoff.
Give each long-lineage stage at least one exact eligible-document hint, and make those primary
hints advance in strict catalog order. Do not use generic early/middle/late labels: make each
requirement and query identify the distinct function or development it must find while staying
neutral about the answer. Each stage label and query must name the stage's distinctive
institution, actor, event, or mechanism; generic topic words shared by the whole question are not
a sufficient stage anchor.
The catalog's role_terms are bounded locally derived search-orientation tokens, not evidence.
For every broad-synthesis stage, choose a primary document hint whose role_terms or title contain
the stage's named actor, institution, mechanism, or period. For a book-spanning causal question
that asks how a named driver acts as an engine, driver, instrument, or source of an outcome, choose
the origin from the earliest eligible documents whose role terms contain that named driver.
Do not quote, paraphrase, or treat role_terms as establishing a historical claim.
Do not merge or omit independently requested parts merely to stay under four.
Keep labels and search queries terse and copy document hints only as exact catalog IDs.
For relational questions, search each named concept plus evidence that explicitly links them.
Return premise hypotheses only when premise_sensitive is present. For every factual premise, use
distinct support, counter, and framing facets. The framing facet searches for the manuscript's own
alternative chronology, origin, identity, or causal frame if the premise fails; do not state that
alternative in the plan.
Document hints must exactly match the supplied eligible catalog.
Do not state conclusions, cite sources, invent aliases, or use prior assistant answers as evidence.
Respect the version-3 limits encoded in the response schema.
"""


def question_plan_json_schema() -> dict[str, Any]:
    """Return the finalized in-memory plan schema."""

    return QuestionPlan.model_json_schema()


def planner_question_plan_json_schema() -> dict[str, Any]:
    """Return the compact provider-facing planner proposal schema."""

    return PlannerQuestionPlan.model_json_schema()


__all__ = [
    "AnswerRequirement",
    "DocumentCatalogEntry",
    "EvidenceTarget",
    "EvidenceTargetRole",
    "F0_FACET_ID",
    "FacetRole",
    "InstitutionalHandoff",
    "MAX_ADDED_QUERY_CHARS",
    "MAX_ADDED_SEARCH_FACETS",
    "LONG_INSTITUTIONAL_LINEAGE_STAGE_REQUIREMENTS",
    "MIN_BROAD_STAGE_REQUIREMENTS",
    "MAX_ORIGINAL_QUERY_CHARS",
    "MAX_INSTITUTIONAL_HANDOFF_CHARS",
    "MAX_PLANNER_FACETS",
    "MAX_PLANNER_REQUIREMENTS",
    "MAX_ANSWER_REQUIREMENTS",
    "MAX_DOCUMENT_HINTS_PER_FACET",
    "MAX_EVIDENCE_TARGETS",
    "MAX_PREMISE_HYPOTHESES",
    "MAX_SEARCH_FACETS",
    "MAX_SEARCH_QUERY_CHARS",
    "PlanValidationError",
    "PLAN_STRUCTURE_INVALID",
    "PlannerAnswerRequirement",
    "PlannerPremiseHypothesis",
    "PlannerQuestionPlan",
    "PlannerSearchFacet",
    "PLANNER_QUESTION_PLAN_SCHEMA",
    "PLANNER_SEMANTIC_VALIDATION_CODES",
    "PLANNER_VALIDATION_CODES",
    "PremiseHypothesis",
    "QUERY_PLANNER_INSTRUCTIONS",
    "QUESTION_PLAN_SCHEMA",
    "QuestionPlan",
    "RESOLVED_TURN_SCHEMA",
    "ResolvedTurn",
    "RouteTrait",
    "SearchFacet",
    "build_question_plan",
    "deterministic_fallback_plan",
    "extract_trusted_targets",
    "insert_original_facet",
    "question_plan_json_schema",
    "planner_question_plan_json_schema",
    "requires_planning",
    "route_question",
    "safe_planner_validation_code",
    "validate_question_plan",
    "validate_planner_question_plan",
]
