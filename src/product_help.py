"""Provider-free answers to tightly bounded questions about Archivist itself."""

from __future__ import annotations

import re
import unicodedata


PRODUCT_HELP_POLICY_VERSION = "product-help-v1"
PRODUCT_HELP_RENDERER_VERSION = "product-help-renderer-v1"

_MAX_QUESTION_CHARACTERS = 160
_SPACE_RE = re.compile(r"\s+")
_MAX_TOTAL_TYPO_DISTANCE = 3
_CONTEXT_INDEPENDENT_PRODUCT_HELP_QUESTIONS = (
    "what do you do",
    "what do you do here",
    "what do you do there",
    "what can you do",
    "what is archivist",
    "what is the archivist",
    "what's archivist",
    "what's the archivist",
    "what is your purpose",
    "what are you here for",
    "how can you help me",
    "how can you help us",
    "what can you help me with",
    "what can i ask you",
    "what should i ask you",
    "how does archivist work",
    "how does the archivist work",
    "how do i use archivist",
    "how do i use the archivist",
)
_FIRST_TURN_PRODUCT_HELP_QUESTIONS = (
    "how does this work",
    "how do i use this",
)
# A one-character change can create a different, meaningful question. These pairs
# protect that semantic boundary while typo recovery handles non-word mistakes in
# any token. Entries that are more than one edit apart are harmless but included to
# make the intended boundary explicit.
_SEMANTIC_TOKEN_ALTERNATIVES = {
    "archivist": frozenset({"archivism"}),
    "help": frozenset({"helm", "tell"}),
    "purpose": frozenset({"purse"}),
    "this": frozenset({"his"}),
    "use": frozenset({"sue"}),
    "work": frozenset({"cork", "fork", "word", "worm"}),
    "you": frozenset({"her", "him", "them"}),
    "your": frozenset({"our"}),
}

PRODUCT_HELP_ANSWER = (
    "Archivist is a guided way to explore *Cradle of the Empire*. Ask about a person, "
    "event, theme, comparison, or argument, and Archivist searches this manuscript—not "
    "the open web—to prepare an answer from relevant passages.\n\n"
    "Manuscript answers show supporting sources you can inspect. Perspectives change the "
    "answer's voice and emphasis, not the underlying evidence. Start with any person, event, "
    "theme, comparison, or argument in the manuscript."
)


def _optimal_string_alignment_distance(value: str, target: str) -> int:
    """Return edit distance with adjacent transposition counted as one edit."""

    distances = [
        [0 for _ in range(len(target) + 1)] for _ in range(len(value) + 1)
    ]
    for value_index in range(len(value) + 1):
        distances[value_index][0] = value_index
    for target_index in range(len(target) + 1):
        distances[0][target_index] = target_index
    for value_index in range(1, len(value) + 1):
        for target_index in range(1, len(target) + 1):
            substitution_cost = int(
                value[value_index - 1] != target[target_index - 1]
            )
            distances[value_index][target_index] = min(
                distances[value_index - 1][target_index] + 1,
                distances[value_index][target_index - 1] + 1,
                distances[value_index - 1][target_index - 1] + substitution_cost,
            )
            if (
                value_index > 1
                and target_index > 1
                and value[value_index - 1] == target[target_index - 2]
                and value[value_index - 2] == target[target_index - 1]
            ):
                distances[value_index][target_index] = min(
                    distances[value_index][target_index],
                    distances[value_index - 2][target_index - 2] + 1,
                )
    return distances[-1][-1]


def _matches_approved_question(value: str, approved_questions: tuple[str, ...]) -> bool:
    value_tokens = value.split()
    fuzzy_candidates: list[tuple[int, bool]] = []
    for candidate in approved_questions:
        if value == candidate:
            return True
        if value.replace(" ", "") == candidate.replace(" ", ""):
            return True
        candidate_tokens = candidate.split()
        if len(value_tokens) != len(candidate_tokens):
            if abs(len(value_tokens) - len(candidate_tokens)) == 1:
                distance = _optimal_string_alignment_distance(value, candidate)
                if distance <= 2:
                    fuzzy_candidates.append((distance, False))
            continue
        has_semantic_collision = False
        token_distances = []
        for actual, expected in zip(value_tokens, candidate_tokens, strict=True):
            if actual in _SEMANTIC_TOKEN_ALTERNATIVES.get(expected, frozenset()):
                has_semantic_collision = True
            distance = _optimal_string_alignment_distance(actual, expected)
            is_same_letter_scramble = (
                len(expected) >= 4
                and len(actual) == len(expected)
                and sorted(actual) == sorted(expected)
                and distance <= 2
            )
            if distance > 1 and not is_same_letter_scramble:
                break
            token_distances.append(distance)
        else:
            total_distance = sum(token_distances)
            if total_distance <= _MAX_TOTAL_TYPO_DISTANCE:
                fuzzy_candidates.append(
                    (total_distance, has_semantic_collision)
                )
    if not fuzzy_candidates:
        return False
    closest_distance = min(distance for distance, _ in fuzzy_candidates)
    return any(
        distance == closest_distance and not has_semantic_collision
        for distance, has_semantic_collision in fuzzy_candidates
    )


def is_product_help_question(question: str, *, has_history: bool = False) -> bool:
    """Return whether a turn asks only how Archivist itself can help."""

    if not isinstance(question, str) or "\n" in question or "\r" in question:
        return False
    normalized = unicodedata.normalize("NFKC", question).strip().casefold().replace("’", "'")
    normalized = "".join(
        character if character.isalnum() or character in {"'", " "} else " "
        for character in normalized
    )
    normalized = _SPACE_RE.sub(" ", normalized)
    normalized = normalized.strip()
    if not normalized or len(normalized) > _MAX_QUESTION_CHARACTERS:
        return False
    if _matches_approved_question(
        normalized,
        _CONTEXT_INDEPENDENT_PRODUCT_HELP_QUESTIONS,
    ):
        return True
    return not has_history and _matches_approved_question(
        normalized,
        _FIRST_TURN_PRODUCT_HELP_QUESTIONS,
    )


def render_product_help_answer() -> str:
    """Return the fixed, source-free explanation of the reader product."""

    return PRODUCT_HELP_ANSWER


__all__ = [
    "PRODUCT_HELP_ANSWER",
    "PRODUCT_HELP_POLICY_VERSION",
    "PRODUCT_HELP_RENDERER_VERSION",
    "is_product_help_question",
    "render_product_help_answer",
]
