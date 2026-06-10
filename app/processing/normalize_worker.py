from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.normalizers import (
    booleans,
    dates,
    identity,
    language,
    links,
    numbers,
    tags,
    text,
)
from app.ingestion.normalizers import document_type as document_type_normalizer
from app.ingestion.normalizers import status as status_normalizer
from app.models import Author, Document, Organization, RawDocument, Tag
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME

logger = logging.getLogger(__name__)


def process_batch(db: Session, batch_size: int) -> tuple[int, int]:
    """Stage 1: normalize a batch of pending raw_documents into documents rows."""
    raw_docs = (
        db.execute(
            select(RawDocument)
            .where(RawDocument.status == "pending")
            .order_by(RawDocument.id)
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    if not raw_docs:
        return 0, _count_pending(db)

    author_cache = _load_id_cache(db, Author)
    organization_cache = _load_id_cache(db, Organization)
    tag_cache = _load_tag_cache(db)

    for raw_doc in raw_docs:
        document, warnings = _build_document(
            db, raw_doc, author_cache, organization_cache, tag_cache
        )
        db.add(document)
        raw_doc.status = "normalized"
        raw_doc.normalized_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if warnings:
            logger.warning("raw_document %s: %s", raw_doc.id, "; ".join(warnings))

    db.commit()

    remaining = _count_pending(db)
    logger.info("stage 1: normalized %d raw documents (remaining=%d)", len(raw_docs), remaining)
    return len(raw_docs), remaining


def _count_pending(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(RawDocument).where(RawDocument.status == "pending")
        )
        or 0
    )


def _load_id_cache(db: Session, model: type[Author] | type[Organization]) -> dict[str, int]:
    return dict(db.execute(select(model.normalized_name, model.id)).tuples().all())


def _load_tag_cache(db: Session) -> dict[str, Tag]:
    return {tag.name: tag for tag in db.execute(select(Tag)).scalars().all()}


def _upsert_person_or_org(
    db: Session,
    model: type[Author] | type[Organization],
    cache: dict[str, int],
    raw_name: object,
) -> tuple[int, str | None]:
    clean_name, warning = identity.normalize_person_or_org_name(raw_name)
    if clean_name is None:
        return cache[UNKNOWN_NORMALIZED_NAME], warning

    normalized_key = text.normalize_title_for_grouping(clean_name)
    entity_id = cache.get(normalized_key)
    if entity_id is None:
        entity = model(name=clean_name, normalized_name=normalized_key)
        db.add(entity)
        db.flush()
        entity_id = entity.id
        cache[normalized_key] = entity_id
    return entity_id, warning


def _upsert_tags(db: Session, cache: dict[str, Tag], tag_names: list[str]) -> list[Tag]:
    result = []
    for name in tag_names:
        tag = cache.get(name)
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
            cache[name] = tag
        result.append(tag)
    return result


def _build_document(
    db: Session,
    raw_doc: RawDocument,
    author_cache: dict[str, int],
    organization_cache: dict[str, int],
    tag_cache: dict[str, Tag],
) -> tuple[Document, list[str]]:
    raw_data = raw_doc.raw_data
    warnings: list[str] = []

    def track(field: str, warning: str | None) -> None:
        if warning:
            warnings.append(f"{field}: {warning}")

    raw_external_id, warning = identity.normalize_external_id(raw_data.get("external_id"))
    track("external_id", warning)

    title, warning = text.normalize_text(raw_data.get("title"))
    track("title", warning)
    normalized_title = text.normalize_title_for_grouping(title) if title else None

    abstract, warning = text.normalize_text(raw_data.get("abstract"))
    track("abstract", warning)

    body, warning = text.normalize_text(raw_data.get("body"))
    track("body", warning)

    published_at, published_at_raw, warning = dates.normalize_date(raw_data.get("published_at"))
    track("published_at", warning)

    updated_at, updated_at_raw, warning = dates.normalize_date(raw_data.get("updated_at"))
    track("updated_at", warning)

    source_name, warning = identity.normalize_source_name(raw_data.get("source_name"))
    track("source_name", warning)

    author_id, warning = _upsert_person_or_org(
        db, Author, author_cache, raw_data.get("author_name")
    )
    track("author_name", warning)

    organization_id, warning = _upsert_person_or_org(
        db, Organization, organization_cache, raw_data.get("organization_name")
    )
    track("organization_name", warning)

    doc_language, language_raw, warning = language.normalize_language(raw_data.get("language"))
    track("language", warning)

    doc_status, status_raw, warning = status_normalizer.normalize_status(raw_data.get("status"))
    track("status", warning)

    doc_type, document_type_raw, warning = document_type_normalizer.normalize_document_type(
        raw_data.get("document_type")
    )
    track("document_type", warning)

    region, warning = text.normalize_text(raw_data.get("region"))
    track("region", warning)

    url, url_valid, warning = links.normalize_url(raw_data.get("url"))
    track("url", warning)

    doi, doi_valid, warning = links.normalize_doi(raw_data.get("doi"))
    track("doi", warning)

    citation_count, warning = numbers.coerce_int(raw_data.get("citation_count"))
    track("citation_count", warning)

    word_count, warning = numbers.coerce_int(raw_data.get("word_count"))
    track("word_count", warning)

    page_count, warning = numbers.coerce_int(raw_data.get("page_count"))
    track("page_count", warning)

    relevance_score, warning = numbers.coerce_float(raw_data.get("relevance_score"))
    track("relevance_score", warning)

    version, warning = numbers.normalize_version(raw_data.get("version"))
    track("version", warning)

    open_access, open_access_raw, warning = booleans.coerce_nullable_bool(
        raw_data.get("open_access")
    )
    track("open_access", warning)

    peer_reviewed, peer_reviewed_raw, warning = booleans.coerce_nullable_bool(
        raw_data.get("peer_reviewed")
    )
    track("peer_reviewed", warning)

    tag_names, warning = tags.normalize_tags(raw_data.get("tags"))
    track("tags", warning)
    doc_tags = _upsert_tags(db, tag_cache, tag_names)

    document = Document(
        raw_document_id=raw_doc.id,
        raw_external_id=raw_external_id,
        title=title,
        normalized_title=normalized_title,
        abstract=abstract,
        body=body,
        published_at=published_at,
        published_at_raw=published_at_raw,
        updated_at=updated_at,
        updated_at_raw=updated_at_raw,
        source_name=source_name,
        author_id=author_id,
        organization_id=organization_id,
        language=doc_language,
        language_raw=language_raw,
        status=doc_status,
        status_raw=status_raw,
        document_type=doc_type,
        document_type_raw=document_type_raw,
        region=region,
        url=url,
        url_valid=url_valid,
        doi=doi,
        doi_valid=doi_valid,
        citation_count=citation_count,
        word_count=word_count,
        page_count=page_count,
        relevance_score=relevance_score,
        version=version,
        open_access=open_access,
        open_access_raw=open_access_raw,
        peer_reviewed=peer_reviewed,
        peer_reviewed_raw=peer_reviewed_raw,
        tags=doc_tags,
        normalization_warnings=warnings or None,
    )
    return document, warnings
