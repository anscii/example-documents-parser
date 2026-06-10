from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

from app.config import settings


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def staged_file_path(run_id: int) -> Path:
    return settings.upload_dir / f"{run_id}.jsonl"


def save_staged_file(run_id: int, content: bytes) -> Path:
    path = staged_file_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def iter_staged_lines(path: Path) -> Iterator[tuple[int, str]]:
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            yield line_number, line.rstrip("\n")
