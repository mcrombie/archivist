import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_usage_database():
    directory = Path("runtime") / "test-ledgers"
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / f"pytest-{os.getpid()}.sqlite3"
    related_paths = [database, Path(f"{database}-wal"), Path(f"{database}-shm")]
    for path in related_paths:
        path.unlink(missing_ok=True)

    previous = os.environ.get("ARCHIVIST_USAGE_DB")
    os.environ["ARCHIVIST_USAGE_DB"] = str(database)
    yield

    if previous is None:
        os.environ.pop("ARCHIVIST_USAGE_DB", None)
    else:
        os.environ["ARCHIVIST_USAGE_DB"] = previous
    for path in related_paths:
        path.unlink(missing_ok=True)
    try:
        directory.rmdir()
        directory.parent.rmdir()
    except OSError:
        pass
