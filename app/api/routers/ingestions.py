from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import IngestionRun
from app.schemas.common import OffsetPage
from app.schemas.ingestion import (
    IngestionRunDetail,
    IngestionRunListItem,
    IngestionRunSummary,
)
from app.services import ingestion_service

router = APIRouter(prefix="/ingestions", tags=["ingestions"])


@router.post("", response_model=IngestionRunSummary, status_code=201)
async def create_ingestion(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force: bool = False,
    db: Session = Depends(get_db),
) -> IngestionRunSummary:
    try:
        run = await ingestion_service.create_run(db, file, force)
    except ingestion_service.DuplicateIngestionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "file already ingested",
                "existing_run_id": exc.existing_run_id,
            },
        ) from exc

    background_tasks.add_task(ingestion_service.run_pipeline, run.id)
    return IngestionRunSummary.model_validate(run)


@router.get("", response_model=OffsetPage[IngestionRunListItem])
def list_ingestions(
    limit: int = 20, offset: int = 0, db: Session = Depends(get_db)
) -> OffsetPage[IngestionRunListItem]:
    total = db.scalar(select(func.count()).select_from(IngestionRun))
    runs = (
        db.execute(
            select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return OffsetPage[IngestionRunListItem](
        items=[IngestionRunListItem.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=IngestionRunDetail)
def get_ingestion(run_id: int, db: Session = Depends(get_db)) -> IngestionRunDetail:
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    return ingestion_service.build_run_detail(db, run)
