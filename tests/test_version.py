"""Test the /version endpoint used by the app footer."""


def test_version_endpoint_returns_commit_hash(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "commit" in data
    assert isinstance(data["commit"], str)
    assert data["commit"]  # non-empty
