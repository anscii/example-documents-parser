import pytest


@pytest.mark.parametrize(
    "path", ["/processing/normalize", "/processing/duplicates", "/processing/scoring"]
)
def test_processing_endpoints_return_zero_when_queues_empty(client, path):
    response = client.post(path)

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "remaining": 0}


def test_processing_endpoint_accepts_batch_size(client):
    response = client.post("/processing/normalize", params={"batch_size": 5})

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "remaining": 0}
