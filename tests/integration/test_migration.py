import os
import sqlite3
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "alembic_version",
    "authors",
    "organizations",
    "tags",
    "document_tags",
    "ingestion_runs",
    "ingestion_errors",
    "raw_documents",
    "documents",
}


def _run_alembic(*args: str, db_path: Path) -> None:
    env = os.environ.copy()
    env["APP_DATABASE_URL"] = f"sqlite:///{db_path}"
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_upgrade_creates_schema_and_seeds_unknown_sentinels(tmp_path):
    db_path = tmp_path / "test.db"

    _run_alembic("upgrade", "head", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        assert EXPECTED_TABLES <= _table_names(conn)

        for table in ("authors", "organizations"):
            rows = conn.execute(f"SELECT name, normalized_name FROM {table}").fetchall()
            assert rows == [("Unknown", "__unknown__")]
    finally:
        conn.close()


def test_downgrade_drops_all_tables(tmp_path):
    db_path = tmp_path / "test.db"

    _run_alembic("upgrade", "head", db_path=db_path)
    _run_alembic("downgrade", "base", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        assert _table_names(conn) - {"alembic_version"} == set()
    finally:
        conn.close()
