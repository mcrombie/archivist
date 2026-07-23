from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_staged_index.py"
SPEC = importlib.util.spec_from_file_location("build_staged_index", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
staged_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staged_index)


class FakeUsageLedger:
    def __init__(self, *, hard_limit_reached: bool = False) -> None:
        self.hard_limit_reached = hard_limit_reached
        self.get_settings_calls = 0
        self.update_settings_calls: list[dict[str, object]] = []
        self.budget_state_calls = 0

    def get_settings(self):
        self.get_settings_calls += 1
        return {
            "monthly_budget_usd": 10.0,
            "warning_threshold_percent": 80,
            "hard_limit_enabled": self.hard_limit_reached,
        }

    def update_settings(self, **settings):
        self.update_settings_calls.append(settings)
        return settings

    def budget_state(self):
        self.budget_state_calls += 1
        return {
            "hard_limit_enabled": self.hard_limit_reached,
            "exceeded": self.hard_limit_reached,
        }


class FakeEmbeddings:
    def __init__(self, *, invalid_indices: bool = False) -> None:
        self.invalid_indices = invalid_indices
        self.requests: list[dict[str, object]] = []

    def create(self, **request):
        self.requests.append(request)
        data = []
        for index, _text in enumerate(request["input"]):
            response_index = index + 1 if self.invalid_indices else index
            data.append(
                SimpleNamespace(
                    index=response_index,
                    embedding=[float(index) + 0.25, 0.5],
                )
            )
        return SimpleNamespace(data=data)


class FakeCollection:
    def __init__(self, metadata):
        self.metadata = dict(metadata)
        self.configuration = {
            "hnsw": {"space": metadata["hnsw:space"]},
            "spann": None,
            "embedding_function": None,
        }
        self.records: dict[str, dict[str, object]] = {}

    def add(self, *, ids, embeddings, metadatas):
        assert len(ids) == len(embeddings) == len(metadatas)
        for chunk_id, embedding, metadata in zip(
            ids,
            embeddings,
            metadatas,
            strict=True,
        ):
            self.records[chunk_id] = {
                "embedding": list(embedding),
                "metadata": dict(metadata),
                "document": None,
            }

    def count(self):
        return len(self.records)

    def get(self, *, include):
        assert include == ["embeddings", "documents", "metadatas"]
        ids = list(reversed(self.records))
        return {
            "ids": ids,
            "embeddings": [self.records[chunk_id]["embedding"] for chunk_id in ids],
            "documents": [self.records[chunk_id]["document"] for chunk_id in ids],
            "metadatas": [self.records[chunk_id]["metadata"] for chunk_id in ids],
        }


class FakeChromaClient:
    def __init__(self, factory, *, reopen: bool) -> None:
        self.factory = factory
        self.reopen = reopen
        self.closed = False

    def create_collection(self, *, name, metadata, embedding_function):
        assert name == "manuscript"
        assert embedding_function is None
        assert self.factory.collection is None
        self.factory.collection = FakeCollection(metadata)
        return self.factory.collection

    def get_collection(self, *, name, embedding_function):
        assert name == "manuscript"
        assert embedding_function is None
        assert self.factory.collection is not None
        if self.reopen and not self.factory.corruption_applied:
            self.factory.apply_corruption()
        return self.factory.collection

    def close(self):
        self.closed = True
        self.factory.closed_clients += 1


class FakeChromaFactory:
    def __init__(self, *, corruption: str | None = None) -> None:
        self.calls: list[str] = []
        self.collection: FakeCollection | None = None
        self.corruption = corruption
        self.corruption_applied = False
        self.closed_clients = 0

    def __call__(self, *, path):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "fake-chroma.sqlite3").touch(exist_ok=True)
        self.calls.append(path)
        return FakeChromaClient(self, reopen=len(self.calls) > 1)

    def apply_corruption(self):
        self.corruption_applied = True
        assert self.collection is not None
        if self.corruption == "metadata":
            first = next(iter(self.collection.records.values()))
            first["metadata"] = {**first["metadata"], "text": "corrupted"}
        elif self.corruption == "embedding":
            first = next(iter(self.collection.records.values()))
            first["embedding"] = [9.0, 9.0]
        elif self.corruption == "configuration":
            self.collection.configuration["hnsw"]["space"] = "cosine"


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_corpus(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    chunks = [
        {
            "document": "01_Chapter.md",
            "chapter_title": "Chapter",
            "chunk_id": "01_Chapter_001",
            "paragraph_start": 1,
            "paragraph_end": 2,
            "text": "A synthetic passage used only for an index test.",
        },
        {
            "document": "02_Table of Contents.md",
            "chapter_title": "Contents",
            "chunk_id": "02_Table of Contents_001",
            "paragraph_start": 1,
            "paragraph_end": 1,
            "text": "Synthetic contents that the shared filter excludes.",
        },
    ]
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    chunks_sha = hashlib.sha256(chunks_path.read_bytes()).hexdigest()
    documents = [
        {
            "filename": "01_Chapter.md",
            "sha256": _sha_text("synthetic chapter source"),
            "paragraph_count": 2,
            "chunk_count": 1,
            "chapter_title": "Chapter",
        },
        {
            "filename": "02_Table of Contents.md",
            "sha256": _sha_text("synthetic contents source"),
            "paragraph_count": 1,
            "chunk_count": 1,
            "chapter_title": "Contents",
        },
    ]
    manifest = {
        "manifest_schema": "archivist.corpus_manifest/1",
        "title": "Synthetic Corpus",
        "source": {
            "kind": "docx",
            "filename": "synthetic.docx",
            "sha256": _sha_text("synthetic source"),
            "byte_count": 16,
        },
        "documents": documents,
        "chunks_sha256": chunks_sha,
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "document": chunk["document"],
                "paragraph_start": chunk["paragraph_start"],
                "paragraph_end": chunk["paragraph_end"],
                "text_sha256": _sha_text(chunk["text"]),
                "char_count": len(chunk["text"]),
            }
            for chunk in chunks
        ],
        "extraction": {
            "document_count": 2,
            "paragraph_count": 3,
            "chunk_count": 2,
            "searchable_chunk_count": 1,
            "skipped_document_count": 1,
        },
        "ingest": {
            "paragraphs_per_chunk": 4,
            "paragraph_overlap": 1,
            "ingest_commit": "a" * 40,
            "skip_files": sorted(staged_index.SKIP_FILES),
        },
        "store": {
            "hnsw_space": "l2",
            "embedding_model": "text-embedding-3-small",
            "collection_name": "manuscript",
            "embedded_chunk_count": 0,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return chunks_path, manifest_path


def _build(
    chunks_path: Path,
    manifest_path: Path,
    target: Path,
    *,
    ledger: FakeUsageLedger | None = None,
    embeddings: FakeEmbeddings | None = None,
    chroma_factory: FakeChromaFactory | None = None,
    allow_over_budget: bool = False,
):
    ledger = ledger or FakeUsageLedger()
    embeddings = embeddings or FakeEmbeddings()
    chroma_factory = chroma_factory or FakeChromaFactory()
    result = staged_index.build_staged_index(
        chunks_path,
        manifest_path,
        target,
        openai_client=SimpleNamespace(embeddings=embeddings),
        chroma_client_factory=chroma_factory,
        usage_ledger=ledger,
        batch_size=1,
        allow_over_budget=allow_over_budget,
    )
    return result, ledger, embeddings, chroma_factory


def test_builds_filtered_index_reopens_store_and_updates_manifest(tmp_path):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    target = tmp_path / "fresh-index"

    embedded_count, ledger, embeddings, chroma_factory = _build(
        chunks_path,
        manifest_path,
        target,
    )

    assert embedded_count == 1
    assert chroma_factory.calls == [str(target.resolve()), str(target.resolve())]
    assert chroma_factory.closed_clients == 2
    assert ledger.get_settings_calls == 1
    assert len(ledger.update_settings_calls) == 1
    assert ledger.budget_state_calls == 2  # preflight plus the one batch
    assert len(embeddings.requests) == 1
    assert embeddings.requests[0] == {
        "model": "text-embedding-3-small",
        "input": ["A synthetic passage used only for an index test."],
    }
    assert chroma_factory.collection is not None
    assert chroma_factory.collection.metadata == {
        "hnsw:space": "l2",
        "embedding_model": "text-embedding-3-small",
        "chunks_sha256": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
    }
    assert set(chroma_factory.collection.records) == {"01_Chapter_001"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["store"] == {
        "hnsw_space": "l2",
        "embedding_model": "text-embedding-3-small",
        "collection_name": "manuscript",
        "embedded_chunk_count": 1,
    }


def test_real_chroma_round_trip_uses_persisted_l2_configuration_without_network(
    tmp_path,
):
    import chromadb

    chunks_path, manifest_path = _write_corpus(tmp_path)
    target = tmp_path / "real-chroma-index"

    result = staged_index.build_staged_index(
        chunks_path,
        manifest_path,
        target,
        openai_client=SimpleNamespace(embeddings=FakeEmbeddings()),
        chroma_client_factory=chromadb.PersistentClient,
        usage_ledger=FakeUsageLedger(),
        batch_size=1,
    )

    assert result == 1
    with chromadb.PersistentClient(path=str(target)) as client:
        collection = client.get_collection(name="manuscript", embedding_function=None)
        assert collection.configuration["hnsw"]["space"] == "l2"
        assert collection.count() == 1


def test_refuses_nonempty_stale_target_without_embedding_or_ledger_write(tmp_path):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    target = tmp_path / "stale-index"
    target.mkdir()
    (target / "chroma.sqlite3").write_bytes(b"old index")
    ledger = FakeUsageLedger()
    embeddings = FakeEmbeddings()
    chroma_factory = FakeChromaFactory()

    with pytest.raises(staged_index.StagedIndexError, match="must be empty"):
        _build(
            chunks_path,
            manifest_path,
            target,
            ledger=ledger,
            embeddings=embeddings,
            chroma_factory=chroma_factory,
        )

    assert ledger.get_settings_calls == 0
    assert embeddings.requests == []
    assert chroma_factory.calls == []


def test_hard_limit_refuses_before_client_creation_and_override_is_explicit(tmp_path):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    ledger = FakeUsageLedger(hard_limit_reached=True)
    embeddings = FakeEmbeddings()
    chroma_factory = FakeChromaFactory()

    with pytest.raises(staged_index.StagedIndexError, match="hard monthly API cost limit"):
        _build(
            chunks_path,
            manifest_path,
            tmp_path / "refused-index",
            ledger=ledger,
            embeddings=embeddings,
            chroma_factory=chroma_factory,
        )

    assert embeddings.requests == []
    assert chroma_factory.calls == []

    override_ledger = FakeUsageLedger(hard_limit_reached=True)
    result, override_ledger, embeddings, chroma_factory = _build(
        chunks_path,
        manifest_path,
        tmp_path / "approved-index",
        ledger=override_ledger,
        allow_over_budget=True,
    )
    assert result == 1
    assert len(embeddings.requests) == 1
    assert override_ledger.budget_state_calls == 2
    assert len(chroma_factory.calls) == 2


@pytest.mark.parametrize(
    "invalid_case, message",
    [
        ("schema", "manifest_schema"),
        ("documents_shape", "documents"),
        ("ingest_shape", "ingest"),
        ("skip_files", "skip_files"),
        ("store_shape", "store"),
        ("chapter_relationship", "chapter title"),
        ("paragraph_bounds", "paragraph bounds"),
    ],
)
def test_refuses_invalid_manifest_shapes_before_any_side_effect(
    tmp_path,
    invalid_case,
    message,
):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if invalid_case == "schema":
        manifest["manifest_schema"] = "archivist.corpus_manifest/2"
    elif invalid_case == "documents_shape":
        manifest["documents"] = {}
    elif invalid_case == "ingest_shape":
        manifest["ingest"] = []
    elif invalid_case == "skip_files":
        manifest["ingest"]["skip_files"] = ["different.md"]
    elif invalid_case == "store_shape":
        manifest["store"] = []
    elif invalid_case == "chapter_relationship":
        manifest["documents"][0]["chapter_title"] = "Different"
    elif invalid_case == "paragraph_bounds":
        manifest["documents"][0]["paragraph_count"] = 1
        manifest["extraction"]["paragraph_count"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ledger = FakeUsageLedger()
    embeddings = FakeEmbeddings()
    chroma_factory = FakeChromaFactory()

    with pytest.raises(staged_index.StagedIndexError, match=message):
        _build(
            chunks_path,
            manifest_path,
            tmp_path / f"invalid-{invalid_case}",
            ledger=ledger,
            embeddings=embeddings,
            chroma_factory=chroma_factory,
        )

    assert ledger.get_settings_calls == 0
    assert embeddings.requests == []
    assert chroma_factory.calls == []


def test_refuses_whole_file_and_per_chunk_sha_mismatches(tmp_path):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["chunks_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(staged_index.StagedIndexError, match="Manifest/chunks SHA mismatch"):
        _build(chunks_path, manifest_path, tmp_path / "whole-sha-index")

    chunks_path, manifest_path = _write_corpus(tmp_path / "second")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["chunks"][0]["text_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(staged_index.StagedIndexError, match="text SHA mismatch"):
        _build(chunks_path, manifest_path, tmp_path / "text-sha-index")


def test_rejects_embedding_response_out_of_order_and_preserves_manifest(tmp_path):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    original_manifest = manifest_path.read_bytes()
    embeddings = FakeEmbeddings(invalid_indices=True)

    with pytest.raises(staged_index.StagedIndexError, match="indices"):
        _build(
            chunks_path,
            manifest_path,
            tmp_path / "invalid-response-index",
            embeddings=embeddings,
        )

    assert len(embeddings.requests) == 1
    assert manifest_path.read_bytes() == original_manifest


@pytest.mark.parametrize("corruption", ["metadata", "embedding", "configuration"])
def test_corrupted_reopened_persistence_leaves_manifest_bytes_unchanged(
    tmp_path,
    corruption,
):
    chunks_path, manifest_path = _write_corpus(tmp_path)
    original_manifest = manifest_path.read_bytes()
    chroma_factory = FakeChromaFactory(corruption=corruption)

    with pytest.raises(staged_index.StagedIndexError, match="Persisted"):
        _build(
            chunks_path,
            manifest_path,
            tmp_path / f"corrupt-{corruption}-index",
            chroma_factory=chroma_factory,
        )

    assert chroma_factory.closed_clients == 2
    assert manifest_path.read_bytes() == original_manifest
    assert (tmp_path / f"corrupt-{corruption}-index").exists()
