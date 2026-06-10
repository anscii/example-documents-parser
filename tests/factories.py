import itertools

from sqlalchemy import select

from app.models import Author, Document, IngestionRun, Organization, RawDocument, Tag
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME

_counter = itertools.count(1)


def make_run(db_session) -> IngestionRun:
    n = next(_counter)
    run = IngestionRun(source_file=f"f{n}.jsonl", file_hash=f"hash{n}", staged_path=f"/tmp/f{n}.jsonl", status="completed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def unknown_author_id(db_session) -> int:
    return db_session.scalar(select(Author.id).where(Author.normalized_name == UNKNOWN_NORMALIZED_NAME))


def unknown_org_id(db_session) -> int:
    return db_session.scalar(select(Organization.id).where(Organization.normalized_name == UNKNOWN_NORMALIZED_NAME))


def _upsert_tags(db_session, names: list[str]) -> list[Tag]:
    result = []
    for name in names:
        tag = db_session.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db_session.add(tag)
            db_session.flush()
        result.append(tag)
    return result


def make_document(db_session, run, raw_data=None, tags=None, **overrides) -> Document:
    raw_doc = RawDocument(
        ingestion_run_id=run.id,
        line_number=next(_counter),
        raw_data=raw_data or {},
        status="normalized",
    )
    db_session.add(raw_doc)
    db_session.flush()

    defaults = {
        "raw_document_id": raw_doc.id,
        "raw_external_id": None,
        "title": "Sample Title",
        "normalized_title": "sample title",
        "author_id": unknown_author_id(db_session),
        "organization_id": unknown_org_id(db_session),
        "language": "en",
        "status": "published",
        "document_type": "report",
        "source_name": None,
        "region": None,
    }
    defaults.update(overrides)

    document = Document(**defaults)
    if tags:
        document.tags = _upsert_tags(db_session, tags)

    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document
