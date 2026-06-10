from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.document import DocumentDetail, DocumentSummary
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=Page[DocumentSummary])
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=document_service.MAX_PAGE_SIZE),
    published_after: date | None = None,
    published_before: date | None = None,
    tag: str | None = None,
    organization: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    language: str | None = None,
    region: str | None = None,
    q: str | None = None,
    canonical_only: bool = False,
    min_quality_score: float | None = None,
    sort_by: str = Query("id", pattern="^(id|published_at|quality_score|created_at)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> Page[DocumentSummary]:
    return document_service.list_documents(
        db,
        page=page,
        page_size=page_size,
        published_after=published_after,
        published_before=published_before,
        tag=tag,
        organization=organization,
        status=status,
        document_type=document_type,
        language=language,
        region=region,
        q=q,
        canonical_only=canonical_only,
        min_quality_score=min_quality_score,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentDetail:
    document = document_service.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document
