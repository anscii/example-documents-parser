from __future__ import annotations

import bisect
import logging
import math
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Document

logger = logging.getLogger(__name__)

RECENCY_HALF_LIFE_YEARS = 5.0
DAYS_PER_YEAR = 365.25

_WEIGHT_CITATION = 25
_WEIGHT_RELEVANCE = 20
_WEIGHT_RECENCY = 20
_WEIGHT_PEER_REVIEWED = 15
_WEIGHT_OPEN_ACCESS = 10
_WEIGHT_WORD_COUNT = 5
_WEIGHT_PAGE_COUNT = 5

_MANY_CITATION_SENTINEL = "many"
_HIGH_RELEVANCE_SENTINEL = "high"
_HIGH_RELEVANCE_VALUE = 0.9


def process_batch(db: Session, batch_size: int) -> tuple[int, int]:
    """Stage 3: compute the composite quality_score for a batch of documents."""
    cc_sorted, p90_value = _citation_count_distribution(db)

    pending = (
        db.execute(
            select(Document)
            .options(selectinload(Document.raw_document))
            .where(Document.quality_score.is_(None))
            .order_by(Document.id)
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    if not pending:
        return 0, _count_pending(db)

    today = date.today()
    for document in pending:
        document.quality_score = _quality_score(
            document, document.raw_document.raw_data, cc_sorted, p90_value, today
        )

    db.commit()

    remaining = _count_pending(db)
    logger.info("stage 3: scored %d documents (remaining=%d)", len(pending), remaining)
    return len(pending), remaining


def _count_pending(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(Document).where(Document.quality_score.is_(None))
    )


def _citation_count_distribution(db: Session) -> tuple[list[int], int | None]:
    cc_sorted = list(
        db.execute(
            select(Document.citation_count)
            .where(Document.citation_count.is_not(None))
            .order_by(Document.citation_count)
        )
        .scalars()
        .all()
    )
    if not cc_sorted:
        return cc_sorted, None
    return cc_sorted, cc_sorted[int(0.9 * (len(cc_sorted) - 1))]


def _citation_percentile(value: int | None, cc_sorted: list[int]) -> float:
    if value is None or not cc_sorted:
        return 0.0
    return bisect.bisect_right(cc_sorted, value) / len(cc_sorted)


def _quality_score(
    document: Document,
    raw_data: dict[str, Any],
    cc_sorted: list[int],
    p90_value: int | None,
    today: date,
) -> float:
    citation_value = document.citation_count
    if citation_value is None and p90_value is not None:
        raw_citation = raw_data.get("citation_count")
        if (
            isinstance(raw_citation, str)
            and raw_citation.strip().lower() == _MANY_CITATION_SENTINEL
        ):
            citation_value = p90_value

    relevance_value = document.relevance_score
    if relevance_value is None:
        raw_relevance = raw_data.get("relevance_score")
        if (
            isinstance(raw_relevance, str)
            and raw_relevance.strip().lower() == _HIGH_RELEVANCE_SENTINEL
        ):
            relevance_value = _HIGH_RELEVANCE_VALUE
        else:
            relevance_value = 0.0

    score = _WEIGHT_CITATION * _citation_percentile(citation_value, cc_sorted)
    score += _WEIGHT_RELEVANCE * relevance_value

    if document.published_at is not None:
        age_years = (today - document.published_at).days / DAYS_PER_YEAR
        score += _WEIGHT_RECENCY * math.exp(-max(0.0, age_years) / RECENCY_HALF_LIFE_YEARS)

    if document.peer_reviewed is True:
        score += _WEIGHT_PEER_REVIEWED
    if document.open_access is True:
        score += _WEIGHT_OPEN_ACCESS
    if document.word_count:
        score += _WEIGHT_WORD_COUNT
    if document.page_count:
        score += _WEIGHT_PAGE_COUNT

    return round(min(100.0, max(0.0, score)), 2)
