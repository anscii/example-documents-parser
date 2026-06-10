import hashlib

from app.config import settings
from app.ingestion.file_io import (
    compute_file_hash,
    iter_staged_lines,
    save_staged_file,
    staged_file_path,
)


def test_compute_file_hash():
    content = b"hello world"
    assert compute_file_hash(content) == hashlib.sha256(content).hexdigest()


def test_staged_file_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    assert staged_file_path(42) == tmp_path / "42.jsonl"


def test_save_staged_file(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", upload_dir)

    path = save_staged_file(7, b'{"a": 1}\n{"b": 2}\n')

    assert path == upload_dir / "7.jsonl"
    assert path.read_bytes() == b'{"a": 1}\n{"b": 2}\n'


def test_iter_staged_lines(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")

    assert list(iter_staged_lines(path)) == [(1, '{"a": 1}'), (2, '{"b": 2}')]
