from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

from app.models import Document, Organization, Tag
from app.schemas.common import Page
from app.schemas.document import DocumentDetail, DocumentSummary, DuplicateGroupInfo

MAX_PAGE_SIZE = 100

_SORT_COLUMNS = {
    "id": Document.id,
    "published_at": Document.published_at,
    "quality_score": Document.quality_score,
    "created_at": Document.created_at,
}


def _apply_filters(
    stmt: Select,
    *,
    published_after: date | None,
    published_before: date | None,
    tag: str | None,
    organization: str | None,
    status: str | None,
    document_type: str | None,
    language: str | None,
    region: str | None,
    q: str | None,
    canonical_only: bool,
    min_quality_score: float | None,
) -> Select:
    if published_after is not None:
        stmt = stmt.where(Document.published_at >= published_after)
    if published_before is not None:
        stmt = stmt.where(Document.published_at <= published_before)
    if tag is not None:
        stmt = stmt.join(Document.tags).where(func.lower(Tag.name) == tag.lower())
    if organization is not None:
        stmt = stmt.join(Document.organization).where(func.lower(Organization.name) == organization.lower())
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if document_type is not None:
        stmt = stmt.where(Document.document_type == document_type)
    if language is not None:
        stmt = stmt.where(Document.language == language)
    if region is not None:
        stmt = stmt.where(Document.region == region)
    if q is not None:
        like = f"%{q}%"
        stmt = stmt.where(or_(Document.title.ilike(like), Document.abstract.ilike(like), Document.body.ilike(like)))
    if canonical_only:
        stmt = stmt.where(Document.is_canonical.isnot(False))
    if min_quality_score is not None:
        stmt = stmt.where(Document.quality_score >= min_quality_score)
    return stmt


def list_documents(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
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
    sort_by: str = "id",
    sort_dir: str = "asc",
) -> Page[DocumentSummary]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)

    filter_kwargs = dict(
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
    )

    count_stmt = _apply_filters(select(func.count(func.distinct(Document.id))).select_from(Document), **filter_kwargs)
    total = db.scalar(count_stmt)

    stmt = _apply_filters(select(Document), **filter_kwargs)
    stmt = stmt.options(
        selectinload(Document.author), selectinload(Document.organization), selectinload(Document.tags)
    )

    sort_column = _SORT_COLUMNS[sort_by]
    order = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    if sort_by == "id":
        stmt = stmt.order_by(order)
    else:
        stmt = stmt.order_by(order, Document.id.asc())

    stmt = stmt.limit(page_size).offset((page - 1) * page_size)

    documents = db.execute(stmt).unique().scalars().all()

    return Page[DocumentSummary](
        items=[DocumentSummary.model_validate(document) for document in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_document(db: Session, document_id: int) -> DocumentDetail | None:
    document = db.execute(
        select(Document)
        .options(
            selectinload(Document.author), selectinload(Document.organization), selectinload(Document.tags)
        )
        .where(Document.id == document_id)
    ).scalar_one_or_none()

    if document is None:
        return None

    detail = DocumentDetail.model_validate(document)

    if document.duplicate_group_id is not None:
        group_size = db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.duplicate_group_id == document.duplicate_group_id)
        )
        detail.duplicate_group = DuplicateGroupInfo(
            group_id=document.duplicate_group_id,
            group_size=group_size,
            is_canonical=bool(document.is_canonical),
            confidence=document.duplicate_confidence,
        )

    return detail
