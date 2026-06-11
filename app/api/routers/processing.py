from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.processing import duplicates_worker, normalize_worker, scoring_worker
from app.schemas.processing import ProcessingResult
from app.services import ingestion_service

router = APIRouter(prefix="/processing", tags=["processing"])


@router.post("/normalize", response_model=ProcessingResult)
def process_normalize(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = ingestion_service.run_processing_batch(normalize_worker, db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)


@router.post("/duplicates", response_model=ProcessingResult)
def process_duplicates(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = ingestion_service.run_processing_batch(duplicates_worker, db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)


@router.post("/scoring", response_model=ProcessingResult)
def process_scoring(
    batch_size: int = settings.default_batch_size, db: Session = Depends(get_db)
) -> ProcessingResult:
    processed, remaining = ingestion_service.run_processing_batch(scoring_worker, db, batch_size)
    return ProcessingResult(processed=processed, remaining=remaining)
