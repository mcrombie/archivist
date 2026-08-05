"""Progress signals and disclosure-safe provisional claims for answer delivery.

These signals describe application stages, not model reasoning.  Callers must
never attach prompts, queries, evidence, source text, diagnostics, or exception
details to them.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum


logger = logging.getLogger(__name__)

ANSWER_STREAM_SCHEMA = "archivist.answer_stream/2"
ANSWER_STREAM_MEDIA_TYPE = "application/x-ndjson"
MAX_STRUCTURED_STREAM_CHARACTERS = 1_000_000
MAX_PROGRESSIVE_LEAD_CHARACTERS = 320
MAX_PROGRESSIVE_LEAD_WORDS = 45

_TERMINAL_SOURCE_CITATION = re.compile(
    r"\s*\[Source\s+\d+(?:\s*,\s*Source\s+\d+)*\](?=[.!?]$)"
)
_WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)
_QUESTION_ANCHOR_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "among",
        "and",
        "are",
        "because",
        "before",
        "book",
        "could",
        "does",
        "did",
        "explain",
        "for",
        "from",
        "happen",
        "happened",
        "have",
        "how",
        "history",
        "manuscript",
        "should",
        "into",
        "its",
        "over",
        "than",
        "that",
        "their",
        "them",
        "then",
        "the",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "versus",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whose",
        "why",
        "with",
        "were",
        "was",
        "would",
    }
)


class AnswerProgressStage(StrEnum):
    ACCEPTED = "accepted"
    CHECKING_CORPUS = "checking_corpus"
    RESOLVING_QUESTION = "resolving_question"
    PLANNING_SEARCH = "planning_search"
    RETRIEVING_SOURCES = "retrieving_sources"
    CHECKING_EVIDENCE = "checking_evidence"
    PREPARING_CONTEXT = "preparing_context"
    GENERATING_ANSWER = "generating_answer"
    VALIDATING_ANSWER = "validating_answer"
    CHECKING_RELEASE = "checking_release"


class ProviderStreamMilestone(StrEnum):
    """Text-free lifecycle events emitted by one streamed provider response."""

    FIRST_DELTA = "first_provider_delta"
    TERMINAL = "provider_terminal"


PROGRESS_MESSAGES: dict[AnswerProgressStage, str] = {
    AnswerProgressStage.ACCEPTED: "Request accepted.",
    AnswerProgressStage.CHECKING_CORPUS: "Checking manuscript availability.",
    AnswerProgressStage.RESOLVING_QUESTION: "Resolving conversation context.",
    AnswerProgressStage.PLANNING_SEARCH: "Planning a source search.",
    AnswerProgressStage.RETRIEVING_SOURCES: "Retrieving manuscript evidence.",
    AnswerProgressStage.CHECKING_EVIDENCE: "Checking evidence sufficiency.",
    AnswerProgressStage.PREPARING_CONTEXT: "Preparing source context.",
    AnswerProgressStage.GENERATING_ANSWER: "Drafting a source-grounded answer.",
    AnswerProgressStage.VALIDATING_ANSWER: "Validating grounding and citations.",
    AnswerProgressStage.CHECKING_RELEASE: "Applying public release safeguards.",
}

ProgressCallback = Callable[[AnswerProgressStage], None]
ProviderStreamMilestoneCallback = Callable[[ProviderStreamMilestone], None]


@dataclass(frozen=True, slots=True)
class CheckedClaimCandidate:
    """One locally checked factual unit plus private release-gate context.

    Only ``paragraph`` and ``text`` may cross the NDJSON boundary.  The chunk
    collections exist solely so the public web adapter can synchronously apply
    locator and cumulative-verbatim checks before notifying its best-effort
    stream observer.
    """

    paragraph: int
    text: str
    source_chunks: tuple[Mapping[str, object], ...]
    audit_chunks: tuple[Mapping[str, object], ...]


CheckedClaimCallback = Callable[[CheckedClaimCandidate], None]


def emit_checked_claim(
    callback: CheckedClaimCallback | None,
    candidate: CheckedClaimCandidate,
) -> None:
    """Notify presentation after local checks without affecting the answer run."""

    if callback is None:
        return
    try:
        callback(candidate)
    except Exception:
        logger.debug("Checked-claim observer failed", exc_info=True)


def emit_provider_stream_milestone(
    callback: ProviderStreamMilestoneCallback | None,
    milestone: ProviderStreamMilestone,
) -> None:
    """Emit timing-only provider lifecycle without affecting the paid run."""

    if callback is None:
        return
    try:
        callback(milestone)
    except Exception:
        logger.debug("Provider-stream milestone observer failed", exc_info=True)


class IncrementalJSONArrayItems:
    """Extract only complete JSON values from one named top-level array.

    Responses Structured Outputs still arrive as JSON text deltas.  This
    scanner never exposes those deltas.  It waits for an entire array member to
    be decodable, then returns that Python value to the caller for schema and
    evidence validation.  The complete response is parsed independently after
    ``response.completed``; this helper is only the provisional-delivery path.
    """

    def __init__(
        self,
        field_name: str,
        *,
        maximum_characters: int = MAX_STRUCTURED_STREAM_CHARACTERS,
    ) -> None:
        if not field_name:
            raise ValueError("field_name must be nonblank")
        if maximum_characters < 1:
            raise ValueError("maximum_characters must be positive")
        self._field_name = field_name
        self._maximum_characters = maximum_characters
        self._buffer = ""
        self._cursor = 0
        self._phase = "root_start"
        self._pending_key: str | None = None
        self._done = False
        self._decoder = json.JSONDecoder()

    @property
    def done(self) -> bool:
        return self._done

    def feed(self, delta: str) -> tuple[object, ...]:
        if not isinstance(delta, str):
            raise TypeError("structured response delta must be text")
        if self._done:
            return ()
        self._buffer += delta
        if len(self._buffer) > self._maximum_characters:
            raise ValueError("structured response exceeded the incremental buffer limit")

        items: list[object] = []
        while not self._done:
            if self._phase == "root_start":
                cursor = self._skip_whitespace(self._cursor)
                if cursor >= len(self._buffer):
                    break
                if self._buffer[cursor] != "{":
                    raise ValueError("structured response must be a top-level object")
                self._cursor = cursor + 1
                self._phase = "root_key_or_end"
                continue

            if self._phase == "root_key_or_end":
                cursor = self._skip_whitespace(self._cursor)
                if cursor >= len(self._buffer):
                    break
                if self._buffer[cursor] == "}":
                    raise ValueError(
                        f"structured response has no top-level {self._field_name!r} field"
                    )
                if self._buffer[cursor] != '"':
                    raise ValueError("structured response expected a top-level object key")
                decoded = self._decode_at(cursor)
                if decoded is None:
                    break
                key, end = decoded
                if not isinstance(key, str):  # pragma: no cover - JSON grammar guard
                    raise ValueError("structured response object key is not text")
                self._pending_key = key
                self._cursor = end
                self._phase = "root_colon"
                continue

            if self._phase == "root_colon":
                cursor = self._skip_whitespace(self._cursor)
                if cursor >= len(self._buffer):
                    break
                if self._buffer[cursor] != ":":
                    raise ValueError("structured response expected ':' after object key")
                self._cursor = cursor + 1
                self._phase = "root_value"
                continue

            if self._phase == "root_value":
                cursor = self._skip_whitespace(self._cursor)
                if cursor >= len(self._buffer):
                    break
                if self._pending_key == self._field_name:
                    if self._buffer[cursor] != "[":
                        raise ValueError("structured claim field is not an array")
                    self._cursor = cursor + 1
                    self._phase = "array_first_or_end"
                    continue

                decoded = self._decode_at(cursor)
                if decoded is None:
                    break
                value, end = decoded
                delimiter = self._skip_whitespace(end)
                if delimiter >= len(self._buffer):
                    # In particular, do not mistake a prefix of a streamed JSON
                    # number for the complete value before its delimiter arrives.
                    break
                if self._number_prefix_can_continue(
                    value=self._buffer[cursor:end],
                    decoded_value=value,
                    delimiter=delimiter,
                    decoded_end=end,
                ):
                    break
                if self._buffer[delimiter] == ",":
                    self._cursor = delimiter + 1
                    self._pending_key = None
                    self._phase = "root_key_or_end"
                    continue
                if self._buffer[delimiter] == "}":
                    raise ValueError(
                        f"structured response has no top-level {self._field_name!r} field"
                    )
                raise ValueError("structured response expected ',' between object fields")

            if self._phase in {"array_first_or_end", "array_item_required"}:
                cursor = self._skip_whitespace(self._cursor)
                if cursor >= len(self._buffer):
                    break
                if self._buffer[cursor] == "]":
                    if self._phase == "array_item_required":
                        raise ValueError("structured claim array has a trailing comma")
                    self._cursor = cursor + 1
                    self._done = True
                    break
                if self._buffer[cursor] == ",":
                    raise ValueError("structured claim array has an unexpected comma")

                decoded = self._decode_at(cursor)
                if decoded is None:
                    # A member split across provider deltas is the normal case.
                    break
                value, end = decoded
                delimiter = self._skip_whitespace(end)
                if delimiter >= len(self._buffer):
                    # A decoded value is not yet known to be an array member.
                    # Wait for ',' or ']' before exposing it to validation.
                    break
                if self._number_prefix_can_continue(
                    value=self._buffer[cursor:end],
                    decoded_value=value,
                    delimiter=delimiter,
                    decoded_end=end,
                ):
                    break
                if self._buffer[delimiter] == ",":
                    items.append(value)
                    self._cursor = delimiter + 1
                    self._phase = "array_item_required"
                    continue
                if self._buffer[delimiter] == "]":
                    items.append(value)
                    self._cursor = delimiter + 1
                    self._done = True
                    break
                raise ValueError("structured claim array expected ',' between members")

            raise RuntimeError(f"unknown incremental JSON phase: {self._phase}")
        return tuple(items)

    def _skip_whitespace(self, cursor: int) -> int:
        while cursor < len(self._buffer) and self._buffer[cursor] in " \t\r\n":
            cursor += 1
        return cursor

    def _decode_at(self, cursor: int) -> tuple[object, int] | None:
        try:
            return self._decoder.raw_decode(self._buffer, cursor)
        except json.JSONDecodeError:
            return None

    def _number_prefix_can_continue(
        self,
        *,
        value: str,
        decoded_value: object,
        delimiter: int,
        decoded_end: int,
    ) -> bool:
        """Return whether a decoded number may only be a streamed prefix.

        ``JSONDecoder.raw_decode`` legitimately decodes ``1`` from the partial
        delta ``1e``.  Treating the ``e`` as a bad delimiter would make valid
        JSON depend on provider chunk boundaries.  Whitespace ends a JSON
        number, so only an immediately adjacent suffix can extend it.
        """

        if isinstance(decoded_value, bool) or not isinstance(
            decoded_value, (int, float)
        ):
            return False
        if delimiter != decoded_end:
            return False
        suffix = self._buffer[decoded_end:]
        return self._is_json_number_prefix(value + suffix)

    @staticmethod
    def _is_json_number_prefix(value: str) -> bool:
        if not value:
            return True
        cursor = 0
        if value[cursor] == "-":
            cursor += 1
            if cursor == len(value):
                return True

        if value[cursor] == "0":
            cursor += 1
        elif value[cursor] in "123456789":
            cursor += 1
            while cursor < len(value) and value[cursor].isdigit():
                cursor += 1
        else:
            return False

        if cursor == len(value):
            return True
        if value[cursor] == ".":
            cursor += 1
            if cursor == len(value):
                return True
            fraction_start = cursor
            while cursor < len(value) and value[cursor].isdigit():
                cursor += 1
            if cursor == fraction_start:
                return False
            if cursor == len(value):
                return True

        if cursor < len(value) and value[cursor] in "eE":
            cursor += 1
            if cursor == len(value):
                return True
            if value[cursor] in "+-":
                cursor += 1
                if cursor == len(value):
                    return True
            while cursor < len(value) and value[cursor].isdigit():
                cursor += 1
            return cursor == len(value)

        return False


def validate_progressive_lead(
    text: str,
    *,
    question_anchors: tuple[str, ...] = (),
) -> None:
    """Fail closed unless the first provisional fact is short and on-subject.

    Atomic generation schemas already restrict a factual unit to one sentence,
    which is within the reader-facing one-to-two sentence lead contract.  This
    release check adds deterministic size limits and, when the application has
    trustworthy subject anchors, requires the lead to name at least one of
    them.  Prompting still owns rhetorical directness; this function is only a
    conservative mechanical boundary for prose shown before terminal review.
    """

    if not isinstance(text, str):
        raise ValueError("progressive lead must be text")
    body = _TERMINAL_SOURCE_CITATION.sub("", text).strip()
    words = _WORD_PATTERN.findall(body)
    if (
        not body
        or len(body) > MAX_PROGRESSIVE_LEAD_CHARACTERS
        or len(words) > MAX_PROGRESSIVE_LEAD_WORDS
    ):
        raise ValueError("progressive lead exceeds the concise-answer boundary")

    body_tokens = {token.casefold() for token in words}
    anchor_tokens = {
        token.casefold()
        for anchor in question_anchors
        if isinstance(anchor, str)
        for token in _WORD_PATTERN.findall(anchor)
        if len(token) >= 3 and token.casefold() not in _QUESTION_ANCHOR_STOPWORDS
    }
    if anchor_tokens and body_tokens.isdisjoint(anchor_tokens):
        raise ValueError("progressive lead does not name the question subject")


def emit_progress(
    callback: ProgressCallback | None,
    stage: AnswerProgressStage,
) -> None:
    """Emit a fixed stage without allowing UI delivery to affect an answer run."""

    if callback is None:
        return
    try:
        callback(stage)
    except Exception:
        # Progress is presentation. A disconnected or faulty observer must not
        # cancel a paid answer run or alter its measured result.
        logger.debug("Answer progress observer failed", exc_info=True)


__all__ = [
    "ANSWER_STREAM_MEDIA_TYPE",
    "ANSWER_STREAM_SCHEMA",
    "AnswerProgressStage",
    "CheckedClaimCallback",
    "CheckedClaimCandidate",
    "IncrementalJSONArrayItems",
    "MAX_PROGRESSIVE_LEAD_CHARACTERS",
    "MAX_PROGRESSIVE_LEAD_WORDS",
    "MAX_STRUCTURED_STREAM_CHARACTERS",
    "PROGRESS_MESSAGES",
    "ProgressCallback",
    "ProviderStreamMilestone",
    "ProviderStreamMilestoneCallback",
    "emit_checked_claim",
    "emit_progress",
    "emit_provider_stream_milestone",
    "validate_progressive_lead",
]
