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
    PlanValidationError,
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
        document_id="part-b.md",
        chapter_title="Closure of the Harbor Network",
        corpus_ordinal=1,
    ),
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
                "Harbor Network closure",
                role=FacetRole.ENDPOINT,
                hints=("part-b.md",),
            ),
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
    targets = extract_trusted_targets(
        "What did Project Lumen report about Harbor Network?"
    )

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
    ],
)
def test_ambiguous_relationship_syntax_uses_the_planner_instead_of_bad_local_operands(
    question,
):
    assert RouteTrait.RELATIONSHIP in route_question(question)
    assert requires_planning(question) is True

    plan = build_question_plan(question)

    assert plan.fallback_reason == "planner_unavailable"
    assert [facet.role for facet in plan.facets] == [FacetRole.ORIGINAL]


def test_long_original_question_is_preserved_while_added_facets_stay_bounded():
    question = ("Explain " + ("synthetic context " * 30)).strip()

    result = build_question_plan(question)

    assert len(question) > 240
    assert result.facets[0].facet_id == "F0"
    assert result.facets[0].search_query == question
    assert all(
        len(facet.search_query) <= 240 for facet in result.facets[1:]
    )


def test_valid_plan_gets_trusted_traits_targets_and_unchanged_f0():
    question = "Trace the Harbor Network from formation to closure."

    result = validate_question_plan(valid_planner_plan(), question, CATALOG)

    assert result.schema == "archivist.question_plan/1"
    assert result.planner_used is True
    assert result.fallback_reason is None
    assert result.facets[0] == SearchFacet(
        facet_id="F0",
        requirement_ids=("R1", "R2"),
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
                        plan.facets[1],
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
                        plan.facets[1],
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
                        plan.facets[1],
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


def test_f0_makes_eight_added_facets_an_oversized_final_plan():
    plan = QuestionPlan(
        requirements=(requirement(),),
        facets=tuple(
            facet(f"F{index}", ("R1",), f"Project Lumen facet {index}") for index in range(1, 9)
        ),
    )

    with pytest.raises(PlanValidationError, match="too_many_facets"):
        validate_question_plan(plan, "What changed for Project Lumen?")


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


def test_start_end_fallback_has_origin_endpoint_transition_and_original_lanes():
    question = "Trace the Harbor Network from formation to closure."

    plan = deterministic_fallback_plan(question, fallback_reason="planner_timeout")

    assert plan.planner_used is False
    assert plan.fallback_reason == "planner_timeout"
    assert [facet.facet_id for facet in plan.facets] == ["F0", "F1", "F2", "F3"]
    assert [facet.role for facet in plan.facets] == [
        FacetRole.ORIGINAL,
        FacetRole.ORIGIN,
        FacetRole.ENDPOINT,
        FacetRole.TRANSITION,
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


def test_question_plan_schema_is_native_pydantic_and_forbids_extra_fields():
    schema = query_planning.question_plan_json_schema()

    assert schema["properties"]["schema"]["const"] == "archivist.question_plan/1"
    assert schema["additionalProperties"] is False

    with pytest.raises(ValidationError):
        QuestionPlan(
            requirements=(requirement(),),
            manuscript_answer="not a planning field",
        )
