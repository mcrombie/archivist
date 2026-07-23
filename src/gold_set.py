"""Validation for owner-authored Archivist gold question sets.

This module validates identifiers and structure only. It cannot decide whether
an owner's historical claim is correct or whether a chunk genuinely supports
that claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


GOLD_SCHEMA = "archivist.gold/1"
CORPUS_MANIFEST_SCHEMA = "archivist.corpus_manifest/1"
PILOT_ITEM_COUNT = 10
PILOT_MIN_STRATA = 4

STRATUM_RANGES = {
    "focused_biographical": (7, 9),
    "focused_analytical": (7, 9),
    "conceptual": (5, 7),
    "broad_thematic": (9, 11),
    "out_of_corpus": (4, 6),
    "adversarial_premise": (2, 4),
}
EXPECTED_BEHAVIORS = {"answer", "abstain"}

ValidationMode = Literal["pilot", "run-of-record"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

_TOP_LEVEL_FIELDS = {"schema", "version", "authored_against_corpus", "items"}
_ITEM_FIELDS = {
    "id",
    "question",
    "stratum",
    "expected_behavior",
    "claims",
    "relevant_chunk_ids",
    "must_not_claim",
    "notes",
}
_CLAIM_FIELDS = {"claim_id", "text", "essential", "supporting_chunk_ids"}


class GoldSetValidationError(ValueError):
    """Raised when a gold set fails one or more mechanical checks."""

    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True, slots=True)
class GoldSetSummary:
    """A concise description of a mechanically valid gold set."""

    mode: ValidationMode
    version: str
    item_count: int
    stratum_counts: dict[str, int]
    corpus_manifest_sha256: str

    @property
    def eligible_for_run_of_record(self) -> bool:
        """Whether full-set composition checks, rather than pilot checks, ran."""

        return self.mode == "run-of-record"


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file's exact bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_object(path: Path, *, label: str) -> dict[str, object]:
    """Load a JSON object with an error suitable for a command-line workflow."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GoldSetValidationError([f"{label}: cannot read {path}: {exc}"]) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoldSetValidationError([f"{label}: invalid UTF-8 JSON in {path}: {exc}"]) from exc
    if not isinstance(value, dict):
        raise GoldSetValidationError([f"{label}: top-level JSON value must be an object"])
    return value


def validate_gold_set_file(
    gold_set_path: Path,
    corpus_manifest_path: Path,
    *,
    mode: ValidationMode = "pilot",
) -> GoldSetSummary:
    """Load and validate a gold set against the exact manifest file supplied."""

    gold_set = load_json_object(gold_set_path, label="gold set")
    corpus_manifest = load_json_object(corpus_manifest_path, label="corpus manifest")
    return validate_gold_set(
        gold_set,
        corpus_manifest,
        corpus_manifest_sha256=sha256_file(corpus_manifest_path),
        mode=mode,
    )


def validate_gold_set(
    gold_set: object,
    corpus_manifest: object,
    *,
    corpus_manifest_sha256: str,
    mode: ValidationMode = "pilot",
) -> GoldSetSummary:
    """Validate ``archivist.gold/1`` without inspecting manuscript text.

    ``pilot`` requires exactly ten items spanning at least four strata and a
    ``-pilot`` prerelease marker. ``run-of-record`` enforces every target range
    in EVAL_CONTRACT.md section 3.4 and rejects prerelease versions.
    """

    if mode not in {"pilot", "run-of-record"}:
        raise ValueError(f"unsupported gold-set validation mode: {mode!r}")

    errors: list[str] = []
    if not _SHA256_RE.fullmatch(corpus_manifest_sha256):
        errors.append(
            "$manifest: corpus_manifest_sha256 must be a lowercase 64-character SHA-256"
        )

    manifest_chunk_ids, eligible_chunk_ids = _validate_manifest(corpus_manifest, errors)

    if not isinstance(gold_set, dict):
        raise GoldSetValidationError(
            [*errors, "$: gold set must be a JSON object"]
        )

    _validate_fields(gold_set, _TOP_LEVEL_FIELDS, "$", errors)
    if gold_set.get("schema") != GOLD_SCHEMA:
        errors.append(f"$.schema: must be exactly {GOLD_SCHEMA!r}")

    version = gold_set.get("version")
    version_match = _SEMVER_RE.fullmatch(version) if isinstance(version, str) else None
    if version_match is None:
        errors.append("$.version: must be a semantic version such as '1.0.0'")
        version_text = ""
    else:
        version_text = version
        prerelease = version_match.group(4)
        prerelease_tokens = prerelease.lower().split(".") if prerelease else []
        if mode == "pilot" and "pilot" not in prerelease_tokens:
            errors.append("$.version: pilot validation requires a '-pilot' prerelease marker")
        if mode == "run-of-record" and prerelease is not None:
            errors.append("$.version: run-of-record validation requires a stable version")

    authored_against = gold_set.get("authored_against_corpus")
    if not isinstance(authored_against, str) or not _SHA256_RE.fullmatch(authored_against):
        errors.append(
            "$.authored_against_corpus: must be a lowercase 64-character SHA-256"
        )
    elif authored_against != corpus_manifest_sha256:
        errors.append(
            "$.authored_against_corpus: does not match the exact corpus manifest "
            f"({corpus_manifest_sha256})"
        )

    items_value = gold_set.get("items")
    if not isinstance(items_value, list):
        errors.append("$.items: must be an array")
        items: list[object] = []
    else:
        items = items_value

    item_ids: set[str] = set()
    claim_ids: set[str] = set()
    normalized_questions: dict[str, str] = {}
    stratum_counts: Counter[str] = Counter()

    for index, item in enumerate(items):
        _validate_item(
            item,
            index=index,
            manifest_chunk_ids=manifest_chunk_ids,
            eligible_chunk_ids=eligible_chunk_ids,
            item_ids=item_ids,
            claim_ids=claim_ids,
            normalized_questions=normalized_questions,
            stratum_counts=stratum_counts,
            errors=errors,
        )

    if mode == "pilot":
        if len(items) != PILOT_ITEM_COUNT:
            errors.append(
                f"$.items: pilot must contain exactly {PILOT_ITEM_COUNT} items; "
                f"found {len(items)}"
            )
        represented = sum(count > 0 for count in stratum_counts.values())
        if represented < PILOT_MIN_STRATA:
            errors.append(
                f"$.items: pilot must span at least {PILOT_MIN_STRATA} valid strata; "
                f"found {represented}"
            )
    else:
        for stratum, (minimum, maximum) in STRATUM_RANGES.items():
            count = stratum_counts[stratum]
            if not minimum <= count <= maximum:
                errors.append(
                    f"$.items: stratum {stratum!r} requires {minimum}\N{EN DASH}{maximum} "
                    f"items for a run of record; found {count}"
                )

    if errors:
        raise GoldSetValidationError(errors)

    return GoldSetSummary(
        mode=mode,
        version=version_text,
        item_count=len(items),
        stratum_counts={
            stratum: stratum_counts[stratum] for stratum in STRATUM_RANGES
        },
        corpus_manifest_sha256=corpus_manifest_sha256,
    )


def _validate_manifest(
    corpus_manifest: object,
    errors: list[str],
) -> tuple[set[str], set[str]]:
    if not isinstance(corpus_manifest, dict):
        errors.append("$manifest: corpus manifest must be a JSON object")
        return set(), set()
    if corpus_manifest.get("manifest_schema") != CORPUS_MANIFEST_SCHEMA:
        errors.append(
            "$manifest.manifest_schema: must be exactly "
            f"{CORPUS_MANIFEST_SCHEMA!r}"
        )

    ingest = corpus_manifest.get("ingest")
    if not isinstance(ingest, dict):
        errors.append("$manifest.ingest: must be an object")
        skip_files: list[str] = []
        skip_files_valid = False
    else:
        raw_skip_files = ingest.get("skip_files")
        if (
            not isinstance(raw_skip_files, list)
            or any(not _is_nonempty_string(value) for value in raw_skip_files)
        ):
            errors.append(
                "$manifest.ingest.skip_files: must be an array of non-empty strings"
            )
            skip_files = []
            skip_files_valid = False
        else:
            skip_files = [str(value) for value in raw_skip_files]
            skip_files_valid = True
            if len(skip_files) != len(set(skip_files)):
                errors.append("$manifest.ingest.skip_files: contains duplicate values")

    chunks = corpus_manifest.get("chunks")
    if not isinstance(chunks, list):
        errors.append("$manifest.chunks: must be an array")
        return set(), set()

    chunk_ids: set[str] = set()
    eligible_chunk_ids: set[str] = set()
    for index, chunk in enumerate(chunks):
        path = f"$manifest.chunks[{index}].chunk_id"
        if not isinstance(chunk, dict):
            errors.append(f"$manifest.chunks[{index}]: must be an object")
            continue
        chunk_id = chunk.get("chunk_id")
        document = chunk.get("document")
        if not _is_nonempty_string(document):
            errors.append(
                f"$manifest.chunks[{index}].document: must be a non-empty string"
            )
        if not _is_nonempty_string(chunk_id):
            errors.append(f"{path}: must be a non-empty string")
        elif chunk_id in chunk_ids:
            errors.append(f"{path}: duplicate corpus chunk ID {chunk_id!r}")
        else:
            chunk_ids.add(chunk_id)
            if (
                skip_files_valid
                and _is_nonempty_string(document)
                and not _document_is_skipped(str(document), skip_files)
            ):
                eligible_chunk_ids.add(chunk_id)
    return chunk_ids, eligible_chunk_ids


def _document_is_skipped(document: str, skip_files: list[str]) -> bool:
    normalized = document.casefold()
    return any(skip_file.casefold() in normalized for skip_file in skip_files)


def _validate_item(
    item: object,
    *,
    index: int,
    manifest_chunk_ids: set[str],
    eligible_chunk_ids: set[str],
    item_ids: set[str],
    claim_ids: set[str],
    normalized_questions: dict[str, str],
    stratum_counts: Counter[str],
    errors: list[str],
) -> None:
    path = f"$.items[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{path}: must be an object")
        return
    _validate_fields(item, _ITEM_FIELDS, path, errors)

    item_id_value = item.get("id")
    if not _is_nonempty_string(item_id_value):
        errors.append(f"{path}.id: must be a non-empty string")
        item_id = ""
    else:
        item_id = item_id_value
        if item_id in item_ids:
            errors.append(f"{path}.id: duplicate item ID {item_id!r}")
        else:
            item_ids.add(item_id)

    question = item.get("question")
    if not _is_nonempty_string(question):
        errors.append(f"{path}.question: must be a non-empty string")
    else:
        normalized = " ".join(question.split()).casefold()
        earlier_item_id = normalized_questions.get(normalized)
        if earlier_item_id is not None:
            errors.append(
                f"{path}.question: duplicates the normalized question from "
                f"item {earlier_item_id!r}"
            )
        else:
            normalized_questions[normalized] = item_id or f"index {index}"

    stratum = item.get("stratum")
    if not isinstance(stratum, str) or stratum not in STRATUM_RANGES:
        errors.append(
            f"{path}.stratum: must be one of {', '.join(repr(key) for key in STRATUM_RANGES)}"
        )
    else:
        stratum_counts[stratum] += 1

    expected_behavior = item.get("expected_behavior")
    if (
        not isinstance(expected_behavior, str)
        or expected_behavior not in EXPECTED_BEHAVIORS
    ):
        errors.append(
            f"{path}.expected_behavior: must be 'answer' or 'abstain'"
        )

    relevant_chunk_ids = _validate_string_list(
        item.get("relevant_chunk_ids"),
        path=f"{path}.relevant_chunk_ids",
        manifest_chunk_ids=manifest_chunk_ids,
        eligible_chunk_ids=eligible_chunk_ids,
        is_location=True,
        allow_empty=True,
        errors=errors,
    )
    _validate_string_list(
        item.get("must_not_claim"),
        path=f"{path}.must_not_claim",
        manifest_chunk_ids=manifest_chunk_ids,
        eligible_chunk_ids=eligible_chunk_ids,
        is_location=False,
        allow_empty=True,
        errors=errors,
    )
    if not isinstance(item.get("notes"), str):
        errors.append(f"{path}.notes: must be a string")

    claims_value = item.get("claims")
    if not isinstance(claims_value, list):
        errors.append(f"{path}.claims: must be an array")
        claims: list[object] = []
    else:
        claims = claims_value

    supporting_union: set[str] = set()
    has_essential_claim = False
    for claim_index, claim in enumerate(claims):
        claim_path = f"{path}.claims[{claim_index}]"
        if not isinstance(claim, dict):
            errors.append(f"{claim_path}: must be an object")
            continue
        _validate_fields(claim, _CLAIM_FIELDS, claim_path, errors)

        claim_id = claim.get("claim_id")
        if not _is_nonempty_string(claim_id):
            errors.append(f"{claim_path}.claim_id: must be a non-empty string")
        else:
            if item_id and not claim_id.startswith(f"{item_id}."):
                errors.append(
                    f"{claim_path}.claim_id: must be prefixed by {item_id!r} plus '.'"
                )
            if claim_id in claim_ids:
                errors.append(f"{claim_path}.claim_id: duplicate claim ID {claim_id!r}")
            else:
                claim_ids.add(claim_id)

        if not _is_nonempty_string(claim.get("text")):
            errors.append(f"{claim_path}.text: must be a non-empty string")
        essential = claim.get("essential")
        if not isinstance(essential, bool):
            errors.append(f"{claim_path}.essential: must be a boolean")
        elif essential:
            has_essential_claim = True

        supporting = _validate_string_list(
            claim.get("supporting_chunk_ids"),
            path=f"{claim_path}.supporting_chunk_ids",
            manifest_chunk_ids=manifest_chunk_ids,
            eligible_chunk_ids=eligible_chunk_ids,
            is_location=True,
            allow_empty=False,
            errors=errors,
        )
        supporting_union.update(supporting)

    missing_relevant = supporting_union - set(relevant_chunk_ids)
    if missing_relevant:
        errors.append(
            f"{path}.relevant_chunk_ids: must contain every supporting chunk ID; "
            f"missing {sorted(missing_relevant)!r}"
        )

    if expected_behavior == "abstain":
        if claims:
            errors.append(
                f"{path}.claims: must be empty when expected_behavior is 'abstain'"
            )
        if relevant_chunk_ids:
            errors.append(
                f"{path}.relevant_chunk_ids: must be empty when "
                "expected_behavior is 'abstain'"
            )
    elif expected_behavior == "answer" and not has_essential_claim:
        errors.append(
            f"{path}.claims: an 'answer' item must have at least one essential claim"
        )


def _validate_string_list(
    value: object,
    *,
    path: str,
    manifest_chunk_ids: set[str],
    eligible_chunk_ids: set[str],
    is_location: bool,
    allow_empty: bool,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path}: must be an array")
        return []
    if not value and not allow_empty:
        errors.append(f"{path}: must contain at least one chunk ID")

    result: list[str] = []
    seen: set[str] = set()
    for index, member in enumerate(value):
        member_path = f"{path}[{index}]"
        if not _is_nonempty_string(member):
            errors.append(f"{member_path}: must be a non-empty string")
            continue
        if member in seen:
            errors.append(f"{member_path}: duplicate value {member!r}")
        else:
            seen.add(member)
            result.append(member)
        if is_location and member not in manifest_chunk_ids:
            errors.append(
                f"{member_path}: chunk ID {member!r} is absent from the corpus manifest"
            )
        elif is_location and member not in eligible_chunk_ids:
            errors.append(
                f"{member_path}: chunk ID {member!r} is not retrieval-eligible "
                "under the corpus manifest skip_files"
            )
    return result


def _validate_fields(
    value: dict[str, object],
    expected: set[str],
    path: str,
    errors: list[str],
) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing:
        errors.append(f"{path}: missing required fields {missing!r}")
    if extra:
        errors.append(f"{path}: unexpected fields {extra!r}")


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
