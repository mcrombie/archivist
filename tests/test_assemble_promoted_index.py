from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "assemble_promoted_index.py"
SPEC = importlib.util.spec_from_file_location("assemble_promoted_index", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
promotion_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion_index)


def _record(
    record_id: str,
    number: float,
    *,
    document: str | None = None,
) -> dict[str, object]:
    return {
        "id": record_id,
        "embedding": [number, number + 0.25],
        "metadata": {
            "chunk_id": record_id,
            "text": f"Synthetic text for {record_id}.",
        },
        "document": document,
    }


class FakeCollection:
    def __init__(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
        records: list[dict[str, object]] | None = None,
        corrupt_add: bool = False,
    ) -> None:
        self.name = name
        self.metadata = copy.deepcopy(metadata)
        self.records = {
            str(record["id"]): copy.deepcopy(record) for record in records or []
        }
        self.corrupt_add = corrupt_add

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

    def add(self, *, ids, embeddings, metadatas=None, documents=None) -> None:
        for index, record_id in enumerate(ids):
            embedding = list(embeddings[index])
            if self.corrupt_add:
                embedding[0] += 1.0
            self.records[record_id] = {
                "id": record_id,
                "embedding": embedding,
                "metadata": copy.deepcopy(metadatas[index]) if metadatas else None,
                "document": documents[index] if documents else None,
            }


class FakeClient:
    def __init__(
        self,
        collections: dict[str, FakeCollection],
        *,
        corrupt_new_collection: bool = False,
        delete_side_effect: bool = False,
    ) -> None:
        self.collections = collections
        self.corrupt_new_collection = corrupt_new_collection
        self.delete_side_effect = delete_side_effect
        self.closed = False

    def list_collections(self):
        return list(self.collections.values())

    def get_collection(self, *, name, embedding_function):
        assert embedding_function is None
        return self.collections[name]

    def delete_collection(self, *, name):
        del self.collections[name]
        if self.delete_side_effect:
            self.collections.pop("project_alpha", None)

    def create_collection(self, *, name, metadata, embedding_function):
        assert embedding_function is None
        collection = FakeCollection(
            name,
            metadata=metadata,
            corrupt_add=self.corrupt_new_collection,
        )
        self.collections[name] = collection
        return collection

    def close(self):
        self.closed = True


class FakeClientFactory:
    def __init__(
        self,
        source: Path,
        staged: Path,
        target: Path,
        *,
        corrupt_new_collection: bool = False,
        delete_side_effect: bool = False,
    ) -> None:
        self.source = source.resolve()
        self.staged = staged.resolve()
        self.target = target.resolve()
        self.states = {
            str(self.source): _source_collections(),
            str(self.staged): _staged_collections(),
        }
        self.corrupt_new_collection = corrupt_new_collection
        self.delete_side_effect = delete_side_effect
        self.clients: list[FakeClient] = []

    def __call__(self, *, path):
        resolved = str(Path(path).resolve())
        if resolved == str(self.target) and resolved not in self.states:
            self.states[resolved] = copy.deepcopy(self.states[str(self.source)])
        client = FakeClient(
            self.states[resolved],
            corrupt_new_collection=(
                self.corrupt_new_collection and resolved == str(self.target)
            ),
            delete_side_effect=self.delete_side_effect and resolved == str(self.target),
        )
        self.clients.append(client)
        return client


def _source_collections() -> dict[str, FakeCollection]:
    return {
        "manuscript": FakeCollection(
            "manuscript",
            metadata={"hnsw:space": "l2", "old": True},
            records=[_record("old", 9.0)],
        ),
        "project_alpha": FakeCollection(
            "project_alpha",
            metadata={"purpose": "must survive"},
            records=[_record("custom-a", 4.0), _record("custom-b", 5.0)],
        ),
    }


def _staged_collections() -> dict[str, FakeCollection]:
    return {
        "manuscript": FakeCollection(
            "manuscript",
            metadata={
                "hnsw:space": "l2",
                "embedding_model": "text-embedding-3-small",
                "chunks_sha256": "a" * 64,
                "cohort": "synthetic-test",
            },
            records=[
                _record("new-a", 1.0, document="Synthetic stored document."),
                _record("new-b", 2.0),
            ],
        )
    }


def _directories(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    staged = tmp_path / "staged"
    target = tmp_path / "target"
    source.mkdir()
    staged.mkdir()
    (source / "chroma.sqlite3").write_bytes(b"source marker")
    (source / "custom-segment.bin").write_bytes(b"custom collection data")
    (staged / "chroma.sqlite3").write_bytes(b"staged marker")
    return source, staged, target


def test_assembles_full_copy_and_replaces_only_manuscript(tmp_path):
    source, staged, target = _directories(tmp_path)
    factory = FakeClientFactory(source, staged, target)
    source_before = copy.deepcopy(factory.states[str(source.resolve())])
    staged_before = copy.deepcopy(factory.states[str(staged.resolve())])

    report = promotion_index.assemble_promoted_index(
        source,
        staged,
        target,
        batch_size=1,
        chroma_client_factory=factory,
    )

    assert (target / "chroma.sqlite3").read_bytes() == b"source marker"
    assert (target / "custom-segment.bin").read_bytes() == b"custom collection data"
    assert report["source_collection_counts"] == {
        "manuscript": 1,
        "project_alpha": 2,
    }
    assert report["preserved_collection_counts"] == {"project_alpha": 2}
    assert report["promoted_manuscript_count"] == 2

    source_state = factory.states[str(source.resolve())]
    target_state = factory.states[str(target.resolve())]
    assert source_state["manuscript"].records == source_before["manuscript"].records
    assert source_state["project_alpha"].records == source_before["project_alpha"].records
    assert target_state["project_alpha"].records == source_before["project_alpha"].records
    assert target_state["project_alpha"].metadata == source_before["project_alpha"].metadata
    assert target_state["manuscript"].records == staged_before["manuscript"].records
    assert target_state["manuscript"].metadata == staged_before["manuscript"].metadata
    assert all(client.closed for client in factory.clients)


def test_refuses_even_an_empty_existing_target_before_opening_clients(tmp_path):
    source, staged, target = _directories(tmp_path)
    target.mkdir()
    factory = FakeClientFactory(source, staged, target)

    with pytest.raises(promotion_index.PromotionIndexError, match="must not already exist"):
        promotion_index.assemble_promoted_index(
            source,
            staged,
            target,
            chroma_client_factory=factory,
        )

    assert target.is_dir()
    assert not any(target.iterdir())
    assert factory.clients == []


@pytest.mark.parametrize("target_kind", ["source", "source_child", "staged_child"])
def test_refuses_targets_that_overlap_an_input(tmp_path, target_kind):
    source, staged, target = _directories(tmp_path)
    if target_kind == "source":
        target = source
    elif target_kind == "source_child":
        target = source / "promotion"
    else:
        target = staged / "promotion"
    factory = FakeClientFactory(source, staged, target)

    with pytest.raises(promotion_index.PromotionIndexError, match="overlap|already exist"):
        promotion_index.assemble_promoted_index(
            source,
            staged,
            target,
            chroma_client_factory=factory,
        )

    assert factory.clients == []


def test_refuses_live_target_and_its_parent_or_child(tmp_path, monkeypatch):
    source, staged, target = _directories(tmp_path)
    live = tmp_path / "live" / "chroma_db"
    live.parent.mkdir()
    monkeypatch.setattr(promotion_index, "LIVE_CHROMA_DIR", live.resolve())

    for unsafe_target in (live, live / "child", live.parent):
        factory = FakeClientFactory(source, staged, unsafe_target)
        with pytest.raises(promotion_index.PromotionIndexError, match="live Chroma"):
            promotion_index.assemble_promoted_index(
                source,
                staged,
                unsafe_target,
                chroma_client_factory=factory,
            )
        assert factory.clients == []


def test_invalid_staged_provenance_cleans_the_copied_target(tmp_path):
    source, staged, target = _directories(tmp_path)
    factory = FakeClientFactory(source, staged, target)
    factory.states[str(staged.resolve())]["manuscript"].metadata = {
        "hnsw:space": "cosine",
        "embedding_model": "text-embedding-3-small",
        "chunks_sha256": "b" * 64,
    }

    with pytest.raises(promotion_index.PromotionIndexError, match="hnsw:space='l2'"):
        promotion_index.assemble_promoted_index(
            source,
            staged,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()
    assert all(client.closed for client in factory.clients)


def test_verification_detects_embedding_corruption_and_cleans_target(tmp_path):
    source, staged, target = _directories(tmp_path)
    factory = FakeClientFactory(
        source,
        staged,
        target,
        corrupt_new_collection=True,
    )

    with pytest.raises(promotion_index.PromotionIndexError, match="embedding mismatch"):
        promotion_index.assemble_promoted_index(
            source,
            staged,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()


def test_verification_detects_non_manuscript_change_and_cleans_target(tmp_path):
    source, staged, target = _directories(tmp_path)
    factory = FakeClientFactory(
        source,
        staged,
        target,
        delete_side_effect=True,
    )

    with pytest.raises(
        promotion_index.PromotionIndexError,
        match="non-manuscript collection",
    ):
        promotion_index.assemble_promoted_index(
            source,
            staged,
            target,
            chroma_client_factory=factory,
        )

    assert not target.exists()


def test_real_chroma_round_trip_preserves_custom_collection(tmp_path):
    chromadb = pytest.importorskip("chromadb")
    source = tmp_path / "real-source"
    staged = tmp_path / "real-staged"
    target = tmp_path / "real-target"

    with chromadb.PersistentClient(path=str(source)) as client:
        old_manuscript = client.create_collection(
            "manuscript",
            metadata={"hnsw:space": "l2", "cohort": "old"},
            embedding_function=None,
        )
        old_manuscript.add(
            ids=["old-id"],
            embeddings=[[9.0, 9.0]],
            metadatas=[{"text": "Synthetic old corpus text."}],
        )
        custom = client.create_collection(
            "project_alpha",
            metadata={"purpose": "preserve"},
            embedding_function=None,
        )
        custom.add(
            ids=["custom-id"],
            embeddings=[[4.0, 5.0]],
            metadatas=[{"text": "Synthetic custom project text."}],
            documents=["Synthetic custom stored document."],
        )

    staged_metadata = {
        "hnsw:space": "l2",
        "embedding_model": "text-embedding-3-small",
        "chunks_sha256": "c" * 64,
    }
    with chromadb.PersistentClient(path=str(staged)) as client:
        manuscript = client.create_collection(
            "manuscript",
            metadata=staged_metadata,
            embedding_function=None,
        )
        manuscript.add(
            ids=["new-a", "new-b"],
            embeddings=[[1.0, 1.25], [2.0, 2.25]],
            metadatas=[
                {"text": "Synthetic staged text A."},
                {"text": "Synthetic staged text B."},
            ],
        )

    report = promotion_index.assemble_promoted_index(source, staged, target)

    assert report["preserved_collection_counts"] == {"project_alpha": 1}
    assert report["promoted_manuscript_count"] == 2
    with chromadb.PersistentClient(path=str(target)) as client:
        assert {collection.name for collection in client.list_collections()} == {
            "manuscript",
            "project_alpha",
        }
        custom = client.get_collection("project_alpha", embedding_function=None)
        assert custom.count() == 1
        assert custom.get(include=["documents"])["documents"] == [
            "Synthetic custom stored document."
        ]
        manuscript = client.get_collection("manuscript", embedding_function=None)
        assert manuscript.metadata == staged_metadata
        records = manuscript.get(include=["embeddings", "documents", "metadatas"])
        assert set(records["ids"]) == {"new-a", "new-b"}
        assert len(records["embeddings"]) == 2
