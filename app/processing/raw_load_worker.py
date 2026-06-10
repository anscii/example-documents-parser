from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion.file_io import iter_staged_lines
from app.ingestion.record_validator import ValidRecord, classify
from app.models import IngestionError, IngestionRun, RawDocument

logger = logging.getLogger(__name__)

RAW_LINE_TRUNCATE_LENGTH = 2000


def process_run(db: Session, run: IngestionRun) -> None:
    """Stage 0: stream the staged file, splitting lines into raw_documents / ingestion_errors."""
    total_lines = 0
    raw_loaded_count = 0
    skipped_count = 0

    for line_number, line in iter_staged_lines(Path(run.staged_path)):
        total_lines += 1
        result = classify(line)

        if isinstance(result, ValidRecord):
            db.add(
                RawDocument(
                    ingestion_run_id=run.id,
                    line_number=line_number,
                    raw_data=result.data,
                    status="pending",
                )
            )
            raw_loaded_count += 1
        else:
            db.add(
                IngestionError(
                    run_id=run.id,
                    line_number=line_number,
                    raw_line=line[:RAW_LINE_TRUNCATE_LENGTH],
                    error_category=result.category,
                    error_detail=result.detail,
                )
            )
            skipped_count += 1
            logger.error(
                "run %s: line %d skipped (%s): %s",
                run.id,
                line_number,
                result.category,
                result.detail,
            )

    run.total_lines = total_lines
    run.raw_loaded_count = raw_loaded_count
    run.skipped_count = skipped_count
    run.status = "processing"
    db.commit()

    logger.info(
        "run %s: stage 0 complete - total_lines=%d raw_loaded=%d skipped=%d",
        run.id,
        total_lines,
        raw_loaded_count,
        skipped_count,
    )
