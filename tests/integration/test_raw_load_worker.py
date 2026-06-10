from pathlib import Path

from app.models import IngestionError, IngestionRun, RawDocument
from app.processing import raw_load_worker

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_input" / "mini.jsonl"


def _make_run(db_session, staged_path: Path) -> IngestionRun:
    run = IngestionRun(
        source_file="mini.jsonl",
        file_hash="testhash",
        staged_path=str(staged_path),
        status="queued",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_process_run_classifies_lines(db_session):
    run = _make_run(db_session, FIXTURE_PATH)

    raw_load_worker.process_run(db_session, run)

    assert run.total_lines == 5
    assert run.raw_loaded_count == 1
    assert run.skipped_count == 4
    assert run.status == "processing"

    raw_docs = (
        db_session.query(RawDocument)
        .filter_by(ingestion_run_id=run.id)
        .order_by(RawDocument.line_number)
        .all()
    )
    assert [rd.line_number for rd in raw_docs] == [1]
    assert all(rd.status == "pending" for rd in raw_docs)
    assert raw_docs[0].raw_data["external_id"] == "doc-001"

    errors = (
        db_session.query(IngestionError)
        .filter_by(run_id=run.id)
        .order_by(IngestionError.line_number)
        .all()
    )
    assert [e.line_number for e in errors] == [2, 3, 4, 5]
    assert [e.error_category for e in errors] == [
        "empty",
        "not_object",
        "broken_stub",
        "invalid_json",
    ]
