import pytest

from app import MAX_DESCRIPTION_LENGTH, MAX_TITLE_LENGTH, create_app


@pytest.fixture()
def client():
    """A fresh app (and therefore an empty in-memory store) for every test."""
    app = create_app({"TESTING": True})
    return app.test_client()


def add_task(client, title="Write tests", description=""):
    return client.post("/tasks", data={"title": title, "description": description})


# ---------- Homepage ----------

def test_homepage_loads_with_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"DevOps Task Manager" in response.data
    assert b"No tasks yet" in response.data


# ---------- Health ----------

def test_health_endpoint_returns_json_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "devops-task-manager"


# ---------- Create ----------

def test_create_task_appears_with_creation_info(client):
    response = add_task(client, "Build image", "Use the Dockerfile")
    assert response.status_code == 302

    page = client.get("/").data
    assert b"Build image" in page
    assert b"Use the Dockerfile" in page
    assert b"Created" in page
    assert b"UTC" in page


def test_counts_for_total_completed_pending(client):
    add_task(client, "One")
    add_task(client, "Two")
    add_task(client, "Three")
    client.post("/tasks/1/complete")

    counts = client.get("/api/tasks").get_json()["counts"]
    assert counts == {"total": 3, "completed": 1, "pending": 2}


# ---------- Complete ----------

def test_complete_task(client):
    add_task(client, "Run pytest")
    response = client.post("/tasks/1/complete")
    assert response.status_code == 302

    task = client.get("/api/tasks").get_json()["tasks"][0]
    assert task["completed"] is True
    assert task["completed_at"] is not None


def test_complete_missing_task_returns_404(client):
    assert client.post("/tasks/999/complete").status_code == 404


# ---------- Delete ----------

def test_delete_task(client):
    add_task(client, "Remove me")
    assert client.post("/tasks/1/delete").status_code == 302
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_delete_missing_task_returns_404(client):
    assert client.post("/tasks/999/delete").status_code == 404


# ---------- Invalid input ----------

@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_is_rejected(client, title):
    response = add_task(client, title)
    assert response.status_code == 400
    assert b"Enter a task title" in response.data
    assert client.get("/api/tasks").get_json()["tasks"] == []


def test_title_too_long_is_rejected(client):
    response = add_task(client, "x" * (MAX_TITLE_LENGTH + 1))
    assert response.status_code == 400


def test_description_too_long_is_rejected(client):
    response = add_task(client, "ok", "y" * (MAX_DESCRIPTION_LENGTH + 1))
    assert response.status_code == 400


def test_html_in_title_is_escaped(client):
    add_task(client, "<script>alert(1)</script>")
    page = client.get("/").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;" in page


def test_unknown_page_returns_404(client):
    assert client.get("/nope").status_code == 404


# ---------- JSON API ----------

def test_api_create_and_validation(client):
    ok = client.post("/api/tasks", json={"title": "API task"})
    assert ok.status_code == 201
    assert ok.get_json()["title"] == "API task"

    assert client.post("/api/tasks", json={"title": ""}).status_code == 400
    assert client.post("/api/tasks", json={"title": 123}).status_code == 400
    assert client.post("/api/tasks", data="not json", content_type="text/plain").status_code == 400


def test_api_complete_and_delete(client):
    client.post("/api/tasks", json={"title": "Task"})
    assert client.patch("/api/tasks/1/complete").get_json()["completed"] is True
    assert client.delete("/api/tasks/1").status_code == 200
    assert client.delete("/api/tasks/1").status_code == 404
    assert client.patch("/api/tasks/1/complete").status_code == 404
