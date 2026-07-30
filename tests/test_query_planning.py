from __future__ import annotations

import pytest
from pydantic import ValidationError

import query_planning
from query_planning import (
    AnswerRequirement,
    DocumentCatalogEntry,
    EvidenceTarget,
    EvidenceTargetRole,
    FacetRole,
    InstitutionalHandoff,
    PlanValidationError,
    PlannerAnswerRequirement,
    PlannerPremiseHypothesis,
    PlannerQuestionPlan,
    PlannerSearchFacet,
    PremiseHypothesis,
    QuestionPlan,
    ResolvedTurn,
    RouteTrait,
    SearchFacet,
    build_question_plan,
    deterministic_fallback_plan,
    extract_trusted_targets,
    requires_planning,
    route_question,
    validate_question_plan,
)


CATALOG = (
    DocumentCatalogEntry(
        document_id="part-a.md",
        chapter_title="Formation of the Harbor Network",
        corpus_ordinal=0,
    ),
    DocumentCatalogEntry(
        document_id="part-middle.md",
        chapter_title="Development of the Harbor Network",
        corpus_ordinal=1,
    ),
    DocumentCatalogEntry(
        document_id="part-b.md",
        chapter_title="Closure of the Harbor Network",
        corpus_ordinal=2,
    ),
)

LINEAGE_CATALOG = tuple(
    DocumentCatalogEntry(
        document_id=f"lineage-{index}.md",
        chapter_title=title,
        corpus_ordinal=index,
    )
    for index, title in enumerate(
        (
            "Chartered Venture",
            "Provincial Council",
            "Assembly Tax Authority",
            "Commonwealth Office",
            "National Treasury",
            "Federal Procurement Bureau",
            "Contractor Command",
            "Data Center Network",
        ),
        start=1,
    )
)
PROFILED_LINEAGE_CATALOG = tuple(
    entry.model_copy(
        update={
            "role_terms": tuple(
                query_planning.normalize_search_query(entry.chapter_title).split()
            )
        }
    )
    for entry in LINEAGE_CATALOG
)
LINEAGE_QUESTION = (
    "Trace the institutional lineage from Alpha Consortium to Omega Network."
)
CAUSAL_SPAN_QUESTION = (
    "How does the book treat conflict as an engine of central power?"
)


def requirement(identifier: str = "R1", *, order: int = 0) -> AnswerRequirement:
    return AnswerRequirement(
        requirement_id=identifier,
        label=f"Requirement {identifier}",
        order=order,
        required=True,
    )


def facet(
    identifier: str,
    requirement_ids: tuple[str, ...],
    query: str,
    *,
    role: FacetRole = FacetRole.BROADER_RELATED,
    hints: tuple[str, ...] = (),
) -> SearchFacet:
    return SearchFacet(
        facet_id=identifier,
        requirement_ids=requirement_ids,
        role=role,
        search_query=query,
        document_hints=hints,
    )


def valid_planner_plan() -> QuestionPlan:
    return QuestionPlan(
        traits=(RouteTrait.BROAD_SYNTHESIS,),
        requirements=(
            requirement("R1", order=0),
            requirement("R2", order=1),
            requirement("R3", order=2),
            requirement("R4", order=3),
            requirement("R5", order=4),
        ),
        facets=(
            facet(
                "F1",
                ("R1",),
                "Harbor Network formation",
                role=FacetRole.ORIGIN,
                hints=("part-a.md",),
            ),
            facet(
                "F2",
                ("R2",),
                "Harbor Network development",
                role=FacetRole.TRANSITION,
                hints=("part-middle.md",),
            ),
            facet(
                "F3",
                ("R3",),
                "Harbor Network middle mechanism",
                role=FacetRole.MECHANISM,
                hints=("part-middle.md",),
            ),
            facet(
                "F4",
                ("R4",),
                "Harbor Network later development",
                role=FacetRole.TRANSITION,
                hints=("part-middle.md",),
            ),
            facet(
                "F5",
                ("R5",),
                "Harbor Network closure",
                role=FacetRole.ENDPOINT,
                hints=("part-b.md",),
            ),
        ),
    )


def valid_planner_proposal() -> PlannerQuestionPlan:
    return PlannerQuestionPlan(
        requirements=(
            PlannerAnswerRequirement(
                requirement_id="R1",
                label="Harbor Network formation",
            ),
            PlannerAnswerRequirement(
                requirement_id="R2",
                label="Harbor Network development",
            ),
            PlannerAnswerRequirement(
                requirement_id="R3",
                label="Harbor Network middle mechanism",
            ),
            PlannerAnswerRequirement(
                requirement_id="R4",
                label="Harbor Network later development",
            ),
            PlannerAnswerRequirement(
                requirement_id="R5",
                label="Harbor Network closure",
            ),
        ),
        facets=(
            PlannerSearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.ORIGIN,
                search_query="Harbor Network formation",
                document_hints=("part-a.md",),
            ),
            PlannerSearchFacet(
                facet_id="F2",
                requirement_ids=("R2",),
                role=FacetRole.TRANSITION,
                search_query="Harbor Network development",
                document_hints=("part-middle.md",),
            ),
            PlannerSearchFacet(
                facet_id="F3",
                requirement_ids=("R3",),
                role=FacetRole.MECHANISM,
                search_query="Harbor Network middle mechanism",
                document_hints=("part-middle.md",),
            ),
            PlannerSearchFacet(
                facet_id="F4",
                requirement_ids=("R4",),
                role=FacetRole.TRANSITION,
                search_query="Harbor Network later development",
                document_hints=("part-middle.md",),
            ),
            PlannerSearchFacet(
                facet_id="F5",
                requirement_ids=("R5",),
                role=FacetRole.ENDPOINT,
                search_query="Harbor Network closure",
                document_hints=("part-b.md",),
            ),
        ),
    )


def valid_lineage_proposal() -> PlannerQuestionPlan:
    stages = (
        (
            "Chartered Alpha Consortium",
            FacetRole.ORIGIN,
            "Alpha Consortium chartered venture",
            "Alpha Consortium",
        ),
        (
            "Provincial council succession",
            FacetRole.TRANSITION,
            "Alpha Consortium provincial council",
            "Provincial Council",
        ),
        (
            "Assembly tax authority",
            FacetRole.MECHANISM,
            "Alpha Consortium assembly taxation",
            "Assembly Tax Authority",
        ),
        (
            "Commonwealth administrative office",
            FacetRole.TRANSITION,
            "Alpha Consortium commonwealth office",
            "Commonwealth Office",
        ),
        (
            "National treasury integration",
            FacetRole.MECHANISM,
            "Omega Network national treasury",
            "National Treasury",
        ),
        (
            "Federal procurement bureau",
            FacetRole.MECHANISM,
            "Omega Network federal procurement",
            "Federal Procurement Bureau",
        ),
        (
            "Contractor logistics command",
            FacetRole.TRANSITION,
            "Omega Network contractor logistics command",
            "Contractor Logistics Command",
        ),
        (
            "Data-centered Omega Network",
            FacetRole.ENDPOINT,
            "Omega Network data center",
            "Omega Network",
        ),
    )
    capacities = (
        "chartered territorial mandate",
        "delegated provincial authority",
        "representative taxing authority",
        "commonwealth administrative capacity",
        "national fiscal capacity",
        "federal procurement authority",
        "contractor command capacity",
        "data-centered operating capacity",
        "networked institutional capacity",
    )
    return PlannerQuestionPlan(
        requirements=tuple(
            PlannerAnswerRequirement(
                requirement_id=f"R{index}",
                label=label,
                institutional_handoff=InstitutionalHandoff(
                    bearer=bearer,
                    inherited_capacity=capacities[index - 1],
                    transfer_mechanism=(
                        f"{bearer} transforms the inherited capacity"
                    ),
                    outgoing_capacity=capacities[index],
                ),
            )
            for index, (label, _role, _query, bearer) in enumerate(
                stages,
                start=1,
            )
        ),
        facets=tuple(
            PlannerSearchFacet(
                facet_id=f"F{index}",
                requirement_ids=(f"R{index}",),
                role=role,
                search_query=query,
                document_hints=(f"lineage-{index}.md",),
            )
            for index, (_label, role, query, _bearer) in enumerate(
                stages,
                start=1,
            )
        ),
    )


def causal_span_catalog() -> tuple[DocumentCatalogEntry, ...]:
    role_by_band = (
        "charter",
        "taxation",
        "mobilization",
        "procurement",
        "centralization",
    )
    body = tuple(
        DocumentCatalogEntry(
            document_id=f"{index:02}_Chapter {index}.md",
            chapter_title=f"Chapter {index}",
            corpus_ordinal=index,
            role_terms=(
                "conflict",
                role_by_band[min(4, (5 * (index - 1)) // 25)],
            ),
        )
        for index in range(1, 26)
    )
    return (
        DocumentCatalogEntry(
            document_id="00_Introduction.md",
            chapter_title="Introduction",
            corpus_ordinal=0,
            role_terms=("conflict", "charter"),
        ),
        *body,
        DocumentCatalogEntry(
            document_id="26_Epilogue.md",
            chapter_title="Epilogue",
            corpus_ordinal=26,
            role_terms=("conflict", "endpoint"),
        ),
    )


def valid_causal_span_proposal(
    *,
    origin_hint: str = "01_Chapter 1.md",
    origin_secondary_hints: tuple[str, ...] = (),
    stage_hint_overrides: dict[int, str] | None = None,
) -> PlannerQuestionPlan:
    labels = (
        "Conflict charter origin",
        "Conflict taxation",
        "Conflict mobilization",
        "Conflict procurement",
        "Conflict centralization",
        "Conflict endpoint",
    )
    roles = (
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.ENDPOINT,
    )
    hints = [
        origin_hint,
        "06_Chapter 6.md",
        "11_Chapter 11.md",
        "16_Chapter 16.md",
        "21_Chapter 21.md",
        "26_Epilogue.md",
    ]
    for stage, hint in (stage_hint_overrides or {}).items():
        hints[stage - 1] = hint
    requirements = tuple(
        PlannerAnswerRequirement(
            requirement_id=f"R{index}",
            label=label,
        )
        for index, label in enumerate(labels, start=1)
    )
    return PlannerQuestionPlan(
        requirements=requirements,
        facets=tuple(
            PlannerSearchFacet(
                facet_id=f"F{index}",
                requirement_ids=(f"R{index}",),
                role=role,
                search_query=labels[index - 1],
                document_hints=(
                    (hint, *origin_secondary_hints)
                    if index == 1
                    else (hint,)
                ),
            )
            for index, (role, hint) in enumerate(
                zip(roles, hints, strict=True),
                start=1,
            )
        ),
    )


def test_resolved_turn_carries_conversation_resolution_structure():
    turn = ResolvedTurn(
        standalone_question="How did Project Lumen affect the Harbor Network?",
        entities=("Project Lumen", "Harbor Network"),
        scope="the period after launch",
        corrections=("The pronoun refers to Project Lumen.",),
        relationship="Project Lumen",
    )

    assert turn.schema == "archivist.resolved_turn/1"
    assert turn.entities == ("Project Lumen", "Harbor Network")
    assert turn.scope == "the period after launch"
    assert turn.corrections == ("The pronoun refers to Project Lumen.",)
    assert turn.relationship == "Project Lumen"

    with pytest.raises(ValidationError):
        ResolvedTurn(standalone_question="Continue.", entities=("QRS", "qrs"))


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Trace the Harbor Network's development over time.",
            (RouteTrait.BROAD_SYNTHESIS,),
        ),
        (
            LINEAGE_QUESTION,
            (
                RouteTrait.BROAD_SYNTHESIS,
                RouteTrait.LONG_INSTITUTIONAL_LINEAGE,
            ),
        ),
        (
            "What caused the signal failure, and what consequences followed?",
            (RouteTrait.MULTI_PART,),
        ),
        (
            "How does the manuscript connect tobacco to labor?",
            (RouteTrait.RELATIONSHIP,),
        ),
        (
            "Why did Project Lumen cause the signal failure?",
            (RouteTrait.PREMISE_SENSITIVE,),
        ),
        (
            "What does the manuscript say about Project Lumen?",
            (RouteTrait.ABSENCE_SENSITIVE,),
        ),
        (
            "How does the book treat conflict as an engine of central power?",
            (RouteTrait.BROAD_SYNTHESIS,),
        ),
        (
            "How does the book treat the Hudson Bay Consortium?",
            (RouteTrait.ABSENCE_SENSITIVE,),
        ),
        ("Who led Project Lumen?", ()),
    ],
)
def test_routing_is_deterministic_and_focused_traits_do_not_leak(question, expected):
    assert route_question(question) == expected
    assert route_question(question) == expected


def test_route_traits_are_composable_in_stable_order():
    question = (
        "Why did Project Lumen change from launch to closure, and what consequences followed?"
    )

    assert route_question(question) == (
        RouteTrait.BROAD_SYNTHESIS,
        RouteTrait.MULTI_PART,
        RouteTrait.PREMISE_SENSITIVE,
    )


@pytest.mark.parametrize(
    ("question", "surface"),
    [
        ('Does the text mention "lowercase signal group"?', "lowercase signal group"),
        ("Who led Project Lumen?", "Project Lumen"),
        ("Does the text mention QRS?", "QRS"),
        ("Does the text mention XR-17?", "XR-17"),
        ("Does the text mention Model 47?", "Model 47"),
    ],
)
def test_trusted_target_extraction_uses_only_conservative_surface_forms(question, surface):
    targets = extract_trusted_targets(question)

    assert len(targets) == 1
    assert targets[0].query_surface_span == surface
    assert targets[0].absence_checkable is True


def test_trusted_target_extraction_does_not_invent_aliases_or_use_entity_metadata_alone():
    turn = ResolvedTurn(
        standalone_question="Does the text discuss the signal group?",
        entities=("Project Lumen",),
    )

    assert extract_trusted_targets(turn) == ()


def test_relationship_metadata_can_classify_an_exact_trusted_target_as_a_facet():
    turn = ResolvedTurn(
        standalone_question="How was Project Lumen related to Harbor Network?",
        entities=("Project Lumen", "Harbor Network"),
        relationship="Harbor Network",
    )

    targets = extract_trusted_targets(turn)

    assert [target.query_surface_span for target in targets] == [
        "Project Lumen",
        "Harbor Network",
    ]
    assert [target.role for target in targets] == [
        EvidenceTargetRole.SUBJECT,
        EvidenceTargetRole.FACET,
    ]


def test_relationship_wording_classifies_second_named_target_as_facet():
    targets = extract_trusted_targets(
        "What was the relationship between Project Lumen and Harbor Network?"
    )

    assert [target.role for target in targets] == [
        EvidenceTargetRole.SUBJECT,
        EvidenceTargetRole.FACET,
    ]


@pytest.mark.parametrize(
    "question",
    [
        "How did Project Lumen affect Harbor Network?",
        "How did Project Lumen influence Harbor Network?",
        "How did Project Lumen lead to changes in Harbor Network?",
    ],
)
def test_directional_relationship_predicates_classify_second_target_as_facet(
    question,
):
    targets = extract_trusted_targets(question)

    assert [target.query_surface_span for target in targets] == [
        "Project Lumen",
        "Harbor Network",
    ]
    assert [target.role for target in targets] == [
        EvidenceTargetRole.SUBJECT,
        EvidenceTargetRole.FACET,
    ]


def test_unrelated_predicate_does_not_turn_second_named_target_into_a_facet():
    targets = extract_trusted_targets("What did Project Lumen report about Harbor Network?")

    assert [target.role for target in targets] == [
        EvidenceTargetRole.SUBJECT,
        EvidenceTargetRole.SUBJECT,
    ]


@pytest.mark.parametrize(
    "question",
    [
        "How does Project Lumen connect to Harbor Network?",
        "How does Project Lumen relate to Harbor Network?",
        "How does Project Lumen link to Harbor Network?",
        "Can Project Lumen connect to Harbor Network?",
        "Does Project Lumen relate to Harbor Network?",
    ],
)
def test_relational_question_forms_are_routed_and_role_the_second_target_as_facet(
    question,
):
    assert route_question(question) == (RouteTrait.RELATIONSHIP,)
    assert requires_planning(question) is False
    assert [target.role for target in extract_trusted_targets(question)] == [
        EvidenceTargetRole.SUBJECT,
        EvidenceTargetRole.FACET,
    ]


@pytest.mark.parametrize(
    "question",
    [
        "How does Project Lumen connect to Harbor Network to explain the change?",
        "How do I connect to the archive to search it?",
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council as proving the hidden conspiracy?"
        ),
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council because the treaty failed?"
        ),
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council over time?"
        ),
        ("What is the relationship between Alpha Network and Beta Council in Port Delta?"),
        ("What is the relationship between Alpha Network and Beta Council in 1700?"),
        (
            "What is the relationship between Alpha Network and Beta Council "
            "given that the treaty failed?"
        ),
        (
            "What is the relationship between Alpha Network and Beta Council "
            "according to the disputed premise?"
        ),
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council as shaping exchange because the treaty failed?"
        ),
        (
            "How did the relationship between Alpha Network and Beta Council "
            "shape exchange because the treaty failed?"
        ),
    ],
)
def test_ambiguous_relationship_syntax_uses_the_planner_instead_of_bad_local_operands(
    question,
):
    assert RouteTrait.RELATIONSHIP in route_question(question)
    assert requires_planning(question) is True

    plan = build_question_plan(question)

    assert plan.fallback_reason == "planner_unavailable"
    assert plan.facets[0].role is FacetRole.ORIGINAL
    assert not {
        FacetRole.BROADER_RELATED,
        FacetRole.MECHANISM,
    }.intersection(facet.role for facet in plan.facets)


def test_between_relationship_keeps_for_inside_a_named_operand():
    question = "What was the relationship between Alpha Network and Society for Public Memory?"

    assert route_question(question) == (RouteTrait.RELATIONSHIP,)
    assert requires_planning(question) is False

    plan = build_question_plan(question)

    assert [requirement.label for requirement in plan.requirements] == [
        "Context for Alpha Network",
        "Context for Society for Public Memory",
        "Connection between Alpha Network and Society for Public Memory",
    ]
    assert plan.facets[-1].search_query == ("Alpha Network Society for Public Memory relationship")


@pytest.mark.parametrize(
    "question",
    [
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council as proving the hidden conspiracy?"
        ),
        (
            "What is the relationship between Alpha Network and Beta Council "
            "given that the treaty failed?"
        ),
        (
            "What is the relationship between Alpha Network and Beta Council "
            "according to the disputed premise?"
        ),
        (
            "How did the manuscript describe the relationship between Alpha Network "
            "and Beta Council as shaping exchange because the treaty failed?"
        ),
    ],
)
def test_factive_between_relationship_preserves_premise_checking(question):

    assert RouteTrait.PREMISE_SENSITIVE in route_question(question)
    assert requires_planning(question) is True

    fallback = build_question_plan(question)

    assert fallback.premises
    assert {
        FacetRole.PREMISE_SUPPORT,
        FacetRole.PREMISE_COUNTER,
        FacetRole.FRAMING,
    }.issubset(facet.role for facet in fallback.facets)


def test_bounded_between_relationship_decomposes_locally_with_its_context():
    question = (
        "How did the manuscript describe the relationship between Project Lumen "
        "and Harbor Network as shaping civic exchange in Port Delta?"
    )

    assert route_question(question) == (RouteTrait.RELATIONSHIP,)
    assert requires_planning(question) is False

    plan = build_question_plan(question)

    assert plan.fallback_reason is None
    assert [requirement.label for requirement in plan.requirements] == [
        "Context for Project Lumen",
        "Context for Harbor Network",
        (
            "Connection between Project Lumen and Harbor Network "
            "as shaping civic exchange in Port Delta"
        ),
    ]
    assert [facet.search_query for facet in plan.facets] == [
        question,
        "Project Lumen context",
        "Harbor Network context",
        ("Project Lumen Harbor Network relationship as shaping civic exchange in Port Delta"),
    ]


def test_directional_between_relationship_decomposes_resolved_followup_locally():
    question = (
        "How did the relationship between tobacco and labor shape everyday exchange in Jamestown?"
    )

    assert route_question(question) == (RouteTrait.RELATIONSHIP,)
    assert requires_planning(question) is False

    plan = build_question_plan(question)

    assert plan.fallback_reason is None
    assert [requirement.label for requirement in plan.requirements] == [
        "Context for tobacco",
        "Context for labor",
        ("Connection between tobacco and labor shape everyday exchange in Jamestown"),
    ]
    assert [facet.search_query for facet in plan.facets] == [
        question,
        "tobacco context",
        "labor context",
        ("tobacco labor relationship shape everyday exchange in Jamestown"),
    ]


def test_between_relationship_uses_planner_instead_of_truncating_long_context():
    left = "Alpha " * 17
    right = "Beta " * 20
    question = (
        "How did the manuscript describe the relationship between "
        f"{left.strip()} and {right.strip()} as shaping civic exchange?"
    )

    assert RouteTrait.RELATIONSHIP in route_question(question)
    assert requires_planning(question) is True

    plan = build_question_plan(question)

    assert plan.fallback_reason == "planner_unavailable"
    assert plan.facets[0].role is FacetRole.ORIGINAL
    assert not {
        FacetRole.BROADER_RELATED,
        FacetRole.MECHANISM,
    }.intersection(facet.role for facet in plan.facets)


def test_between_relationship_with_oversized_operand_still_routes_to_planner():
    question = f"What was the relationship between Alpha Network and {'Beta ' * 30}?"

    assert RouteTrait.RELATIONSHIP in route_question(question)
    assert requires_planning(question) is True


def test_long_original_question_is_preserved_while_added_facets_stay_bounded():
    question = ("Explain " + ("synthetic context " * 30)).strip()

    result = build_question_plan(question)

    assert len(question) > 240
    assert result.facets[0].facet_id == "F0"
    assert result.facets[0].search_query == question
    assert all(len(facet.search_query) <= 240 for facet in result.facets[1:])


def test_valid_plan_gets_trusted_traits_targets_and_unchanged_f0():
    question = "Trace the Harbor Network from formation to closure."

    result = validate_question_plan(valid_planner_plan(), question, CATALOG)

    assert result.schema == "archivist.question_plan/3"
    assert result.planner_used is True
    assert result.fallback_reason is None
    assert result.facets[0] == SearchFacet(
        facet_id="F0",
        requirement_ids=("R1", "R2", "R3", "R4", "R5"),
        role=FacetRole.ORIGINAL,
        search_query=question,
        document_hints=(),
    )
    assert result.targets == (
        EvidenceTarget(
            target_id="T1",
            query_surface_span="Harbor Network",
            role=EvidenceTargetRole.SUBJECT,
            absence_checkable=True,
        ),
    )


def test_provider_proposal_materializes_application_owned_plan_fields():
    question = "Trace the Harbor Network from formation to closure."

    result = build_question_plan(
        question,
        valid_planner_proposal(),
        CATALOG,
    )

    assert result.planner_used is True
    assert result.fallback_reason is None
    assert result.traits == (RouteTrait.BROAD_SYNTHESIS,)
    assert [requirement.order for requirement in result.requirements] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert all(requirement.required for requirement in result.requirements)
    assert result.facets[0].facet_id == "F0"
    assert result.targets == (
        EvidenceTarget(
            target_id="T1",
            query_surface_span="Harbor Network",
            role=EvidenceTargetRole.SUBJECT,
            absence_checkable=True,
        ),
    )


@pytest.mark.parametrize("by_alias", [False, True])
def test_provider_proposal_mapping_round_trip_is_recognized(by_alias):
    result = build_question_plan(
        "Trace the Harbor Network from formation to closure.",
        valid_planner_proposal().model_dump(by_alias=by_alias),
        CATALOG,
    )

    assert result.planner_used is True
    assert result.fallback_reason is None


def test_shape_valid_but_semantically_invalid_proposal_falls_back_locally():
    proposal = valid_planner_proposal().model_copy(
        update={
            "facets": (
                PlannerSearchFacet(
                    facet_id="F1",
                    requirement_ids=("R1",),
                    role=FacetRole.ORIGIN,
                    search_query="Harbor Network formation",
                ),
            ),
        }
    )

    diagnostics = {}
    result = build_question_plan(
        "Trace the Harbor Network from formation to closure.",
        proposal,
        CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert result.fallback_reason == "invalid_planner_output"
    assert result.facets[0].facet_id == "F0"
    assert diagnostics == {"planner_validation_code": "missing_requirement_mapping"}


def test_structurally_invalid_proposal_records_only_normalized_code():
    proposal = valid_planner_proposal().model_copy(
        update={
            "facets": (
                valid_planner_proposal().facets[0],
                valid_planner_proposal().facets[0],
            ),
        }
    )
    diagnostics = {}

    result = build_question_plan(
        "Trace the Harbor Network from formation to closure.",
        proposal,
        CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.fallback_reason == "invalid_planner_output"
    assert diagnostics == {"planner_validation_code": "plan_structure_invalid"}


def test_planner_premise_is_rejected_when_the_local_route_is_absence_only():
    proposal = PlannerQuestionPlan(
        requirements=(
            PlannerAnswerRequirement(
                requirement_id="R1",
                label="Hudson Bay Consortium treatment",
            ),
        ),
        facets=(
            PlannerSearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.PREMISE_SUPPORT,
                search_query="Hudson Bay Consortium support",
            ),
            PlannerSearchFacet(
                facet_id="F2",
                requirement_ids=("R1",),
                role=FacetRole.PREMISE_COUNTER,
                search_query="Hudson Bay Consortium counter evidence",
            ),
            PlannerSearchFacet(
                facet_id="F3",
                requirement_ids=("R1",),
                role=FacetRole.FRAMING,
                search_query="Hudson Bay Consortium framing",
            ),
        ),
        premises=(
            PlannerPremiseHypothesis(
                premise_id="P1",
                proposition="The manuscript treats the Hudson Bay Consortium as central",
                support_facet_id="F1",
                counter_facet_id="F2",
                framing_facet_id="F3",
            ),
        ),
    )
    diagnostics = {}
    question = "What does the manuscript say about the Hudson Bay Consortium?"

    result = build_question_plan(
        question,
        proposal,
        validation_diagnostics=diagnostics,
    )

    assert route_question(question) == (RouteTrait.ABSENCE_SENSITIVE,)
    assert result.premises == ()
    assert result.fallback_reason == "invalid_planner_output"
    assert diagnostics == {"planner_validation_code": "premise_route_mismatch"}


def test_genuine_planner_premise_requires_a_framing_facet():
    plan = QuestionPlan(
        requirements=(requirement(),),
        facets=(
            facet(
                "F1",
                ("R1",),
                "Project Lumen signal failure support",
                role=FacetRole.PREMISE_SUPPORT,
            ),
            facet(
                "F2",
                ("R1",),
                "Project Lumen earlier signal failure",
                role=FacetRole.PREMISE_COUNTER,
            ),
        ),
        premises=(
            PremiseHypothesis(
                premise_id="P1",
                proposition="Project Lumen caused the signal failure",
                support_facet_id="F1",
                counter_facet_id="F2",
            ),
        ),
    )

    with pytest.raises(PlanValidationError, match="missing_premise_framing"):
        validate_question_plan(plan, "Why did Project Lumen cause the signal failure?")


def test_under_decomposed_causal_proposal_falls_back_to_six_protected_lanes():
    proposal = PlannerQuestionPlan(
        requirements=(
            PlannerAnswerRequirement(
                requirement_id="R1",
                label="Conflict and central power",
            ),
        ),
        facets=(
            PlannerSearchFacet(
                facet_id="F1",
                requirement_ids=("R1",),
                role=FacetRole.MECHANISM,
                search_query="conflict engine central power",
            ),
        ),
    )
    diagnostics = {}
    question = CAUSAL_SPAN_QUESTION

    result = build_question_plan(
        question,
        proposal,
        validation_diagnostics=diagnostics,
    )

    assert result.fallback_reason == "invalid_planner_output"
    assert len(result.requirements) == 6
    assert [facet.role for facet in result.facets[1:]] == [
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.ENDPOINT,
    ]
    assert diagnostics == {"planner_validation_code": "broad_narrative_gap"}


def test_broad_proposal_requires_origin_middle_endpoint_requirement_order():
    proposal = valid_planner_proposal().model_copy(
        update={
            "facets": (
                valid_planner_proposal().facets[0],
                PlannerSearchFacet(
                    facet_id="F2",
                    requirement_ids=("R2",),
                    role=FacetRole.ENDPOINT,
                    search_query="Harbor Network premature closure",
                    document_hints=("part-b.md",),
                ),
                PlannerSearchFacet(
                    facet_id="F3",
                    requirement_ids=("R3",),
                    role=FacetRole.TRANSITION,
                    search_query="Harbor Network middle development",
                    document_hints=("part-middle.md",),
                ),
                *valid_planner_proposal().facets[3:],
            )
        }
    )
    diagnostics = {}

    result = build_question_plan(
        "Trace the Harbor Network from formation to closure.",
        proposal,
        CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert result.fallback_reason == "invalid_planner_output"
    assert diagnostics == {"planner_validation_code": "broad_plan_under_decomposed"}
    assert [facet.role for facet in result.facets[1:]] == [
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.ENDPOINT,
    ]


def test_long_institutional_lineage_accepts_eight_distinct_ordered_roles():
    result = build_question_plan(
        LINEAGE_QUESTION,
        valid_lineage_proposal(),
        LINEAGE_CATALOG,
    )

    assert result.planner_used is True
    assert result.traits == (
        RouteTrait.BROAD_SYNTHESIS,
        RouteTrait.LONG_INSTITUTIONAL_LINEAGE,
    )
    assert len(result.requirements) == 8
    assert len(result.facets) == 9
    assert [facet.role for facet in result.facets[1:]] == [
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.ENDPOINT,
    ]
    assert [facet.document_hints[0] for facet in result.facets[1:]] == [
        f"lineage-{index}.md" for index in range(1, 9)
    ]
    assert all(
        requirement.institutional_handoff is not None
        for requirement in result.requirements
    )
    assert all(
        predecessor.institutional_handoff.outgoing_capacity
        == successor.institutional_handoff.inherited_capacity
        for predecessor, successor in zip(
            result.requirements,
            result.requirements[1:],
            strict=False,
        )
    )


def test_profiled_long_lineage_rejects_a_document_without_the_stage_role():
    mismatched_catalog = (
        PROFILED_LINEAGE_CATALOG[0],
        PROFILED_LINEAGE_CATALOG[1].model_copy(
            update={
                "chapter_title": "Unrelated Orbital Archive",
                "role_terms": ("unrelated", "orbital", "archive"),
            }
        ),
        *PROFILED_LINEAGE_CATALOG[2:],
    )
    diagnostics = {}

    result = build_question_plan(
        LINEAGE_QUESTION,
        valid_lineage_proposal(),
        mismatched_catalog,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert result.fallback_reason == "invalid_planner_output"
    assert diagnostics == {
        "planner_validation_code": "document_role_mismatch"
    }


def test_book_spanning_causal_origin_repairs_only_the_late_origin_hint(
    monkeypatch,
):
    catalog = causal_span_catalog()
    proposal = valid_causal_span_proposal(
        origin_hint="05_Chapter 5.md",
    )
    diagnostics = {}

    result = build_question_plan(
        CAUSAL_SPAN_QUESTION,
        proposal,
        catalog,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is True
    assert result.fallback_reason is None
    assert diagnostics == {"planner_validation_code": None}
    assert tuple(requirement.label for requirement in result.requirements) == tuple(
        requirement.label for requirement in proposal.requirements
    )
    stage_facets = result.facets[1:]
    assert tuple(facet.facet_id for facet in stage_facets) == (
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
        "F6",
    )
    assert stage_facets[0].document_hints == (
        "01_Chapter 1.md",
        "05_Chapter 5.md",
    )
    assert tuple(facet.document_hints for facet in stage_facets[1:]) == (
        ("06_Chapter 6.md",),
        ("11_Chapter 11.md",),
        ("16_Chapter 16.md",),
        ("21_Chapter 21.md",),
        ("26_Epilogue.md",),
    )

    monkeypatch.setattr(
        query_planning,
        "_repair_broad_origin_plan",
        lambda *_args, **_kwargs: None,
    )
    failed_repair_diagnostics = {}
    fallback = build_question_plan(
        CAUSAL_SPAN_QUESTION,
        proposal,
        catalog,
        validation_diagnostics=failed_repair_diagnostics,
    )

    assert fallback.planner_used is False
    assert fallback.fallback_reason == "invalid_planner_output"
    assert failed_repair_diagnostics == {
        "planner_validation_code": "broad_origin_not_preserved"
    }


def test_causal_span_rejects_secondary_overview_hint_from_v21_shape():
    diagnostics = {}

    result = build_question_plan(
        CAUSAL_SPAN_QUESTION,
        valid_causal_span_proposal(
            origin_secondary_hints=("00_Introduction.md",),
        ),
        causal_span_catalog(),
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert len(result.requirements) == 6
    assert diagnostics == {
        "planner_validation_code": "broad_origin_is_overview"
    }


def test_causal_span_rejects_a_skipped_body_band():
    diagnostics = {}

    result = build_question_plan(
        CAUSAL_SPAN_QUESTION,
        valid_causal_span_proposal(
            stage_hint_overrides={2: "11_Chapter 11.md"},
        ),
        causal_span_catalog(),
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {"planner_validation_code": "broad_narrative_gap"}


def test_causal_span_requires_terminal_endpoint_when_catalog_has_epilogue():
    diagnostics = {}

    result = build_question_plan(
        CAUSAL_SPAN_QUESTION,
        valid_causal_span_proposal(
            stage_hint_overrides={6: "25_Chapter 25.md"},
        ),
        causal_span_catalog(),
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "broad_endpoint_not_terminal"
    }


def test_long_lineage_requires_complete_contiguous_handoffs():
    proposal = valid_lineage_proposal()
    missing = proposal.model_copy(
        update={
            "requirements": (
                proposal.requirements[0].model_copy(
                    update={"institutional_handoff": None}
                ),
                *proposal.requirements[1:],
            )
        }
    )
    diagnostics = {}

    result = build_question_plan(
        LINEAGE_QUESTION,
        missing,
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_handoff_invalid"
    }

    broken_handoff = proposal.requirements[2].model_copy(
        update={
            "institutional_handoff": (
                proposal.requirements[2].institutional_handoff.model_copy(
                    update={
                        "inherited_capacity": "unrelated orbital capacity"
                    }
                )
            )
        }
    )
    diagnostics = {}
    result = build_question_plan(
        LINEAGE_QUESTION,
        proposal.model_copy(
            update={
                "requirements": (
                    *proposal.requirements[:2],
                    broken_handoff,
                    *proposal.requirements[3:],
                )
            }
        ),
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_handoff_invalid"
    }


def test_long_lineage_binds_first_and_last_bearers_to_question_endpoints():
    proposal = valid_lineage_proposal()
    wrong_endpoint = proposal.requirements[-1].model_copy(
        update={
            "institutional_handoff": (
                proposal.requirements[-1].institutional_handoff.model_copy(
                    update={"bearer": "Unrelated Terminal Bureau"}
                )
            )
        }
    )
    diagnostics = {}

    result = build_question_plan(
        LINEAGE_QUESTION,
        proposal.model_copy(
            update={
                "requirements": (
                    *proposal.requirements[:-1],
                    wrong_endpoint,
                )
            }
        ),
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_handoff_invalid"
    }


def test_non_lineage_route_rejects_planner_handoff_metadata():
    proposal = valid_planner_proposal()
    first_requirement = proposal.requirements[0].model_copy(
        update={
            "institutional_handoff": InstitutionalHandoff(
                bearer="Harbor Council",
                inherited_capacity="local mandate",
                transfer_mechanism="council succession",
                outgoing_capacity="regional mandate",
            )
        }
    )
    diagnostics = {}

    result = build_question_plan(
        "Trace the Harbor Network from formation to closure.",
        proposal.model_copy(
            update={
                "requirements": (
                    first_requirement,
                    *proposal.requirements[1:],
                )
            }
        ),
        CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_handoff_route_mismatch"
    }


def test_short_lineage_proposal_falls_back_to_eight_capacity_aware_stages():
    proposal = valid_lineage_proposal().model_copy(
        update={
            "requirements": valid_lineage_proposal().requirements[:5],
            "facets": valid_lineage_proposal().facets[:5],
        }
    )
    diagnostics = {}

    result = build_question_plan(
        LINEAGE_QUESTION,
        proposal,
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert result.fallback_reason == "invalid_planner_output"
    assert len(result.requirements) == 8
    assert len(result.facets) == 9
    assert diagnostics == {
        "planner_validation_code": "lineage_stage_cardinality_mismatch"
    }


def test_long_lineage_rejects_repeated_bearers_and_nonadvancing_hints():
    proposal = valid_lineage_proposal()
    repeated_role = proposal.facets[1].model_copy(
        update={
            "search_query": "Alpha Consortium later chartered venture",
        }
    )
    repeated_requirement = proposal.requirements[1].model_copy(
        update={
            "label": "Later chartered Alpha Consortium",
            "institutional_handoff": (
                proposal.requirements[1].institutional_handoff.model_copy(
                    update={"bearer": "Alpha Consortium"}
                )
            ),
        },
    )
    repeated = proposal.model_copy(
        update={
            "requirements": (
                proposal.requirements[0],
                repeated_requirement,
                *proposal.requirements[2:],
            ),
            "facets": (
                proposal.facets[0],
                repeated_role,
                *proposal.facets[2:],
            ),
        }
    )
    diagnostics = {}

    result = build_question_plan(
        LINEAGE_QUESTION,
        repeated,
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_handoff_invalid"
    }

    reversed_hint = proposal.facets[1].model_copy(
        update={"document_hints": ("lineage-1.md",)}
    )
    nonadvancing = proposal.model_copy(
        update={
            "facets": (
                proposal.facets[0],
                reversed_hint,
                *proposal.facets[2:],
            )
        }
    )
    diagnostics = {}
    result = build_question_plan(
        LINEAGE_QUESTION,
        nonadvancing,
        LINEAGE_CATALOG,
        validation_diagnostics=diagnostics,
    )

    assert result.planner_used is False
    assert diagnostics == {
        "planner_validation_code": "lineage_stage_role_invalid"
    }


def test_planner_cannot_promote_a_focused_question_to_a_sensitive_route():
    plan = QuestionPlan(
        traits=(RouteTrait.PREMISE_SENSITIVE, RouteTrait.ABSENCE_SENSITIVE),
        requirements=(requirement(),),
        facets=(facet("F1", ("R1",), "Project Lumen leadership"),),
    )

    result = validate_question_plan(plan, "Who led Project Lumen?")

    assert result.traits == ()


def test_planner_cannot_supply_or_replace_the_original_lane():
    plan = valid_planner_plan().model_copy(
        update={
            "facets": (
                facet("F0", ("R1", "R2"), "changed question", role=FacetRole.ORIGINAL),
                *valid_planner_plan().facets,
            )
        }
    )

    with pytest.raises(PlanValidationError, match="planner_owned_original"):
        validate_question_plan(plan, "Trace the Harbor Network from formation to closure.", CATALOG)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda plan: plan.model_copy(
                update={"facets": (facet("F1", ("R1",), "Harbor Network formation"),)}
            ),
            "missing_requirement_mapping",
        ),
        (
            lambda plan: plan.model_copy(
                update={
                    "facets": (
                        facet(
                            "F1",
                            ("R1",),
                            "Harbor Network formation",
                            hints=("unknown.md",),
                        ),
                        *plan.facets[1:],
                    )
                }
            ),
            "unknown_document_hint",
        ),
        (
            lambda plan: plan.model_copy(
                update={
                    "facets": (
                        facet("F1", ("R1",), "unrelated orbital taxonomy"),
                        *plan.facets[1:],
                    )
                }
            ),
            "query_drift",
        ),
        (
            lambda plan: plan.model_copy(
                update={
                    "facets": (
                        facet(
                            "F1",
                            ("R1",),
                            "The answer is that Harbor Network formed",
                        ),
                        *plan.facets[1:],
                    )
                }
            ),
            "established_answer_claim",
        ),
    ],
)
def test_contextual_plan_validation_rejects_missing_unknown_and_drifting_data(mutate, error):
    with pytest.raises(PlanValidationError, match=error):
        validate_question_plan(
            mutate(valid_planner_plan()),
            "Trace the Harbor Network from formation to closure.",
            CATALOG,
        )


def test_query_can_be_grounded_by_an_exact_selected_catalog_title():
    plan = QuestionPlan(
        requirements=(requirement(),),
        facets=(
            facet(
                "F1",
                ("R1",),
                "Formation",
                role=FacetRole.ORIGIN,
                hints=("part-a.md",),
            ),
        ),
    )

    result = validate_question_plan(plan, "Trace the Harbor Network.", CATALOG)

    assert result.facets[1].search_query == "Formation"


def test_planner_generated_target_alias_cannot_become_a_trusted_target():
    plan = valid_planner_plan().model_copy(
        update={
            "targets": (
                EvidenceTarget(
                    target_id="T1",
                    query_surface_span="The Shining Initiative",
                    role=EvidenceTargetRole.SUBJECT,
                    absence_checkable=True,
                ),
            )
        }
    )

    with pytest.raises(PlanValidationError, match="untrusted_target"):
        validate_question_plan(
            plan,
            "Trace Project Lumen from formation to closure.",
            CATALOG,
        )


def test_pydantic_contract_rejects_duplicate_and_dangling_ids():
    with pytest.raises(ValidationError, match="requirement IDs"):
        QuestionPlan(
            requirements=(requirement("R1"), requirement("R1", order=1)),
        )

    with pytest.raises(ValidationError, match="unknown requirement"):
        QuestionPlan(
            requirements=(requirement(),),
            facets=(facet("F1", ("R9",), "Project Lumen"),),
        )

    with pytest.raises(ValidationError, match="dangling facet"):
        QuestionPlan(
            requirements=(requirement(),),
            facets=(
                facet(
                    "F1",
                    ("R1",),
                    "Project Lumen support",
                    role=FacetRole.PREMISE_SUPPORT,
                ),
                facet(
                    "F2",
                    ("R1",),
                    "Project Lumen counter",
                    role=FacetRole.PREMISE_COUNTER,
                ),
            ),
            premises=(
                PremiseHypothesis(
                    premise_id="P1",
                    proposition="Project Lumen began the change.",
                    support_facet_id="F1",
                    counter_facet_id="F2",
                    framing_facet_id="F9",
                ),
            ),
        )


def test_exact_version_one_count_caps_are_enforced():
    with pytest.raises(ValidationError):
        QuestionPlan(
            requirements=tuple(requirement(f"R{index}", order=index - 1) for index in range(1, 10))
        )

    with pytest.raises(ValidationError):
        QuestionPlan(
            requirements=(requirement(),),
            premises=tuple(
                PremiseHypothesis(
                    premise_id=f"P{index}",
                    proposition=f"Project Lumen proposition {index}",
                    support_facet_id="F1",
                    counter_facet_id="F2",
                )
                for index in range(1, 4)
            ),
        )

    with pytest.raises(ValidationError):
        SearchFacet(
            facet_id="F1",
            requirement_ids=("R1",),
            role=FacetRole.ORIGIN,
            search_query="Project Lumen",
            document_hints=("a", "b", "c"),
        )

    with pytest.raises(ValidationError):
        SearchFacet(
            facet_id="F1",
            requirement_ids=("R1",),
            role=FacetRole.ORIGIN,
            search_query="x" * 241,
        )


def test_f0_allows_eight_lineage_facets_but_rejects_a_ninth_added_facet():
    plan = QuestionPlan(
        requirements=(requirement(),),
        facets=tuple(
            facet(f"F{index}", ("R1",), f"Project Lumen facet {index}") for index in range(1, 9)
        ),
    )

    result = validate_question_plan(plan, "What changed for Project Lumen?")

    assert len(result.facets) == 9

    oversized = QuestionPlan(
        requirements=(requirement(),),
        facets=tuple(
            facet(f"F{index}", ("R1",), f"Project Lumen lane {index}")
            for index in range(1, 10)
        ),
    )
    with pytest.raises(PlanValidationError, match="too_many_facets"):
        validate_question_plan(oversized, "What changed for Project Lumen?")


def test_added_query_total_cap_is_exact():
    queries = tuple(f"Project Lumen {index} " + ("x" * 190) for index in range(1, 7))
    assert sum(map(len, queries)) > 1_200

    with pytest.raises(ValidationError, match="1200"):
        QuestionPlan(
            requirements=(requirement(),),
            facets=tuple(
                facet(f"F{index}", ("R1",), query) for index, query in enumerate(queries, start=1)
            ),
        )


def test_duplicate_queries_are_rejected_after_normalization():
    with pytest.raises(ValidationError, match="unique after normalization"):
        QuestionPlan(
            requirements=(requirement(),),
            facets=(
                facet("F1", ("R1",), "Project-Lumen formation"),
                facet("F2", ("R1",), "project lumen, formation"),
            ),
        )


def test_start_end_fallback_has_five_ordered_narrative_stage_lanes():
    question = "Trace the Harbor Network from formation to closure."

    plan = deterministic_fallback_plan(question, fallback_reason="planner_timeout")

    assert plan.planner_used is False
    assert plan.fallback_reason == "planner_timeout"
    assert [facet.facet_id for facet in plan.facets] == [
        "F0",
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    ]
    assert [facet.role for facet in plan.facets] == [
        FacetRole.ORIGINAL,
        FacetRole.ORIGIN,
        FacetRole.TRANSITION,
        FacetRole.MECHANISM,
        FacetRole.TRANSITION,
        FacetRole.ENDPOINT,
    ]
    assert plan.facets[0].search_query == question


def test_coordinated_fallback_builds_one_requirement_and_facet_per_clause():
    plan = deterministic_fallback_plan(
        "What caused the signal failure, and what consequences followed?",
        fallback_reason="planner_refusal",
    )

    assert len(plan.requirements) == 2
    assert [facet.facet_id for facet in plan.facets] == ["F0", "F1", "F2"]
    assert {requirement.requirement_id for requirement in plan.requirements} == {"R1", "R2"}


def test_homepage_relationship_fallback_searches_both_concepts_and_their_link():
    question = "How does the manuscript connect tobacco to labor?"

    plan = build_question_plan(question)

    assert plan.traits == (RouteTrait.RELATIONSHIP,)
    assert plan.fallback_reason is None
    assert [requirement.label for requirement in plan.requirements] == [
        "Context for tobacco",
        "Context for labor",
        "Connection between tobacco and labor",
    ]
    assert [facet.role for facet in plan.facets] == [
        FacetRole.ORIGINAL,
        FacetRole.BROADER_RELATED,
        FacetRole.BROADER_RELATED,
        FacetRole.MECHANISM,
    ]
    assert [facet.search_query for facet in plan.facets] == [
        question,
        "tobacco context",
        "labor context",
        "tobacco labor connect",
    ]
    assert [facet.requirement_ids for facet in plan.facets[1:]] == [
        ("R1",),
        ("R2",),
        ("R3",),
    ]


def test_origin_premise_fallback_reserves_support_counter_and_framing_lanes():
    plan = deterministic_fallback_plan(
        "Why did Project Lumen begin the signal change?",
        fallback_reason="low_budget_headroom",
    )

    assert len(plan.premises) == 1
    assert [facet.role for facet in plan.facets] == [
        FacetRole.ORIGINAL,
        FacetRole.PREMISE_SUPPORT,
        FacetRole.PREMISE_COUNTER,
        FacetRole.FRAMING,
    ]
    assert plan.premises[0].support_facet_id == "F1"
    assert plan.premises[0].counter_facet_id == "F2"
    assert plan.premises[0].framing_facet_id == "F3"


def test_focused_fallback_is_the_unchanged_standard_retrieval_lane():
    question = "Who led Project Lumen?"

    plan = build_question_plan(question)

    assert plan.traits == ()
    assert plan.fallback_reason is None
    assert len(plan.facets) == 1
    assert plan.facets[0].facet_id == "F0"
    assert plan.facets[0].search_query == question


def test_invalid_planner_output_falls_back_once_without_retry(monkeypatch):
    attempts = 0

    def reject_once(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise PlanValidationError("invalid", "synthetic invalid plan")

    monkeypatch.setattr(query_planning, "validate_question_plan", reject_once)

    result = build_question_plan(
        "Trace Project Lumen from formation to closure.",
        valid_planner_plan(),
        CATALOG,
    )

    assert attempts == 1
    assert result.planner_used is False
    assert result.fallback_reason == "invalid_planner_output"
    assert result.facets[0].facet_id == "F0"


def test_planner_proposal_schema_exposes_only_model_owned_fields():
    schema = query_planning.planner_question_plan_json_schema()

    assert schema["properties"]["schema"]["const"] == (
        "archivist.planner_question_plan/3"
    )
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "schema",
        "requirements",
        "facets",
        "premises",
    }
    assert schema["properties"]["requirements"]["maxItems"] == 8
    assert schema["properties"]["facets"]["maxItems"] == 8
    facet_schema = schema["$defs"]["PlannerSearchFacet"]
    assert facet_schema["properties"]["search_query"]["maxLength"] == 240
    assert facet_schema["properties"]["document_hints"]["items"]["maxLength"] == 300
    assert facet_schema["properties"]["requirement_ids"]["items"]["pattern"] == (
        "^[A-Za-z][A-Za-z0-9_-]{0,31}$"
    )

    with pytest.raises(ValidationError):
        PlannerQuestionPlan(
            requirements=valid_planner_proposal().requirements,
            facets=valid_planner_proposal().facets,
            manuscript_answer="not a planning field",
        )
    with pytest.raises(ValidationError):
        PlannerQuestionPlan(
            requirements=tuple(
                PlannerAnswerRequirement(
                    requirement_id=f"R{index}",
                    label=f"Requirement {index}",
                )
                for index in range(1, 10)
            ),
            facets=valid_planner_proposal().facets,
        )


def test_planner_proposal_preserves_multi_part_contract_capacity():
    requirements = tuple(
        PlannerAnswerRequirement(
            requirement_id=f"R{index}",
            label=f"Requested part {index}",
        )
        for index in range(1, 6)
    )
    facets = tuple(
        PlannerSearchFacet(
            facet_id=f"F{index}",
            requirement_ids=(f"R{index}",),
            role=FacetRole.BROADER_RELATED,
            search_query=f"Requested part {index}",
        )
        for index in range(1, 6)
    )

    proposal = PlannerQuestionPlan(
        requirements=requirements,
        facets=facets,
    )

    assert len(proposal.requirements) == 5
    assert len(proposal.facets) == 5


def test_finalized_question_plan_schema_remains_distinct_from_provider_proposal():
    schema = query_planning.question_plan_json_schema()

    assert schema["properties"]["schema"]["const"] == "archivist.question_plan/3"
    assert {
        "traits",
        "targets",
        "planner_used",
        "fallback_reason",
    } <= set(schema["properties"])
