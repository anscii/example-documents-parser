from datetime import date

import pytest

from app.models import Author, Organization
from tests.factories import make_document, make_run


def _seed(db_session):
    run = make_run(db_session)

    author_jane = Author(name="Jane Doe", normalized_name="jane doe")
    author_john = Author(name="John Smith", normalized_name="john smith")
    org_climate = Organization(name="Climate Institute", normalized_name="climate institute")
    org_urban = Organization(name="Urban Council", normalized_name="urban council")
    db_session.add_all([author_jane, author_john, org_climate, org_urban])
    db_session.flush()

    doc_climate = make_document(
        db_session,
        run,
        title="Climate Policy Report",
        normalized_title="climate policy report",
        author_id=author_jane.id,
        organization_id=org_climate.id,
        source_name="Feed A",
        published_at=date(2021, 1, 1),
        language="en",
        status="published",
        document_type="report",
        region="Europe",
        citation_count=50,
        relevance_score=0.8,
        quality_score=70.0,
        is_canonical=True,
        tags=["energy", "climate"],
    )

    doc_urban = make_document(
        db_session,
        run,
        title="Urban Development Strategies",
        normalized_title="urban development strategies",
        author_id=author_john.id,
        organization_id=org_urban.id,
        source_name="Feed B",
        published_at=date(2022, 6, 15),
        language="fr",
        status="draft",
        document_type="working_paper",
        region="North America",
        citation_count=5,
        relevance_score=0.3,
        quality_score=30.0,
        is_canonical=True,
        tags=["urban"],
    )

    doc_dup_a = make_document(
        db_session,
        run,
        title="Shared Report",
        normalized_title="shared report",
        published_at=date(2020, 1, 1),
        quality_score=50.0,
        is_canonical=True,
    )
    doc_dup_b = make_document(
        db_session,
        run,
        title="Shared Report",
        normalized_title="shared report",
        published_at=date(2020, 6, 1),
        quality_score=40.0,
        is_canonical=False,
        duplicate_confidence=0.75,
    )
    doc_dup_a.duplicate_group_id = doc_dup_a.id
    doc_dup_b.duplicate_group_id = doc_dup_a.id
    doc_dup_a.duplicate_confidence = 0.75
    db_session.add_all([doc_dup_a, doc_dup_b])
    db_session.commit()
    db_session.refresh(doc_dup_a)
    db_session.refresh(doc_dup_b)

    doc_pending = make_document(
        db_session,
        run,
        title="Pending Document",
        normalized_title="pending document",
    )

    return {
        "climate": doc_climate,
        "urban": doc_urban,
        "dup_a": doc_dup_a,
        "dup_b": doc_dup_b,
        "pending": doc_pending,
    }


@pytest.fixture()
def seeded(db_session):
    return _seed(db_session)


def test_list_documents_default_includes_known_duplicates_and_pending(client, seeded):
    response = client.get("/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert {item["id"] for item in body["items"]} == {doc.id for doc in seeded.values()}


def test_list_documents_canonical_only_excludes_known_duplicates(client, seeded):
    response = client.get("/documents", params={"canonical_only": "true"})

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["items"]}
    assert seeded["dup_b"].id not in ids
    assert body["total"] == 4


def test_list_documents_filter_by_published_after(client, seeded):
    response = client.get("/documents", params={"published_after": "2022-01-01"})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["urban"].id]


def test_list_documents_filter_by_published_before(client, seeded):
    response = client.get("/documents", params={"published_before": "2020-12-31"})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["dup_a"].id, seeded["dup_b"].id]


def test_list_documents_filter_by_tag_case_insensitive(client, seeded):
    response = client.get("/documents", params={"tag": "ENERGY"})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["climate"].id]


def test_list_documents_filter_by_organization_case_insensitive(client, seeded):
    response = client.get("/documents", params={"organization": "climate institute"})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["climate"].id]


@pytest.mark.parametrize(
    ("param", "value", "expected_key"),
    [
        ("status", "draft", "urban"),
        ("document_type", "working_paper", "urban"),
        ("language", "fr", "urban"),
        ("region", "Europe", "climate"),
    ],
)
def test_list_documents_filter_by_taxonomy_field(client, seeded, param, value, expected_key):
    response = client.get("/documents", params={param: value})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded[expected_key].id]


def test_list_documents_filter_by_q_searches_title(client, seeded):
    response = client.get("/documents", params={"q": "climate"})

    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["climate"].id]


def test_list_documents_filter_by_min_quality_score(client, seeded):
    response = client.get("/documents", params={"min_quality_score": 50})

    body = response.json()
    assert {item["id"] for item in body["items"]} == {seeded["climate"].id, seeded["dup_a"].id}


def test_list_documents_sort_by_quality_score_desc(client, seeded):
    response = client.get("/documents", params={"sort_by": "quality_score", "sort_dir": "desc"})

    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert ids[0] == seeded["climate"].id
    assert ids[-1] == seeded["pending"].id


def test_list_documents_pagination(client, seeded):
    page1 = client.get("/documents", params={"page": 1, "page_size": 2}).json()
    page2 = client.get("/documents", params={"page": 2, "page_size": 2}).json()
    page3 = client.get("/documents", params={"page": 3, "page_size": 2}).json()

    assert page1["total"] == page2["total"] == page3["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1

    all_ids = [item["id"] for page in (page1, page2, page3) for item in page["items"]]
    assert all_ids == sorted(all_ids)
    assert len(set(all_ids)) == 5


def test_get_document_detail_singleton_has_no_duplicate_group(client, seeded):
    response = client.get(f"/documents/{seeded['climate'].id}")

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate_group"] is None
    assert {tag["name"] for tag in body["tags"]} == {"energy", "climate"}
    assert body["author"]["name"] == "Jane Doe"
    assert body["organization"]["name"] == "Climate Institute"


def test_get_document_detail_duplicate_group_members(client, seeded):
    canonical = client.get(f"/documents/{seeded['dup_a'].id}").json()
    duplicate = client.get(f"/documents/{seeded['dup_b'].id}").json()

    for body, is_canonical in ((canonical, True), (duplicate, False)):
        assert body["duplicate_group"] == {
            "group_id": seeded["dup_a"].id,
            "group_size": 2,
            "is_canonical": is_canonical,
            "confidence": 0.75,
        }


def test_get_document_pending_has_null_score_and_canonical(client, seeded):
    response = client.get(f"/documents/{seeded['pending'].id}")

    body = response.json()
    assert body["quality_score"] is None
    assert body["is_canonical"] is None
    assert body["duplicate_group"] is None


def test_get_document_not_found(client):
    response = client.get("/documents/999999")

    assert response.status_code == 404
