"""Flag possible manuscript quotation in an owner-adjudicated gold set.

The audit finds exact contiguous normalized token runs. Its report intentionally
contains only gold IDs, chunk IDs, and token counts; matching words are never
written to output.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import TextIO
import unicodedata


TOKEN_RE = re.compile(r"[^\W_]+(?:['\N{RIGHT SINGLE QUOTATION MARK}][^\W_]+)?", re.UNICODE)


class PrivacyAuditError(ValueError):
    """Raised when privacy audit inputs cannot be verified."""


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return TOKEN_RE.findall(normalized)


def _load(path: Path, *, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrivacyAuditError(f"cannot read {label} {path}: {exc}") from exc


def _verified_chunk_tokens(
    manifest: object,
    chunk_payload: object,
) -> dict[str, list[str]]:
    if not isinstance(manifest, dict) or manifest.get("manifest_schema") != (
        "archivist.corpus_manifest/1"
    ):
        raise PrivacyAuditError("manifest schema must be archivist.corpus_manifest/1")
    manifest_chunks = manifest.get("chunks")
    if not isinstance(manifest_chunks, list) or not isinstance(chunk_payload, list):
        raise PrivacyAuditError("manifest chunks and local chunk payload must be arrays")

    expected_by_id: dict[str, dict[str, object]] = {}
    for chunk in manifest_chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("chunk_id"), str):
            raise PrivacyAuditError("manifest chunks require string chunk IDs")
        expected_by_id[str(chunk["chunk_id"])] = chunk

    result: dict[str, list[str]] = {}
    for chunk in chunk_payload:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("chunk_id"), str):
            raise PrivacyAuditError("local chunks require string chunk IDs")
        chunk_id = str(chunk["chunk_id"])
        expected = expected_by_id.get(chunk_id)
        if expected is None:
            continue
        text = chunk.get("text")
        if not isinstance(text, str):
            raise PrivacyAuditError(f"local chunk {chunk_id!r} has no string text")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected.get("text_sha256"):
            raise PrivacyAuditError(f"local chunk {chunk_id!r} failed text-hash verification")
        if chunk.get("document") != expected.get("document"):
            raise PrivacyAuditError(f"local chunk {chunk_id!r} failed document verification")
        result[chunk_id] = _tokens(text)

    missing = sorted(set(expected_by_id) - set(result))
    if missing:
        raise PrivacyAuditError(f"local chunk payload is missing {len(missing)} manifest chunks")
    return result


def _longest_match_from(
    claim_tokens: list[str],
    claim_start: int,
    chunk_tokens: list[str],
    chunk_start: int,
) -> int:
    length = 0
    while (
        claim_start + length < len(claim_tokens)
        and chunk_start + length < len(chunk_tokens)
        and claim_tokens[claim_start + length] == chunk_tokens[chunk_start + length]
    ):
        length += 1
    return length


def audit_gold_privacy(
    *,
    gold_set: object,
    manifest: object,
    chunk_payload: object,
    minimum_run_tokens: int = 10,
) -> dict[str, object]:
    """Return a quotation-risk report without including any matching text."""

    if minimum_run_tokens < 5:
        raise PrivacyAuditError("minimum_run_tokens must be at least 5")
    if not isinstance(gold_set, dict) or gold_set.get("schema") != "archivist.gold/1":
        raise PrivacyAuditError("gold schema must be archivist.gold/1")
    items = gold_set.get("items")
    if not isinstance(items, list):
        raise PrivacyAuditError("gold items field must be an array")

    chunk_tokens = _verified_chunk_tokens(manifest, chunk_payload)
    ngram_positions: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    for chunk_id, tokens in chunk_tokens.items():
        for start in range(len(tokens) - minimum_run_tokens + 1):
            ngram = tuple(tokens[start : start + minimum_run_tokens])
            ngram_positions[ngram].append((chunk_id, start))

    flags: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise PrivacyAuditError("gold items require string IDs")
        claims = item.get("claims")
        if not isinstance(claims, list):
            raise PrivacyAuditError("gold items require claims arrays")
        prose_fields: list[tuple[str, str, str]] = []
        question = item.get("question")
        if not isinstance(question, str):
            raise PrivacyAuditError("gold items require string questions")
        prose_fields.append(("question", "question", question))
        for claim in claims:
            if (
                not isinstance(claim, dict)
                or not isinstance(claim.get("claim_id"), str)
                or not isinstance(claim.get("text"), str)
            ):
                raise PrivacyAuditError("gold claims require string claim_id and text")
            prose_fields.append(("claim", str(claim["claim_id"]), str(claim["text"])))

        must_not_claim = item.get("must_not_claim")
        if not isinstance(must_not_claim, list) or not all(
            isinstance(value, str) for value in must_not_claim
        ):
            raise PrivacyAuditError("gold items require string must_not_claim arrays")
        prose_fields.extend(
            ("must_not_claim", f"must_not_claim[{index}]", value)
            for index, value in enumerate(must_not_claim)
        )
        notes = item.get("notes")
        if not isinstance(notes, str):
            raise PrivacyAuditError("gold items require string notes")
        prose_fields.append(("notes", "notes", notes))

        for field, entry_id, prose in prose_fields:
            tokens = _tokens(prose)
            longest_by_chunk: dict[str, int] = {}
            for prose_start in range(len(tokens) - minimum_run_tokens + 1):
                ngram = tuple(tokens[prose_start : prose_start + minimum_run_tokens])
                for chunk_id, chunk_start in ngram_positions.get(ngram, []):
                    length = _longest_match_from(
                        tokens,
                        prose_start,
                        chunk_tokens[chunk_id],
                        chunk_start,
                    )
                    longest_by_chunk[chunk_id] = max(
                        longest_by_chunk.get(chunk_id, 0),
                        length,
                    )
            for chunk_id, matched_count in longest_by_chunk.items():
                flags.append(
                    {
                        "item_id": item["id"],
                        "field": field,
                        "entry_id": entry_id,
                        "chunk_id": chunk_id,
                        "matched_token_count": matched_count,
                    }
                )

    flags.sort(
        key=lambda flag: (
            str(flag["item_id"]),
            str(flag["field"]),
            str(flag["entry_id"]),
            str(flag["chunk_id"]),
        )
    )
    return {
        "schema": "archivist.gold_privacy_audit/2",
        "minimum_run_tokens": minimum_run_tokens,
        "flag_count": len(flags),
        "flags": flags,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flag long exact token runs without printing manuscript words."
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--minimum-run-tokens", type=int, default=10)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None, *, output: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit_gold_privacy(
            gold_set=_load(args.gold, label="gold set"),
            manifest=_load(args.manifest, label="manifest"),
            chunk_payload=_load(args.chunks, label="local chunks"),
            minimum_run_tokens=args.minimum_run_tokens,
        )
    except PrivacyAuditError as exc:
        print(f"ERROR: {exc}", file=output)
        return 2

    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(serialized, end="", file=output)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote privacy report: {args.output}", file=output)
    return 1 if report["flag_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
