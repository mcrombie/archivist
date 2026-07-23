from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "reuse_filtered_index.py"
SPEC = importlib.util.spec_from_file_location("reuse_filtered_index", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
reused_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reused_index)


def _record(
    record_id: str,
    number: float,
    document: str,
    *,
    stored_document: str | None = None,
) -> dict[str, object]:
    return {
        "id": record_id,
        "embedding": [number, number + 0.25],
        "metadata": {
            "chunk_id": record_id,
            "document": document,
            "text": f"Synthetic text for {record_id}.",
            "paragraph_start": int(number),
        },
        "document": stored_document,
    }


class FakeCollection:
    def __init__(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
        configuration: dict[str, object] | None = None,
        records: list[dict[str, object]] | None = None,
        corruption: str | None = None,
    ) -> None:
        self.name = name
        self.metadata = copy.deepcopy(metadata)
        self.configuration = copy.deepcopy(
            configuration
            or {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100,
                    "ef_search": 100,
                    "max_neighbors": 16,
                    "resize_factor": 1.2,
                    "sync_threshold": 1000,
                },
                "spann": None,
                "embedding_function": None,
            }
        )
        self.records = {
            str(record["id"]): copy.deepcopy(record) for record in records or []
        }
        self.corruption = corruption
        self.add_calls = 0

    def count(self) -> int:
        return len(self.records)

    def get(self, *, include):
        assert include == ["embeddings", "documents", "metadatas"]
        ids = list(reversed(self.records))
        return {
            "ids": ids,
            "embeddings": [self.records[record_id]["embedding"] for record_id in ids],
            "documents": [self.records[record_id]["document"] for record_id in ids],
            "metadatas": [self.records[record_id]["metadata"] for record_id in ids],
        }

    def add(self, *, ids, embeddings, metadatas, documents=None) -> None:
        self.add_calls += 1
        for position, record_id in enumerate(ids):
            embedding = list(embeddings[position])
            metadata = copy.deepcopy(metadatas[position])
            document = documents[position] if documents is not None else None
            if self.corruption == "embedding":
                embedding[0] += 1.0
            elif self.corruption == "metadata":
                metadata["text"] = "Synthetic corruption."
            elif self.corruption == "document":
                document = "Synthetic corruption."
            self.records[record_id] = {
                "id": record_id,
                "embedding": embedding,
                "metadata": metadata,
                "document": document,
            }


class FakeClient:
    def __init__(
        self,
        collections: dict[str, FakeCollection],
        *,
        target_corruption: str | None = None,
    ) -> None:
        self.collections = collections
        self.target_corruption = target_corruption
        self.closed = False
        self.create_calls = 0

    def list_collections(self):
        return list(self.collections.values())

    def get_collection(self, *, name, embedding_function):
        assert embedding_function is None
        return self.collections[name]

    def create_collection(
        self,
        *,
        name,
        configuration,
        embedding_function,
        metadata=None,
    ):
        assert embedding_function is None
        self.create_calls += 1
        collection = FakeCollection(
            name,
            metadata=metadata,
            configuration={
                "hnsw": copy.deepcopy(configuration["hnsw"]),
                "spann": None,
                "embedding_function": None,
            },
            corruption=self.target_corruption,
        )
        self.collections[name] = collection
        return collection

    def close(self):
        self.closed = True


class FakeClientFactory:
    def __init__(
        self,
        source: Path,
        target: Path,
        *,
        records: list[dict[str, object]] | None = None,
        target_corruption: str | None = None,
    ) -> None:
        self.source = source.resolve()
        self.target = target.resolve()
        self.source_records = records if records is not None else _source_records()
        self.states: dict[str, dict[str, FakeCollection]] = {
            str(self.source): {
                "manuscript": FakeCollection(
                    "manuscript",
                    metadata={
                        "hnsw:space": "l2",
                        "embedding_model": "synthetic-model",
                        "cohort": "synthetic-test",
                    },
                    records=self.source_records,
                ),
                "unrelated": FakeCollection(
                    "unrelated",
                    metadata={"purpose": "source-only"},
                    records=[
                        _record("other", 8.0, "Synthetic other document.md")
                    ],
                ),
            }
        }
        self.target_corruption = target_corruption
        self.clients: list[FakeClient] = []

    def __call__(self, *, path):
        resolved = str(Path(path).resolve())
        if resolved == str(self.target) and resolved not in self.states:
            self.states[resolved] = {}
        client = FakeClient(
            self.states[resolved],
            target_corruption=(
                self.target_corruption if resolved == str(self.target) else None
            ),
        )
        self.clients.append(client)
        return client


def _source_records() -> list[dict[str, object]]:
    return [
        _record(
            "05_Introduction_001",
            1.0,
            "05_Introduction.md",
            stored_document="Synthetic stored document payload.",
        ),
        _record(
            "06_Chapter_001",
            2.0,
            "06_Chapter.md",
        ),
        _record(
            "02_Table_of_Contents_001",
            3.0,
            "02_Table of Contents.md",
        ),
    ]


def _directories(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"synthetic source marker")
    return source, target


def test_reuses_exact_values_and_keeps_only_currently_eligible_records(tmp_path):
    source, target = _directories(tmp_path)
    factory = FakeClientFactory(source, target)
    source_before = copy.deepcopy(factory.states[str(source.resolve())])

    report = reused_index.reuse_filtered_index(
        source,
        target,
        batch_size=1,
        chroma_client_factory=factory,
    )

    target_state = factory.states[str(target.resolve())]
    assert set(target_state) == {"manuscript"}
    assert set(target_state["manuscript"].records) == {
        "05_Introduction_001",
        "06_Chapter_001",
    }
    for record_id in target_state["manuscript"].records:
        assert (
            target_state["manuscript"].records[record_id]
            == source_before["manuscript"].records[record_id]
        )
    assert (
        target_state["manuscript"].metadata
        == source_before["manuscript"].metadata
    )
    assert (
        target_state["manuscript"].configuration
        == source_before["manuscript"].configuration
    )
    source_after = factory.states[str(source.resolve())]
    assert set(source_after) == set(source_before)
    for collection_name in source_after:
        assert (
            source_after[collection_name].records
            == source_before[collection_name].records
        )
        assert (
            source_after[collection_name].metadata
            == source_before[collection_name].metadata
        )
        assert (
            source_after[collection_name].configuration
            == source_before[collection_name].configuration
        )
    assert report == {
        "source_collection": "manuscript",
        "source_record_count": 3,
        "retained_record_count": 2,
        "excluded_record_count": 1,
        "excluded_document_counts": {"02_Table of Contents.md": 1},
        "embedding_dimension": 2,
        "hnsw_space": "l2",
        "filter": "filters.should_skip_document",
        "api_calls": 0,
    }
    assert all(client.closed for client in factory.clients)


@pytest.mark.parametrize("target_kind", ["existing", "source", "source_child"])
def test_rejects_nonfresh_or_overlapping_target_before_opening_chroma(
    tmp_path,
    target_kind,
):
    source, target = _directories(tmp_path)
    if target_kind == "existing":
        target.mkdir()
    elif target_kind == "source":
        target = source
    else:
        target = source / "child"
    factory = FakeClientFactory(source, target)

    with pytest.raises(reused_index.ReusedIndexError, match="overlap|already exist"):
        reused_index.reuse_filtered_index(
            source,
            target,
            chroma_client_factory=factory,
        )

    assert factory.clients == []


def test_rejects_target_that_overlaps_live_index_before_opening_chroma(
    tmp_path,
    monkeypatch,
):
    source, _ = _directories(tmp_path)
    live = tmp_path / "live" / "chroma_db"
    live.parent.mkdir()
    monkeypatch.setattr(reused_index, "LIVE_CHROMA_DIR", live.resolve())
    factory = FakeClientFactory(source, live)

    with pytest.raises(reused_index.ReusedIndexError, match="live Chroma"):
        reused_index.reuse_filtered_index(
            source,
            live,
            chroma_client_factory=factory,
        )

    assert factory.clients == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document", None, "document"),
        ("document", "", "document"),
        ("text", None, "string text"),
    ],
)
def test_invalid_filter_metadata_fails_before_creating_target(
    tmp_path,
    field,
    value,
    message,
):
    source, target = _directories(tmp_path)
    records = _source_records()
    records[0]["metadata"][field] = value
    factory = FakeClientFactory(source, target, records=records)

    with pytest.raises(reused_index.ReusedIndexError, match=message):
        reused_index.reuse_filtered_index(
            source,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()
    assert len(factory.clients) == 1
    assert factory.clients[0].closed


def test_no_eligible_records_fails_without_creating_target(tmp_path):
    source, target = _directories(tmp_path)
    records = [
        _record(
            "02_Table_of_Contents_001",
            1.0,
            "02_Table of Contents.md",
        )
    ]
    factory = FakeClientFactory(source, target, records=records)

    with pytest.raises(reused_index.ReusedIndexError, match="No retrieval-eligible"):
        reused_index.reuse_filtered_index(
            source,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()


@pytest.mark.parametrize("corruption", ["embedding", "metadata", "document"])
def test_postwrite_verification_detects_corruption_and_removes_target(
    tmp_path,
    corruption,
):
    source, target = _directories(tmp_path)
    factory = FakeClientFactory(
        source,
        target,
        target_corruption=corruption,
    )

    with pytest.raises(reused_index.ReusedIndexError, match="mismatch"):
        reused_index.reuse_filtered_index(
            source,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()
    assert all(client.closed for client in factory.clients)


def test_real_chroma_round_trip_reuses_synthetic_vectors_without_api_calls(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    source = tmp_path / "real-source"
    target = tmp_path / "real-target"
    collection_metadata = {
        "hnsw:space": "l2",
        "embedding_model": "synthetic-model",
        "cohort": "synthetic-test",
    }

    with chromadb.PersistentClient(path=str(source)) as client:
        collection = client.create_collection(
            "manuscript",
            metadata=collection_metadata,
            configuration={"hnsw": {"space": "l2"}},
            embedding_function=None,
        )
        collection.add(
            ids=["introduction", "contents"],
            embeddings=[[1.0, 1.25], [2.0, 2.25]],
            metadatas=[
                {
                    "document": "05_Introduction.md",
                    "text": "Synthetic introduction text.",
                    "chunk_id": "introduction",
                },
                {
                    "document": "02_Table of Contents.md",
                    "text": "Synthetic contents text.",
                    "chunk_id": "contents",
                },
            ],
            documents=["Synthetic stored payload.", "Synthetic excluded payload."],
        )

    report = reused_index.reuse_filtered_index(source, target)

    assert report["source_record_count"] == 2
    assert report["retained_record_count"] == 1
    assert report["excluded_record_count"] == 1
    assert report["api_calls"] == 0
    with chromadb.PersistentClient(path=str(source)) as client:
        assert client.get_collection("manuscript", embedding_function=None).count() == 2
    with chromadb.PersistentClient(path=str(target)) as client:
        assert [item.name for item in client.list_collections()] == ["manuscript"]
        collection = client.get_collection("manuscript", embedding_function=None)
        assert collection.count() == 1
        assert collection.metadata == collection_metadata
        result = collection.get(
            include=["embeddings", "documents", "metadatas"]
        )
        assert result["ids"] == ["introduction"]
        assert list(result["embeddings"][0]) == [1.0, 1.25]
        assert result["documents"] == ["Synthetic stored payload."]
        assert result["metadatas"] == [
            {
                "document": "05_Introduction.md",
                "text": "Synthetic introduction text.",
                "chunk_id": "introduction",
            }
        ]
