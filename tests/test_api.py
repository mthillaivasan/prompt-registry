def _create_prompt(client, name="test-prompt", content="Hello {{name}}"):
    return client.post("/prompts", json={
        "name": name,
        "description": "A test prompt",
        "tags": ["greeting", "test"],
        "content": content,
    })


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_prompt(client):
    resp = _create_prompt(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-prompt"
    assert data["tags"] == ["greeting", "test"]
    assert data["latest_version"]["version"] == 1
    assert data["latest_version"]["content"] == "Hello {{name}}"


def test_create_duplicate_prompt(client):
    _create_prompt(client)
    resp = _create_prompt(client)
    assert resp.status_code == 409


def test_list_prompts(client):
    _create_prompt(client, name="prompt-a")
    _create_prompt(client, name="prompt-b")
    resp = client.get("/prompts")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_search_prompts(client):
    _create_prompt(client, name="greeting-prompt")
    _create_prompt(client, name="code-review")
    resp = client.get("/prompts", params={"search": "greeting"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "greeting-prompt"


def test_filter_by_tag(client):
    _create_prompt(client, name="tagged")
    resp = client.get("/prompts", params={"tag": "greeting"})
    assert len(resp.json()) == 1


def test_get_prompt_detail(client):
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    resp = client.get(f"/prompts/{prompt_id}")
    assert resp.status_code == 200
    assert len(resp.json()["versions"]) == 1


def test_get_prompt_not_found(client):
    resp = client.get("/prompts/999")
    assert resp.status_code == 404


def test_update_prompt(client):
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    resp = client.patch(f"/prompts/{prompt_id}", json={"description": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated"


def test_delete_prompt(client):
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    resp = client.delete(f"/prompts/{prompt_id}")
    assert resp.status_code == 204
    assert client.get(f"/prompts/{prompt_id}").status_code == 404


def test_add_version(client):
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    resp = client.post(f"/prompts/{prompt_id}/versions", json={
        "content": "Hello {{name}}, welcome!",
        "change_note": "Added welcome message",
    })
    assert resp.status_code == 201
    assert resp.json()["version"] == 2


def test_get_specific_version(client):
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    client.post(f"/prompts/{prompt_id}/versions", json={"content": "v2 content"})
    resp = client.get(f"/prompts/{prompt_id}/versions/1")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Hello {{name}}"
    resp2 = client.get(f"/prompts/{prompt_id}/versions/2")
    assert resp2.json()["content"] == "v2 content"
