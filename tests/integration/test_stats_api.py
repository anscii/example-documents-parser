from tests.factories import make_document, make_run


def _seed(db_session):
    run = make_run(db_session)

    doc_a = make_document(
        db_session,
        run,
        title="Group One Report A",
        normalized_title="group one report",
        status="published",
        document_type="report",
        region="Europe",
        language="en",
        quality_score=10.0,
        tags=["alpha"],
    )
    doc_b = make_document(
        db_session,
        run,
        title="Group One Report B",
        normalized_title="group one report",
        status="published",
        document_type="report",
        region="Europe",
        language="en",
        quality_score=20.0,
        tags=["alpha", "beta"],
    )
    doc_c = make_document(
        db_session,
        run,
        title="Group One Report C",
        normalized_title="group one report",
        status="draft",
        document_type="working_paper",
        region=None,
        language="fr",
        quality_score=30.0,
        tags=["beta"],
    )
    doc_d = make_document(
        db_session,
        run,
        title="Group Two Brief A",
        normalized_title="group two brief",
        status="archived",
        document_type="policy_brief",
        region="Asia",
        language="de",
        quality_score=40.0,
    )
    doc_e = make_document(
        db_session,
        run,
        title="Group Two Brief B",
        normalized_title="group two brief",
        status="published",
        document_type="report",
        region=None,
        language="en",
        quality_score=50.0,
        tags=["gamma"],
    )
    doc_f = make_document(
        db_session,
        run,
        title="Pending Score Doc",
        normalized_title="pending score doc",
        status="published",
        document_type="report",
        region="Europe",
        language="en",
    )

    doc_a.duplicate_group_id = doc_a.id
    doc_b.duplicate_group_id = doc_a.id
    doc_c.duplicate_group_id = doc_a.id
    doc_a.is_canonical = True
    doc_b.is_canonical = False
    doc_c.is_canonical = False
    doc_a.duplicate_confidence = 0.75
    doc_b.duplicate_confidence = 0.75
    doc_c.duplicate_confidence = 0.75

    doc_d.duplicate_group_id = doc_d.id
    doc_e.duplicate_group_id = doc_d.id
    doc_d.is_canonical = True
    doc_e.is_canonical = False
    doc_d.duplicate_confidence = 0.6
    doc_e.duplicate_confidence = 0.6

    db_session.add_all([doc_a, doc_b, doc_c, doc_d, doc_e])
    db_session.commit()

    return {"a": doc_a, "b": doc_b, "c": doc_c, "d": doc_d, "e": doc_e, "f": doc_f}


def test_get_stats_empty_database(client):
    response = client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 0
    assert body["by_status"] == {}
    assert body["by_document_type"] == {}
    assert body["by_region"] == {}
    assert body["by_language"] == {}
    assert body["top_tags"] == {}
    assert body["duplicate_stats"] == {
        "total_groups": 0,
        "total_duplicates": 0,
        "avg_group_size": 0.0,
        "top_groups": [],
    }
    assert body["quality_score_distribution"] == {
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "p25": None,
        "p75": None,
        "histogram": [0] * 10,
    }


def test_get_stats_aggregates_documents(client, db_session):
    seeded = _seed(db_session)

    response = client.get("/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 6
    assert body["by_status"] == {"published": 4, "draft": 1, "archived": 1}
    assert body["by_document_type"] == {
        "report": 4,
        "working_paper": 1,
        "policy_brief": 1,
    }
    assert body["by_region"] == {"Europe": 3, "unknown": 2, "Asia": 1}
    assert body["by_language"] == {"en": 4, "fr": 1, "de": 1}
    assert body["top_tags"] == {"alpha": 2, "beta": 2, "gamma": 1}

    assert body["duplicate_stats"] == {
        "total_groups": 2,
        "total_duplicates": 5,
        "avg_group_size": 2.5,
        "top_groups": [
            {
                "group_id": seeded["a"].id,
                "size": 3,
                "canonical_document_id": seeded["a"].id,
                "normalized_title": "group one report",
            },
            {
                "group_id": seeded["d"].id,
                "size": 2,
                "canonical_document_id": seeded["d"].id,
                "normalized_title": "group two brief",
            },
        ],
    }

    assert body["quality_score_distribution"] == {
        "min": 10.0,
        "max": 50.0,
        "mean": 30.0,
        "median": 30.0,
        "p25": 20.0,
        "p75": 40.0,
        "histogram": [0, 1, 1, 1, 1, 1, 0, 0, 0, 0],
    }


def test_get_stats_quality_score_distribution_single_score(client, db_session):
    run = make_run(db_session)
    make_document(db_session, run, title="Solo", normalized_title="solo", quality_score=42.5)

    response = client.get("/stats")

    body = response.json()
    distribution = body["quality_score_distribution"]
    assert distribution["min"] == 42.5
    assert distribution["max"] == 42.5
    assert distribution["mean"] == 42.5
    assert distribution["median"] == 42.5
    assert distribution["p25"] == 42.5
    assert distribution["p75"] == 42.5
    assert distribution["histogram"] == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0]


def test_get_stats_quality_score_histogram_clamps_top_bucket(client, db_session):
    run = make_run(db_session)
    make_document(
        db_session,
        run,
        title="Perfect",
        normalized_title="perfect",
        quality_score=100.0,
    )

    response = client.get("/stats")

    body = response.json()
    assert body["quality_score_distribution"]["histogram"] == [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
    ]
