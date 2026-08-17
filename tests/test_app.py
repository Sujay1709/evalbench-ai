def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Replace prompt intuition with evidence" in response.data
