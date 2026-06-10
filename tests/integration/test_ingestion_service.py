import threading

from app.models import Document, IngestionRun, RawDocument
from app.services import ingestion_service


def test_resume_pending_runs_drains_processing_run(db_session, db_session_factory, monkeypatch):
    monkeypatch.setattr("app.services.ingestion_service.SessionLocal", db_session_factory)

    run = IngestionRun(source_file="f.jsonl", file_hash="h1", staged_path="/tmp/f.jsonl", status="processing")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    raw_doc = RawDocument(ingestion_run_id=run.id, line_number=1, raw_data={"title": "Resumed Doc"}, status="pending")
    db_session.add(raw_doc)
    db_session.commit()

    ingestion_service.resume_pending_runs()

    db_session.refresh(run)
    assert run.status == "completed"
    assert run.finished_at is not None

    db_session.refresh(raw_doc)
    assert raw_doc.status == "normalized"

    document = db_session.query(Document).filter_by(raw_document_id=raw_doc.id).one()
    assert document.is_canonical is True
    assert document.quality_score is not None


def test_resume_pending_runs_ignores_terminal_runs(db_session, db_session_factory, monkeypatch):
    monkeypatch.setattr("app.services.ingestion_service.SessionLocal", db_session_factory)

    completed = IngestionRun(source_file="a.jsonl", file_hash="h2", staged_path="/tmp/a.jsonl", status="completed")
    failed = IngestionRun(source_file="b.jsonl", file_hash="h3", staged_path="/tmp/b.jsonl", status="failed")
    db_session.add_all([completed, failed])
    db_session.commit()

    ingestion_service.resume_pending_runs()

    db_session.refresh(completed)
    db_session.refresh(failed)
    assert completed.status == "completed"
    assert failed.status == "failed"


def test_run_pipeline_serializes_concurrent_runs(db_session, db_session_factory, monkeypatch):
    monkeypatch.setattr("app.services.ingestion_service.SessionLocal", db_session_factory)

    run = IngestionRun(source_file="f.jsonl", file_hash="h5", staged_path="/tmp/f.jsonl", status="completed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    entered = threading.Event()
    release = threading.Event()
    original_drain = ingestion_service._drain

    def slow_drain(db, worker):
        entered.set()
        release.wait(timeout=5)
        return original_drain(db, worker)

    monkeypatch.setattr(ingestion_service, "_drain", slow_drain)

    thread = threading.Thread(target=ingestion_service.run_pipeline, args=(run.id,))
    thread.start()
    try:
        assert entered.wait(timeout=5)
        assert ingestion_service._pipeline_lock.locked()
    finally:
        release.set()
        thread.join(timeout=5)

    assert not ingestion_service._pipeline_lock.locked()
    db_session.refresh(run)
    assert run.status == "completed"


def test_drain_all_queues_processes_global_leftovers(db_session, db_session_factory, monkeypatch):
    monkeypatch.setattr("app.services.ingestion_service.SessionLocal", db_session_factory)

    run = IngestionRun(source_file="f.jsonl", file_hash="h4", staged_path="/tmp/f.jsonl", status="completed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    raw_doc = RawDocument(ingestion_run_id=run.id, line_number=1, raw_data={"title": "Leftover Doc"}, status="pending")
    db_session.add(raw_doc)
    db_session.commit()

    ingestion_service.drain_all_queues()

    db_session.refresh(raw_doc)
    assert raw_doc.status == "normalized"

    document = db_session.query(Document).filter_by(raw_document_id=raw_doc.id).one()
    assert document.is_canonical is True
    assert document.quality_score is not None
