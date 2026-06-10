import itertools
from datetime import date

from sqlalchemy import select

from app.models import Author, Document, IngestionRun, Organization, RawDocument
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME
from app.processing import duplicates_worker

_line_numbers = itertools.count(1)


def _make_run(db_session) -> IngestionRun:
    run = IngestionRun(source_file="f.jsonl", file_hash="h", staged_path="/tmp/f.jsonl", status="processing")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _unknown_author_id(db_session) -> int:
    return db_session.scalar(select(Author.id).where(Author.normalized_name == UNKNOWN_NORMALIZED_NAME))


def _unknown_org_id(db_session) -> int:
    return db_session.scalar(select(Organization.id).where(Organization.normalized_name == UNKNOWN_NORMALIZED_NAME))


def _make_document(db_session, run, **overrides) -> Document:
    raw_doc = RawDocument(
        ingestion_run_id=run.id,
        line_number=next(_line_numbers),
        raw_data={},
        status="normalized",
    )
    db_session.add(raw_doc)
    db_session.flush()

    defaults = {
        "raw_document_id": raw_doc.id,
        "raw_external_id": None,
        "title": "Sample Title",
        "normalized_title": "sample title",
        "author_id": _unknown_author_id(db_session),
        "organization_id": _unknown_org_id(db_session),
        "language": "unknown",
        "status": "unknown",
        "document_type": "unknown",
        "source_name": None,
        "region": None,
    }
    defaults.update(overrides)

    document = Document(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def test_blank_title_is_singleton(db_session):
    run = _make_run(db_session)
    doc = _make_document(db_session, run, normalized_title=None)

    processed, remaining = duplicates_worker.process_batch(db_session, batch_size=10)

    assert processed == 1
    assert remaining == 0

    db_session.refresh(doc)
    assert doc.is_canonical is True
    assert doc.duplicate_group_id is None
    assert doc.duplicate_confidence is None


def test_unique_title_is_singleton(db_session):
    run = _make_run(db_session)
    doc = _make_document(db_session, run, normalized_title="a unique title")

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.is_canonical is True
    assert doc.duplicate_group_id is None
    assert doc.duplicate_confidence is None


def test_author_only_edge_groups_documents(db_session):
    run = _make_run(db_session)

    author = Author(name="Jane Doe", normalized_name="jane doe")
    db_session.add(author)
    db_session.flush()

    doc_a = _make_document(
        db_session, run, normalized_title="shared title", author_id=author.id, source_name="Feed A"
    )
    doc_b = _make_document(
        db_session, run, normalized_title="shared title", author_id=author.id, source_name="Feed B"
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.duplicate_group_id == doc_b.duplicate_group_id == doc_a.id
    assert {doc_a.is_canonical, doc_b.is_canonical} == {True, False}
    assert doc_a.duplicate_confidence == 0.75
    assert doc_b.duplicate_confidence == 0.75


def test_source_only_edge_groups_documents(db_session):
    run = _make_run(db_session)

    author_a = Author(name="Author A", normalized_name="author a")
    author_b = Author(name="Author B", normalized_name="author b")
    db_session.add_all([author_a, author_b])
    db_session.flush()

    doc_a = _make_document(
        db_session, run, normalized_title="shared title 2", author_id=author_a.id, source_name="Feed A"
    )
    doc_b = _make_document(
        db_session, run, normalized_title="shared title 2", author_id=author_b.id, source_name="Feed A"
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.duplicate_group_id == doc_b.duplicate_group_id == doc_a.id
    assert doc_a.duplicate_confidence == 0.75
    assert doc_b.duplicate_confidence == 0.75


def test_neither_author_nor_source_match_yields_singletons(db_session):
    run = _make_run(db_session)

    author_c = Author(name="Author C", normalized_name="author c")
    author_d = Author(name="Author D", normalized_name="author d")
    db_session.add_all([author_c, author_d])
    db_session.flush()

    doc_a = _make_document(
        db_session, run, normalized_title="shared title 3", author_id=author_c.id, source_name="Feed A"
    )
    doc_b = _make_document(
        db_session, run, normalized_title="shared title 3", author_id=author_d.id, source_name="Feed B"
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_canonical is True
    assert doc_b.is_canonical is True
    assert doc_a.duplicate_group_id is None
    assert doc_b.duplicate_group_id is None
    assert doc_a.duplicate_confidence is None
    assert doc_b.duplicate_confidence is None


def test_unknown_author_and_null_source_never_create_edge(db_session):
    run = _make_run(db_session)
    unknown_author_id = _unknown_author_id(db_session)

    doc_a = _make_document(
        db_session, run, normalized_title="shared title 4", author_id=unknown_author_id, source_name=None
    )
    doc_b = _make_document(
        db_session, run, normalized_title="shared title 4", author_id=unknown_author_id, source_name=None
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.is_canonical is True
    assert doc_b.is_canonical is True
    assert doc_a.duplicate_group_id is None
    assert doc_b.duplicate_group_id is None


def test_confidence_capped_at_one(db_session):
    run = _make_run(db_session)

    author = Author(name="Author E", normalized_name="author e")
    org = Organization(name="Org E", normalized_name="org e")
    db_session.add_all([author, org])
    db_session.flush()

    common = {
        "normalized_title": "shared title 5",
        "author_id": author.id,
        "organization_id": org.id,
        "source_name": "Feed A",
        "language": "en",
        "region": "Global",
    }
    doc_a = _make_document(db_session, run, **common)
    doc_b = _make_document(db_session, run, **common)

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)

    assert doc_a.duplicate_confidence == 1.0
    assert doc_b.duplicate_confidence == 1.0


def test_canonical_pick_prefers_earliest_published_at(db_session):
    run = _make_run(db_session)

    author = Author(name="Author F", normalized_name="author f")
    db_session.add(author)
    db_session.flush()

    doc_late = _make_document(
        db_session, run, normalized_title="shared title 6", author_id=author.id, published_at=date(2022, 1, 1)
    )
    doc_early = _make_document(
        db_session, run, normalized_title="shared title 6", author_id=author.id, published_at=date(2020, 1, 1)
    )
    doc_no_date = _make_document(
        db_session, run, normalized_title="shared title 6", author_id=author.id, published_at=None
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_early)
    db_session.refresh(doc_late)
    db_session.refresh(doc_no_date)

    assert doc_early.is_canonical is True
    assert doc_late.is_canonical is False
    assert doc_no_date.is_canonical is False
    assert doc_early.duplicate_group_id == doc_late.duplicate_group_id == doc_no_date.duplicate_group_id


def test_canonical_pick_tiebreaks_by_completeness_then_id(db_session):
    run = _make_run(db_session)

    author = Author(name="Author G", normalized_name="author g")
    db_session.add(author)
    db_session.flush()

    same_date = date(2021, 1, 1)
    doc_sparse = _make_document(
        db_session, run, normalized_title="shared title 7", author_id=author.id, published_at=same_date
    )
    doc_rich = _make_document(
        db_session,
        run,
        normalized_title="shared title 7",
        author_id=author.id,
        published_at=same_date,
        abstract="abstract",
        body="body",
        doi="10.1/abc",
        url="https://x",
        region="Global",
        citation_count=1,
        word_count=1,
        page_count=1,
    )

    duplicates_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_sparse)
    db_session.refresh(doc_rich)

    assert doc_rich.is_canonical is True
    assert doc_sparse.is_canonical is False


def test_component_merges_when_bridging_document_arrives(db_session):
    run = _make_run(db_session)

    author_h = Author(name="Author H", normalized_name="author h")
    author_i = Author(name="Author I", normalized_name="author i")
    db_session.add_all([author_h, author_i])
    db_session.flush()

    doc_a = _make_document(
        db_session, run, normalized_title="shared title 8", author_id=author_h.id, source_name="Feed A"
    )
    doc_b = _make_document(
        db_session, run, normalized_title="shared title 8", author_id=author_i.id, source_name="Feed A"
    )

    processed, remaining = duplicates_worker.process_batch(db_session, batch_size=10)
    assert processed == 2
    assert remaining == 0

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    assert doc_a.duplicate_group_id == doc_b.duplicate_group_id == doc_a.id

    # doc_c shares an author with doc_b (but not doc_a) and a different source
    # than either - it should bridge doc_a and doc_b into one component.
    doc_c = _make_document(
        db_session, run, normalized_title="shared title 8", author_id=author_i.id, source_name="Feed C"
    )

    processed, remaining = duplicates_worker.process_batch(db_session, batch_size=10)
    assert processed == 1
    assert remaining == 0

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    db_session.refresh(doc_c)

    assert doc_a.duplicate_group_id == doc_b.duplicate_group_id == doc_c.duplicate_group_id == doc_a.id
