from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Author, Document, Organization
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME

logger = logging.getLogger(__name__)

# Fields whose presence (non-null/non-default) counts toward a document's
# "completeness" when picking the canonical member of a duplicate group.
_COMPLETENESS_FIELDS = ("abstract", "body", "doi", "url", "region", "citation_count", "word_count", "page_count")


class _UnionFind:
    def __init__(self, ids: list[int]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def process_batch(db: Session, batch_size: int) -> tuple[int, int]:
    """Stage 2: group documents into duplicate clusters by title + (author OR source)."""
    pending = (
        db.execute(
            select(Document)
            .where(Document.duplicate_group_id.is_(None), Document.is_canonical.is_(None))
            .order_by(Document.id)
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    if not pending:
        return 0, _count_pending(db)

    unknown_author_id = _unknown_id(db, Author)
    unknown_org_id = _unknown_id(db, Organization)

    titles: set[str] = set()
    for doc in pending:
        if doc.normalized_title:
            titles.add(doc.normalized_title)
        else:
            _mark_singleton(doc)

    for normalized_title in titles:
        _process_title_cohort(db, normalized_title, unknown_author_id, unknown_org_id)

    db.commit()

    remaining = _count_pending(db)
    logger.info("stage 2: processed %d documents (remaining=%d)", len(pending), remaining)
    return len(pending), remaining


def _count_pending(db: Session) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.duplicate_group_id.is_(None), Document.is_canonical.is_(None))
    )


def _unknown_id(db: Session, model: type[Author] | type[Organization]) -> int:
    return db.scalar(select(model.id).where(model.normalized_name == UNKNOWN_NORMALIZED_NAME))


def _mark_singleton(doc: Document) -> None:
    doc.is_canonical = True
    doc.duplicate_group_id = None
    doc.duplicate_confidence = None


def _process_title_cohort(db: Session, normalized_title: str, unknown_author_id: int, unknown_org_id: int) -> None:
    cohort = db.execute(select(Document).where(Document.normalized_title == normalized_title)).scalars().all()

    if len(cohort) == 1:
        _mark_singleton(cohort[0])
        return

    uf = _UnionFind([doc.id for doc in cohort])
    for i, a in enumerate(cohort):
        for b in cohort[i + 1 :]:
            if _authors_match(a, b, unknown_author_id) or _sources_match(a, b):
                uf.union(a.id, b.id)

    components: dict[int, list[Document]] = defaultdict(list)
    for doc in cohort:
        components[uf.find(doc.id)].append(doc)

    for members in components.values():
        if len(members) == 1:
            _mark_singleton(members[0])
            continue

        group_id = min(doc.id for doc in members)
        canonical = _pick_canonical(members, unknown_author_id, unknown_org_id)
        for doc in members:
            doc.duplicate_group_id = group_id
            doc.is_canonical = doc.id == canonical.id
            doc.duplicate_confidence = _confidence(doc, members, unknown_author_id, unknown_org_id)


def _authors_match(a: Document, b: Document, unknown_author_id: int) -> bool:
    return a.author_id == b.author_id and a.author_id != unknown_author_id


def _organizations_match(a: Document, b: Document, unknown_org_id: int) -> bool:
    return a.organization_id == b.organization_id and a.organization_id != unknown_org_id


def _sources_match(a: Document, b: Document) -> bool:
    return a.source_name is not None and a.source_name == b.source_name


def _languages_match(a: Document, b: Document) -> bool:
    return a.language == b.language and a.language != "unknown"


def _regions_match(a: Document, b: Document) -> bool:
    return a.region is not None and a.region == b.region


def _completeness(doc: Document, unknown_author_id: int, unknown_org_id: int) -> int:
    score = sum(1 for field in _COMPLETENESS_FIELDS if getattr(doc, field) is not None)
    if doc.author_id != unknown_author_id:
        score += 1
    if doc.organization_id != unknown_org_id:
        score += 1
    return score


def _pick_canonical(members: list[Document], unknown_author_id: int, unknown_org_id: int) -> Document:
    def sort_key(doc: Document) -> tuple[date, int, int]:
        published = doc.published_at or date.max
        return (published, -_completeness(doc, unknown_author_id, unknown_org_id), doc.id)

    return min(members, key=sort_key)


def _confidence(doc: Document, members: list[Document], unknown_author_id: int, unknown_org_id: int) -> float:
    others = [m for m in members if m.id != doc.id]

    score = 0.5
    if any(_authors_match(doc, other, unknown_author_id) for other in others):
        score += 0.25
    if any(_sources_match(doc, other) for other in others):
        score += 0.25
    if any(_organizations_match(doc, other, unknown_org_id) for other in others):
        score += 0.1
    if any(_languages_match(doc, other) for other in others):
        score += 0.1
    if any(_regions_match(doc, other) for other in others):
        score += 0.1

    return min(score, 1.0)
