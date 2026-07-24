from __future__ import annotations

import json
from pathlib import Path

from query_planning import FacetRole, RouteTrait, build_question_plan


OPENING_QUESTIONS_FILE = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "openingQuestions.json"
)


def opening_questions() -> list[dict[str, str]]:
    return json.loads(OPENING_QUESTIONS_FILE.read_text(encoding="utf-8"))


def test_every_homepage_question_has_a_local_planning_regression():
    questions = opening_questions()

    assert questions
    assert len({item["question"] for item in questions}) == len(questions)
    for item in questions:
        plan = build_question_plan(item["question"])
        assert plan.requirements
        assert plan.facets[0].role is FacetRole.ORIGINAL
        assert plan.facets[0].search_query == item["question"]


def test_homepage_tobacco_labor_question_gets_three_local_evidence_lanes():
    item = next(
        item
        for item in opening_questions()
        if item["label"] == "Trace a theme"
    )

    plan = build_question_plan(item["question"])

    assert plan.traits == (RouteTrait.RELATIONSHIP,)
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
