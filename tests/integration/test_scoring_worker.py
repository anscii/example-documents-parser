import itertools
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Author, Document, IngestionRun, Organization, RawDocument
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME
from app.processing import scoring_worker

_line_numbers = itertools.count(1)


def _make_run(db_session) -> IngestionRun:
    run = IngestionRun(
        source_file="f.jsonl",
        file_hash="h",
        staged_path="/tmp/f.jsonl",
        status="processing",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _unknown_author_id(db_session) -> int:
    return db_session.scalar(
        select(Author.id).where(Author.normalized_name == UNKNOWN_NORMALIZED_NAME)
    )


def _unknown_org_id(db_session) -> int:
    return db_session.scalar(
        select(Organization.id).where(Organization.normalized_name == UNKNOWN_NORMALIZED_NAME)
    )


def _make_document(db_session, run, raw_data=None, **overrides) -> Document:
    raw_doc = RawDocument(
        ingestion_run_id=run.id,
        line_number=next(_line_numbers),
        raw_data=raw_data or {},
        status="normalized",
    )
    db_session.add(raw_doc)
    db_session.flush()

    defaults = {
        "raw_document_id": raw_doc.id,
        "raw_external_id": None,
        "title": "Sample Title",
        "normalized_title": None,
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


def test_citation_percentile_ranking(db_session):
    run = _make_run(db_session)

    doc_low = _make_document(db_session, run, citation_count=10)
    doc_mid = _make_document(db_session, run, citation_count=20)
    doc_high = _make_document(db_session, run, citation_count=30)

    processed, remaining = scoring_worker.process_batch(db_session, batch_size=10)
    assert processed == 3
    assert remaining == 0

    db_session.refresh(doc_low)
    db_session.refresh(doc_mid)
    db_session.refresh(doc_high)

    assert doc_low.quality_score == 8.33
    assert doc_mid.quality_score == 16.67
    assert doc_high.quality_score == 25.0


def test_many_citation_sentinel_uses_p90(db_session):
    run = _make_run(db_session)

    _make_document(db_session, run, citation_count=10)
    _make_document(db_session, run, citation_count=20)
    _make_document(db_session, run, citation_count=30)
    doc_many = _make_document(
        db_session, run, citation_count=None, raw_data={"citation_count": "many"}
    )

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc_many)
    assert doc_many.quality_score == 16.67


def test_high_relevance_sentinel(db_session):
    run = _make_run(db_session)

    doc = _make_document(
        db_session, run, relevance_score=None, raw_data={"relevance_score": "high"}
    )

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 18.0


def test_future_published_at_gives_max_recency_bonus(db_session):
    run = _make_run(db_session)

    doc = _make_document(db_session, run, published_at=date.today() + timedelta(days=30))

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 20.0


def test_missing_published_at_gives_zero_recency(db_session):
    run = _make_run(db_session)

    doc = _make_document(db_session, run, published_at=None)

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 0.0


def test_quality_score_clamped_to_100(db_session):
    run = _make_run(db_session)

    doc = _make_document(
        db_session,
        run,
        citation_count=100,
        relevance_score=2.0,
        published_at=date.today(),
        peer_reviewed=True,
        open_access=True,
        word_count=1000,
        page_count=10,
    )

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 100.0


def test_process_batch_returns_zero_when_nothing_pending(db_session):
    processed, remaining = scoring_worker.process_batch(db_session, batch_size=10)
    assert processed == 0
    assert remaining == 0
