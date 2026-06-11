import pytest

from app.models import RawDocument
from tests.factories import make_run


@pytest.mark.parametrize(
    "path", ["/processing/normalize", "/processing/duplicates", "/processing/scoring"]
)
def test_processing_endpoints_return_zero_when_queues_empty(client, path):
    response = client.post(path)

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "remaining": 0}


def test_processing_endpoint_accepts_batch_size(client, db_session):
    run = make_run(db_session)
    for line_number in range(1, 4):
        db_session.add(
            RawDocument(
                ingestion_run_id=run.id,
                line_number=line_number,
                raw_data={"title": f"Doc {line_number}"},
                status="pending",
            )
        )
    db_session.commit()

    response = client.post("/processing/normalize", params={"batch_size": 1})

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "remaining": 2}
