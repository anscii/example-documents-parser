from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.processing import duplicates_worker, normalize_worker, scoring_worker
from app.schemas.processing import ProcessingResult

router = APIRouter(prefix="/processing", tags=["processing"])


@router.post("/normalize", response_model=ProcessingResult)
def process_normalize(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = normalize_worker.process_batch(db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)


@router.post("/duplicates", response_model=ProcessingResult)
def process_duplicates(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = duplicates_worker.process_batch(db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)


@router.post("/scoring", response_model=ProcessingResult)
def process_scoring(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = scoring_worker.process_batch(db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)
