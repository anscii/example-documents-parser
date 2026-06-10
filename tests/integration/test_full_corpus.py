from pathlib import Path

import pytest

from app.models import Document, IngestionRun

INPUT_DIR = Path(__file__).resolve().parents[2] / "input_docs"
INPUT_FILES = sorted(INPUT_DIR.glob("documents_*.jsonl"))


@pytest.mark.slow
@pytest.mark.skipif(not INPUT_FILES, reason="input_docs/documents_*.jsonl not present")
def test_full_corpus_ingestion_matches_data_profile(client, db_session):
    """End-to-end run over the full ~11,000-line corpus (see docs/stats_examples.md)."""
    for path in INPUT_FILES:
        with open(path, "rb") as f:
            response = client.post(
                "/ingestions",
                files={"file": (path.name, f, "application/x-ndjson")},
            )
        assert response.status_code == 201
        run = db_session.get(IngestionRun, response.json()["id"])
        assert run.status == "completed"

    runs = db_session.query(IngestionRun).all()
    assert len(runs) == len(INPUT_FILES)
    assert sum(r.total_lines for r in runs) == 11000
    assert sum(r.raw_loaded_count for r in runs) == 10555
    assert sum(r.skipped_count for r in runs) == 445

    documents = db_session.query(Document).all()
    assert len(documents) == 10555
    for document in documents:
        assert document.is_canonical is not None
        assert document.quality_score is not None

    distinct_titles = {d.normalized_title for d in documents if d.normalized_title}
    assert len(distinct_titles) == 41

    duplicate_group_ids = {d.duplicate_group_id for d in documents if d.duplicate_group_id is not None}
    assert len(duplicate_group_ids) == 48

    total_duplicates = sum(1 for d in documents if d.duplicate_group_id is not None)
    assert total_duplicates == 8066

    stats = client.get("/stats").json()
    assert stats["total_documents"] == 10555
