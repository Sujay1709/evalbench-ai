def test_liveness(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_readiness(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ready", "checks": {"database": "ok"}}
