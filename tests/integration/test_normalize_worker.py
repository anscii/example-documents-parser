from datetime import date

from app.models import Author, Document, IngestionRun, Organization, RawDocument
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME
from app.processing import normalize_worker

FULL_RECORD = {
    "external_id": "doc-100",
    "title": "  Climate   Policy   Report  ",
    "abstract": "An abstract.",
    "body": "Body text.",
    "author_name": "  Jane Doe  ",
    "organization_name": "Climate Institute",
    "source_name": "Feed A",
    "language": "english",
    "status": "PUBLISHED",
    "document_type": "REPORT",
    "region": "Southern Europe",
    "published_at": "2021-05-01",
    "updated_at": 20210601,
    "tags": "energy; renewables",
    "url": "https://example.com/report.pdf",
    "doi": "10.1234/abcd",
    "citation_count": "12",
    "word_count": 1000,
    "page_count": "10",
    "relevance_score": 1,
    "version": 1.0,
    "open_access": "yes",
    "peer_reviewed": 0,
}

DUPLICATE_AUTHOR_RECORD = {
    "external_id": "doc-101",
    "author_name": "JANE DOE",
    "organization_name": "  climate institute  ",
}

MESSY_RECORD = {
    "external_id": "duplicate-id",
    "title": None,
    "author_name": "N/A",
    "organization_name": None,
    "source_name": "unknown",
    "language": "xx",
    "status": 5,
    "document_type": "something_else",
    "region": "",
    "published_at": "invalid-date",
    "tags": [None],
    "citation_count": "many",
    "relevance_score": "high",
    "open_access": "yes",
    "peer_reviewed": 2,
}


def _make_run(db_session) -> IngestionRun:
    run = IngestionRun(
        source_file="mini.jsonl",
        file_hash="hash",
        staged_path="/tmp/mini.jsonl",
        status="processing",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _add_raw_doc(db_session, run, raw_data, line_number):
    raw_doc = RawDocument(
        ingestion_run_id=run.id,
        line_number=line_number,
        raw_data=raw_data,
        status="pending",
    )
    db_session.add(raw_doc)
    db_session.commit()
    db_session.refresh(raw_doc)
    return raw_doc


def test_process_batch_normalizes_full_record(db_session):
    run = _make_run(db_session)
    raw_doc = _add_raw_doc(db_session, run, FULL_RECORD, line_number=1)

    processed, remaining = normalize_worker.process_batch(db_session, batch_size=10)

    assert processed == 1
    assert remaining == 0

    db_session.refresh(raw_doc)
    assert raw_doc.status == "normalized"
    assert raw_doc.normalized_at is not None

    document = db_session.query(Document).filter_by(raw_document_id=raw_doc.id).one()
    assert document.raw_external_id == "doc-100"
    assert document.title == "Climate   Policy   Report"
    assert document.normalized_title == "climate policy report"
    assert document.abstract == "An abstract."
    assert document.body == "Body text."
    assert document.published_at == date(2021, 5, 1)
    assert document.published_at_raw == "2021-05-01"
    assert document.updated_at == date(2021, 6, 1)
    assert document.updated_at_raw == "20210601"
    assert document.source_name == "Feed A"
    assert document.language == "en"
    assert document.language_raw == "english"
    assert document.status == "published"
    assert document.status_raw == repr("PUBLISHED")
    assert document.document_type == "report"
    assert document.document_type_raw == "REPORT"
    assert document.region == "Southern Europe"
    assert document.url == "https://example.com/report.pdf"
    assert document.url_valid is True
    assert document.doi == "10.1234/abcd"
    assert document.doi_valid is True
    assert document.citation_count == 12
    assert document.word_count == 1000
    assert document.page_count == 10
    assert document.relevance_score == 1.0
    assert document.version == "1.0"
    assert document.open_access is True
    assert document.peer_reviewed is False
    assert document.normalization_warnings is None
    assert sorted(tag.name for tag in document.tags) == ["energy", "renewables"]

    author = db_session.get(Author, document.author_id)
    assert author.name == "Jane Doe"
    assert author.normalized_name == "jane doe"

    organization = db_session.get(Organization, document.organization_id)
    assert organization.name == "Climate Institute"
    assert organization.normalized_name == "climate institute"


def test_process_batch_dedups_authors_and_organizations_within_batch(db_session):
    run = _make_run(db_session)
    _add_raw_doc(db_session, run, FULL_RECORD, line_number=1)
    _add_raw_doc(db_session, run, DUPLICATE_AUTHOR_RECORD, line_number=2)

    processed, remaining = normalize_worker.process_batch(db_session, batch_size=10)

    assert processed == 2
    assert remaining == 0

    documents = db_session.query(Document).order_by(Document.id).all()
    assert documents[0].author_id == documents[1].author_id
    assert documents[0].organization_id == documents[1].organization_id

    # Only one new Author/Organization beyond the seeded "Unknown" sentinel.
    assert db_session.query(Author).count() == 2
    assert db_session.query(Organization).count() == 2


def test_process_batch_handles_messy_record(db_session):
    run = _make_run(db_session)
    raw_doc = _add_raw_doc(db_session, run, MESSY_RECORD, line_number=1)

    normalize_worker.process_batch(db_session, batch_size=10)

    document = db_session.query(Document).filter_by(raw_document_id=raw_doc.id).one()
    assert document.raw_external_id is None
    assert document.title is None
    assert document.normalized_title is None
    assert document.source_name is None
    assert document.region is None
    assert document.language == "unknown"
    assert document.status == "unknown"
    assert document.document_type == "unknown"
    assert document.published_at is None
    assert document.published_at_raw == "invalid-date"
    assert document.citation_count is None
    assert document.relevance_score is None
    assert document.open_access is True
    assert document.peer_reviewed is None
    assert document.tags == []

    unknown_author = db_session.get(Author, document.author_id)
    unknown_org = db_session.get(Organization, document.organization_id)
    assert unknown_author.normalized_name == UNKNOWN_NORMALIZED_NAME
    assert unknown_org.normalized_name == UNKNOWN_NORMALIZED_NAME

    assert document.normalization_warnings == [
        "published_at: could not parse date: 'invalid-date'",
        "citation_count: could not parse integer: 'many'",
        "relevance_score: could not parse float: 'high'",
        "peer_reviewed: unexpected integer for boolean field: 2",
        "tags: tags list contained non-string elements, which were dropped",
    ]


def test_process_batch_handles_empty_record(db_session):
    run = _make_run(db_session)
    raw_doc = _add_raw_doc(db_session, run, {}, line_number=1)

    normalize_worker.process_batch(db_session, batch_size=10)

    document = db_session.query(Document).filter_by(raw_document_id=raw_doc.id).one()
    assert document.title is None
    assert document.normalized_title is None
    assert document.language == "unknown"
    assert document.status == "unknown"
    assert document.status_raw == repr(None)
    assert document.document_type == "unknown"
    assert document.url is None
    assert document.url_valid is None
    assert document.tags == []
    assert document.normalization_warnings is None

    unknown_author = db_session.get(Author, document.author_id)
    assert unknown_author.normalized_name == UNKNOWN_NORMALIZED_NAME


def test_process_batch_returns_zero_when_nothing_pending(db_session):
    processed, remaining = normalize_worker.process_batch(db_session, batch_size=10)
    assert processed == 0
    assert remaining == 0
