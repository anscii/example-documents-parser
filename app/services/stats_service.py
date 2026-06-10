from __future__ import annotations

import statistics

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, Tag, document_tags
from app.schemas.stats import DuplicateGroupSummary, DuplicateStats, QualityScoreDistribution, StatsResponse

HISTOGRAM_BUCKET_WIDTH = 10
HISTOGRAM_BUCKET_COUNT = 10
TOP_GROUPS_LIMIT = 10
UNKNOWN_REGION_LABEL = "unknown"


def get_stats(db: Session) -> StatsResponse:
    return StatsResponse(
        total_documents=db.scalar(select(func.count()).select_from(Document)),
        by_status=_count_by(db, Document.status),
        by_document_type=_count_by(db, Document.document_type),
        by_region=_count_by_region(db),
        by_language=_count_by(db, Document.language),
        top_tags=_top_tags(db),
        duplicate_stats=_duplicate_stats(db),
        quality_score_distribution=_quality_score_distribution(db),
    )


def _count_by(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column).order_by(func.count().desc())).all()
    return dict(rows)


def _count_by_region(db: Session) -> dict[str, int]:
    region_label = func.coalesce(Document.region, UNKNOWN_REGION_LABEL)
    rows = db.execute(
        select(region_label, func.count()).group_by(region_label).order_by(func.count().desc())
    ).all()
    return dict(rows)


def _top_tags(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Tag.name, func.count(document_tags.c.document_id))
        .join(document_tags, Tag.id == document_tags.c.tag_id)
        .group_by(Tag.name)
        .order_by(func.count(document_tags.c.document_id).desc())
    ).all()
    return dict(rows)


def _duplicate_stats(db: Session) -> DuplicateStats:
    group_sizes = dict(
        db.execute(
            select(Document.duplicate_group_id, func.count())
            .where(Document.duplicate_group_id.is_not(None))
            .group_by(Document.duplicate_group_id)
        ).all()
    )

    total_groups = len(group_sizes)
    total_duplicates = sum(group_sizes.values())
    avg_group_size = round(total_duplicates / total_groups, 2) if total_groups else 0.0

    top_group_ids = sorted(group_sizes, key=lambda group_id: group_sizes[group_id], reverse=True)[:TOP_GROUPS_LIMIT]

    top_groups: list[DuplicateGroupSummary] = []
    if top_group_ids:
        canonical_docs = (
            db.execute(
                select(Document).where(
                    Document.duplicate_group_id.in_(top_group_ids), Document.is_canonical.is_(True)
                )
            )
            .scalars()
            .all()
        )
        canonical_by_group = {doc.duplicate_group_id: doc for doc in canonical_docs}
        for group_id in top_group_ids:
            canonical = canonical_by_group[group_id]
            top_groups.append(
                DuplicateGroupSummary(
                    group_id=group_id,
                    size=group_sizes[group_id],
                    canonical_document_id=canonical.id,
                    normalized_title=canonical.normalized_title or "",
                )
            )

    return DuplicateStats(
        total_groups=total_groups,
        total_duplicates=total_duplicates,
        avg_group_size=avg_group_size,
        top_groups=top_groups,
    )


def _quality_score_distribution(db: Session) -> QualityScoreDistribution:
    scores = list(
        db.execute(
            select(Document.quality_score).where(Document.quality_score.is_not(None)).order_by(Document.quality_score)
        )
        .scalars()
        .all()
    )

    histogram = [0] * HISTOGRAM_BUCKET_COUNT
    for score in scores:
        bucket = min(int(score // HISTOGRAM_BUCKET_WIDTH), HISTOGRAM_BUCKET_COUNT - 1)
        histogram[bucket] += 1

    if not scores:
        return QualityScoreDistribution(min=None, max=None, mean=None, median=None, p25=None, p75=None, histogram=histogram)

    if len(scores) == 1:
        value = scores[0]
        return QualityScoreDistribution(min=value, max=value, mean=value, median=value, p25=value, p75=value, histogram=histogram)

    p25, median, p75 = statistics.quantiles(scores, n=4, method="inclusive")
    return QualityScoreDistribution(
        min=scores[0],
        max=scores[-1],
        mean=round(statistics.fmean(scores), 2),
        median=round(median, 2),
        p25=round(p25, 2),
        p75=round(p75, 2),
        histogram=histogram,
    )
