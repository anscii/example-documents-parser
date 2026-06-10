from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.models import Author, Document, IngestionError, IngestionRun, Organization
from app.models.sentinels import UNKNOWN_NORMALIZED_NAME

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sample_input" / "staged_pipeline.jsonl"
)


def _post_fixture(client):
    with open(FIXTURE_PATH, "rb") as f:
        return client.post(
            "/ingestions",
            files={"file": ("staged_pipeline.jsonl", f, "application/x-ndjson")},
        )


def _documents_by_normalized_title(db_session, normalized_title):
    return db_session.scalars(
        select(Document).where(Document.normalized_title == normalized_title).order_by(Document.id)
    ).all()


def test_staged_pipeline_runs_to_completion(client, db_session):
    response = _post_fixture(client)
    assert response.status_code == 201
    run_id = response.json()["id"]

    run = db_session.get(IngestionRun, run_id)
    assert run.status == "completed"
    assert run.total_lines == 12
    assert run.raw_loaded_count == 8
    assert run.skipped_count == 4

    errors = (
        db_session.query(IngestionError)
        .filter_by(run_id=run_id)
        .order_by(IngestionError.line_number)
        .all()
    )
    assert [(e.line_number, e.error_category) for e in errors] == [
        (2, "not_object"),
        (3, "broken_stub"),
        (4, "invalid_json"),
        (5, "empty"),
    ]

    documents = db_session.query(Document).all()
    assert len(documents) == 8
    for document in documents:
        assert document.is_canonical is not None
        assert document.quality_score is not None


def test_staged_pipeline_normalizes_messy_record(client, db_session):
    _post_fixture(client)

    document = db_session.scalar(
        select(Document).where(Document.normalized_title == "untitled field notes")
    )
    assert document is not None
    assert document.raw_external_id is None
    assert document.source_name is None
    assert document.region is None
    assert document.language == "unknown"
    assert document.document_type == "unknown"
    assert document.tags == []
    assert document.published_at == date(2021, 3, 15)
    assert document.normalization_warnings == [
        "citation_count: could not parse integer: 'many'",
        "relevance_score: could not parse float: 'high'",
        "peer_reviewed: unexpected integer for boolean field: 2",
        "tags: tags list contained non-string elements, which were dropped",
    ]

    author = db_session.get(Author, document.author_id)
    organization = db_session.get(Organization, document.organization_id)
    assert author.normalized_name == UNKNOWN_NORMALIZED_NAME
    assert organization.normalized_name == UNKNOWN_NORMALIZED_NAME


def test_staged_pipeline_groups_duplicates_by_shared_author(client, db_session):
    _post_fixture(client)

    canonical, duplicate = _documents_by_normalized_title(db_session, "energy transition roadmap")

    assert canonical.duplicate_group_id == duplicate.duplicate_group_id == canonical.id
    assert canonical.is_canonical is True
    assert duplicate.is_canonical is False
    assert canonical.duplicate_confidence == 0.75
    assert duplicate.duplicate_confidence == 0.75


def test_staged_pipeline_groups_duplicates_by_shared_source(client, db_session):
    _post_fixture(client)

    canonical, duplicate = _documents_by_normalized_title(db_session, "coastal resilience plan")

    assert canonical.duplicate_group_id == duplicate.duplicate_group_id == canonical.id
    assert canonical.is_canonical is True
    assert duplicate.is_canonical is False
    assert canonical.duplicate_confidence == 0.75
    assert duplicate.duplicate_confidence == 0.75


def test_staged_pipeline_same_title_different_author_and_source_are_not_duplicates(
    client, db_session
):
    _post_fixture(client)

    docs = _documents_by_normalized_title(db_session, "annual sustainability review")

    assert len(docs) == 2
    for document in docs:
        assert document.is_canonical is True
        assert document.duplicate_group_id is None
        assert document.duplicate_confidence is None


def test_staged_pipeline_document_detail_shows_duplicate_group(client, db_session):
    _post_fixture(client)

    canonical, duplicate = _documents_by_normalized_title(db_session, "energy transition roadmap")

    canonical_body = client.get(f"/documents/{canonical.id}").json()
    duplicate_body = client.get(f"/documents/{duplicate.id}").json()

    for body, is_canonical in ((canonical_body, True), (duplicate_body, False)):
        assert body["duplicate_group"] == {
            "group_id": canonical.id,
            "group_size": 2,
            "is_canonical": is_canonical,
            "confidence": 0.75,
        }


def test_staged_pipeline_processing_endpoints_report_drained(client):
    _post_fixture(client)

    for path in (
        "/processing/normalize",
        "/processing/duplicates",
        "/processing/scoring",
    ):
        response = client.post(path)
        assert response.json() == {"processed": 0, "remaining": 0}
