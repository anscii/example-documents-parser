import itertools
from datetime import date, timedelta

from app.models import Document, RawDocument
from app.processing import scoring_worker
from tests.factories import make_run, unknown_author_id, unknown_org_id

_line_numbers = itertools.count(1)


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
        "author_id": unknown_author_id(db_session),
        "organization_id": unknown_org_id(db_session),
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
    run = make_run(db_session)

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
    run = make_run(db_session)

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
    run = make_run(db_session)

    doc = _make_document(
        db_session, run, relevance_score=None, raw_data={"relevance_score": "high"}
    )

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 18.0


def test_future_published_at_gives_max_recency_bonus(db_session):
    run = make_run(db_session)

    doc = _make_document(db_session, run, published_at=date.today() + timedelta(days=30))

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 20.0


def test_missing_published_at_gives_zero_recency(db_session):
    run = make_run(db_session)

    doc = _make_document(db_session, run, published_at=None)

    scoring_worker.process_batch(db_session, batch_size=10)

    db_session.refresh(doc)
    assert doc.quality_score == 0.0


def test_quality_score_clamped_to_100(db_session):
    run = make_run(db_session)

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


def test_citation_count_distribution_is_cached_per_session(
    db_session, db_session_factory, monkeypatch
):
    run = make_run(db_session)
    _make_document(db_session, run, citation_count=10)
    _make_document(db_session, run, citation_count=20)

    call_count = {"n": 0}
    original = scoring_worker._citation_count_distribution

    def spy(db):
        call_count["n"] += 1
        return original(db)

    monkeypatch.setattr(scoring_worker, "_citation_count_distribution", spy)

    scoring_worker.process_batch(db_session, batch_size=1)
    scoring_worker.process_batch(db_session, batch_size=1)
    assert call_count["n"] == 1

    other_session = db_session_factory()
    try:
        scoring_worker.process_batch(other_session, batch_size=10)
    finally:
        other_session.close()
    assert call_count["n"] == 2
