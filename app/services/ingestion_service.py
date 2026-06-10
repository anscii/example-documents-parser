from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Protocol

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.ingestion.file_io import compute_file_hash, save_staged_file
from app.logging_config import run_log_handler
from app.models import Document, IngestionError, IngestionRun, RawDocument
from app.processing import (
    duplicates_worker,
    normalize_worker,
    raw_load_worker,
    scoring_worker,
)
from app.schemas.ingestion import (
    IngestionErrorSummary,
    IngestionRunDetail,
    IngestionRunListItem,
)

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("completed", "failed")

# The pipeline stages pull from global queues (raw_documents.status='pending',
# documents.duplicate_group_id/quality_score IS NULL) without row-level locking
# (see docs/adr/0001-staged-db-as-queue-pipeline.md). Serialize pipeline runs
# within this process so concurrent `POST /ingestions` background tasks can't
# race on the same queue rows.
_pipeline_lock = threading.Lock()


class _BatchWorker(Protocol):
    __name__: str

    def process_batch(self, db: Session, batch_size: int) -> tuple[int, int]: ...


class DuplicateIngestionError(Exception):
    def __init__(self, existing_run_id: int) -> None:
        self.existing_run_id = existing_run_id
        super().__init__(f"file already ingested as run {existing_run_id}")


async def create_run(db: Session, file: UploadFile, force: bool) -> IngestionRun:
    content = await file.read()
    file_hash = compute_file_hash(content)

    if not force:
        existing = db.execute(
            select(IngestionRun)
            .where(
                IngestionRun.file_hash == file_hash,
                IngestionRun.status == "completed",
            )
            .order_by(IngestionRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateIngestionError(existing_run_id=existing.id)

    run = IngestionRun(
        source_file=file.filename or "upload.jsonl",
        file_hash=file_hash,
        staged_path="",
        status="queued",
    )
    db.add(run)
    db.flush()

    staged_path = save_staged_file(run.id, content)
    run.staged_path = str(staged_path)
    db.commit()
    return run


def run_pipeline(run_id: int) -> None:
    """Background-task entrypoint: drives a run through all pipeline stages."""
    with _pipeline_lock:
        _run_pipeline_locked(run_id)


def _run_pipeline_locked(run_id: int) -> None:
    db = SessionLocal()
    handler = run_log_handler(run_id)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        run = db.get(IngestionRun, run_id)
        if run is None:
            logger.error("run %s: not found", run_id)
            return

        logger.info(
            "run %s: pipeline started (source_file=%s, status=%s)",
            run_id,
            run.source_file,
            run.status,
        )

        if run.status == "queued":
            raw_load_worker.process_run(db, run)

        _drain(db, normalize_worker)
        _drain(db, duplicates_worker)
        _drain(db, scoring_worker)

        run.status = "completed"
        finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.finished_at = finished_at
        db.commit()
        _log_run_summary(db, run, finished_at)
        logger.info("run %s: pipeline completed", run_id)
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
        logger.exception("run %s: pipeline failed", run_id)
    finally:
        root_logger.removeHandler(handler)
        handler.close()
        db.close()


def _log_run_summary(db: Session, run: IngestionRun, finished_at: datetime) -> None:
    run_documents = select(Document).join(
        RawDocument, Document.raw_document_id == RawDocument.id
    ).where(RawDocument.ingestion_run_id == run.id)

    normalized_count = (
        db.scalar(select(func.count()).select_from(run_documents.subquery())) or 0
    )
    duplicates_count = (
        db.scalar(
            select(func.count()).select_from(
                run_documents.where(Document.is_canonical.is_(False)).subquery()
            )
        )
        or 0
    )
    scored_count = (
        db.scalar(
            select(func.count()).select_from(
                run_documents.where(Document.quality_score.isnot(None)).subquery()
            )
        )
        or 0
    )
    elapsed = (finished_at - run.started_at).total_seconds()

    logger.info(
        "run %s: FINAL SUMMARY - total_lines=%d raw_loaded=%d skipped=%d "
        "normalized=%d duplicates=%d scored=%d elapsed=%.2fs",
        run.id,
        run.total_lines or 0,
        run.raw_loaded_count or 0,
        run.skipped_count or 0,
        normalized_count,
        duplicates_count,
        scored_count,
        elapsed,
    )


def _drain(db: Session, worker: _BatchWorker) -> None:
    batch_size = settings.default_batch_size
    while True:
        processed, remaining = worker.process_batch(db, batch_size)
        logger.info("%s: processed=%d remaining=%d", worker.__name__, processed, remaining)
        if processed == 0 or remaining == 0:
            break


def resume_pending_runs() -> None:
    """Startup hook: re-launch any run that didn't reach a terminal state."""
    db = SessionLocal()
    try:
        run_ids = db.scalars(
            select(IngestionRun.id).where(IngestionRun.status.notin_(_TERMINAL_STATUSES))
        ).all()
    finally:
        db.close()

    for run_id in run_ids:
        logger.info("resuming ingestion run %s", run_id)
        run_pipeline(run_id)


def drain_all_queues() -> None:
    """Startup hook: mop up any global queue leftovers from a prior unclean shutdown."""
    db = SessionLocal()
    try:
        _drain(db, normalize_worker)
        _drain(db, duplicates_worker)
        _drain(db, scoring_worker)
    finally:
        db.close()


def build_run_detail(db: Session, run: IngestionRun) -> IngestionRunDetail:
    normalize_pending = (
        db.scalar(
            select(func.count())
            .select_from(RawDocument)
            .where(RawDocument.ingestion_run_id == run.id, RawDocument.status == "pending")
        )
        or 0
    )

    dedup_pending = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .join(RawDocument, Document.raw_document_id == RawDocument.id)
            .where(
                RawDocument.ingestion_run_id == run.id,
                Document.duplicate_group_id.is_(None),
                Document.is_canonical.is_(None),
            )
        )
        or 0
    )

    scoring_pending = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .join(RawDocument, Document.raw_document_id == RawDocument.id)
            .where(RawDocument.ingestion_run_id == run.id, Document.quality_score.is_(None))
        )
        or 0
    )

    error_count = (
        db.scalar(
            select(func.count()).select_from(IngestionError).where(IngestionError.run_id == run.id)
        )
        or 0
    )

    sample_errors = (
        db.execute(
            select(IngestionError)
            .where(IngestionError.run_id == run.id)
            .order_by(IngestionError.line_number)
            .limit(20)
        )
        .scalars()
        .all()
    )

    return IngestionRunDetail(
        **IngestionRunListItem.model_validate(run).model_dump(),
        normalize_pending=normalize_pending,
        dedup_pending=dedup_pending,
        scoring_pending=scoring_pending,
        error_count=error_count,
        sample_errors=[IngestionErrorSummary.model_validate(e) for e in sample_errors],
    )
