from pathlib import Path

from app.models import Document, IngestionError, IngestionRun, RawDocument

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_input" / "mini.jsonl"


def _post_mini(client, **params):
    with open(FIXTURE_PATH, "rb") as f:
        return client.post(
            "/ingestions",
            files={"file": ("mini.jsonl", f, "application/x-ndjson")},
            params=params,
        )


def test_create_ingestion_runs_pipeline_in_background(client, db_session):
    response = _post_mini(client)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["source_file"] == "mini.jsonl"
    assert body["file_hash"]
    run_id = body["id"]

    run = db_session.get(IngestionRun, run_id)
    assert run.total_lines == 5
    assert run.raw_loaded_count == 2
    assert run.skipped_count == 3
    assert run.status == "completed"
    assert run.finished_at is not None
    assert Path(run.staged_path).exists()

    raw_docs = db_session.query(RawDocument).filter_by(ingestion_run_id=run_id).all()
    assert len(raw_docs) == 2
    assert {raw_doc.status for raw_doc in raw_docs} == {"normalized"}

    errors = db_session.query(IngestionError).filter_by(run_id=run_id).all()
    assert len(errors) == 3

    documents = db_session.query(Document).all()
    assert len(documents) == 2
    for document in documents:
        assert document.is_canonical is True
        assert document.quality_score is not None


def test_ingestion_run_writes_per_run_log_file(client, tmp_path):
    response = _post_mini(client)
    run_id = response.json()["id"]

    log_file = tmp_path / "logs" / f"ingestion_run_{run_id}.log"
    assert log_file.exists()

    contents = log_file.read_text()
    assert f"run {run_id}: stage 0 complete - total_lines=5 raw_loaded=2 skipped=3" in contents
    assert contents.count(" ERROR ") == 3
    assert f"run {run_id}: pipeline completed" in contents


def test_duplicate_ingestion_rejected_without_force(client, db_session):
    first = _post_mini(client)
    assert first.status_code == 201
    run_id = first.json()["id"]

    run = db_session.get(IngestionRun, run_id)
    run.status = "completed"
    db_session.commit()

    second = _post_mini(client)

    assert second.status_code == 409
    assert second.json()["detail"]["existing_run_id"] == run_id


def test_duplicate_ingestion_with_force_creates_new_run(client, db_session):
    first = _post_mini(client)
    run_id = first.json()["id"]

    run = db_session.get(IngestionRun, run_id)
    run.status = "completed"
    db_session.commit()

    second = _post_mini(client, force="true")

    assert second.status_code == 201
    assert second.json()["id"] != run_id


def test_list_ingestions_returns_runs_newest_first(client):
    first = _post_mini(client)
    second = _post_mini(client, force="true")

    response = client.get("/ingestions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [item["id"] for item in body["items"]] == [second.json()["id"], first.json()["id"]]


def test_get_ingestion_detail(client):
    response = _post_mini(client)
    run_id = response.json()["id"]

    detail = client.get(f"/ingestions/{run_id}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == run_id
    assert body["status"] == "completed"
    assert body["normalize_pending"] == 0
    assert body["dedup_pending"] == 0
    assert body["scoring_pending"] == 0
    assert body["error_count"] == 3
    assert len(body["sample_errors"]) == 3
    assert {error["error_category"] for error in body["sample_errors"]} == {
        "invalid_json",
        "not_object",
        "broken_stub",
    }


def test_get_ingestion_not_found(client):
    response = client.get("/ingestions/999")

    assert response.status_code == 404
