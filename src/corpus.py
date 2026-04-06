import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = BASE_DIR / "output" / "chunks.json"


def load_chunks() -> list[dict]:
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {chunk["chunk_id"]: chunk for chunk in chunks}


def get_neighbor_chunk_ids(chunk_id: str) -> list[str]:
    """
    Given a chunk_id like '04_Introduction_002', return neighboring chunk IDs.
    """
    match = re.match(r"^(.*)_(\d{3})$", chunk_id)
    if not match:
        return []

    prefix = match.group(1)
    number = int(match.group(2))

    neighbors = []
    if number > 1:
        neighbors.append(f"{prefix}_{number - 1:03}")
    neighbors.append(f"{prefix}_{number + 1:03}")

    return neighbors


ALL_CHUNKS = load_chunks()
CHUNK_LOOKUP = build_chunk_lookup(ALL_CHUNKS)