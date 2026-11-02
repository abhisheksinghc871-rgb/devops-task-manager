"""DevOps Task Manager - a small Flask app for practising Jenkins CI/CD.

Tasks are kept in memory, so the app runs in a single container with no
database. All tasks are lost when the process or container restarts.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 300
SERVICE_NAME = "devops-task-manager"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Task:
    id: int
    title: str
    description: str = ""
    completed: bool = False
    created_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskStore:
    """Thread-safe in-memory task storage."""

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def add(self, title: str, description: str = "") -> Task:
        with self._lock:
            task = Task(id=self._next_id, title=title, description=description)
            self._tasks[task.id] = task
            self._next_id += 1
            return task

    def all(self) -> list[Task]:
        """Return tasks, newest first."""
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: t.id, reverse=True)

    def complete(self, task_id: int) -> Optional[Task]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and not task.completed:
                task.completed = True
                task.completed_at = utc_now()
            return task

    def delete(self, task_id: int) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def counts(self) -> dict:
        with self._lock:
            total = len(self._tasks)
            done = sum(1 for t in self._tasks.values() if t.completed)
        return {"total": total, "completed": done, "pending": total - done}


def validate_task_input(title, description):
    """Return (clean_title, clean_description, error_message_or_None)."""
    if title is not None and not isinstance(title, str):
        return "", "", "Title must be text."
    if description is not None and not isinstance(description, str):
        return "", "", "Description must be text."

    title = (title or "").strip()
    description = (description or "").strip()

    if not title:
        return title, description, "Enter a task title."
    if len(title) > MAX_TITLE_LENGTH:
        return title, description, f"Title must be {MAX_TITLE_LENGTH} characters or fewer."
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return title, description, f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."
    return title, description, None


def create_app(config: Optional[dict] = None) -> Flask:
    app = Flask(__name__)
    if config:
        app.config.update(config)

    store = TaskStore()
    app.extensions["task_store"] = store

    @app.template_filter("display_time")
    def display_time(value: datetime) -> str:
        return value.strftime("%d %b %Y, %H:%M UTC")

    def render_index(error=None, form=None, status=200):
        return (
            render_template(
                "index.html",
                tasks=store.all(),
                counts=store.counts(),
                error=error,
                form=form or {},
                max_title=MAX_TITLE_LENGTH,
                max_description=MAX_DESCRIPTION_LENGTH,
            ),
            status,
        )

    # ---------- Web pages ----------

    @app.get("/")
    def index():
        return render_index()

    @app.post("/tasks")
    def add_task():
        title, description, error = validate_task_input(
            request.form.get("title"), request.form.get("description")
        )
        if error:
            return render_index(error, {"title": title, "description": description}, 400)
        store.add(title, description)
        return redirect(url_for("index"))

    @app.post("/tasks/<int:task_id>/complete")
    def complete_task(task_id: int):
        if store.complete(task_id) is None:
            return render_template("error.html", code=404, message="That task does not exist."), 404
        return redirect(url_for("index"))

    @app.post("/tasks/<int:task_id>/delete")
    def delete_task(task_id: int):
        if not store.delete(task_id):
            return render_template("error.html", code=404, message="That task does not exist."), 404
        return redirect(url_for("index"))

    # ---------- Health check ----------

    @app.get("/health")
    def health():
        return jsonify(
            status="ok",
            service=SERVICE_NAME,
            timestamp=utc_now().isoformat(),
            tasks=store.counts(),
        )

    # ---------- JSON API (handy for curl practice) ----------

    @app.get("/api/tasks")
    def api_list():
        return jsonify(tasks=[t.to_dict() for t in store.all()], counts=store.counts())

    @app.post("/api/tasks")
    def api_add():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Send a JSON object with a 'title' field."), 400
        title, description, error = validate_task_input(data.get("title"), data.get("description"))
        if error:
            return jsonify(error=error), 400
        return jsonify(store.add(title, description).to_dict()), 201

    @app.patch("/api/tasks/<int:task_id>/complete")
    def api_complete(task_id: int):
        task = store.complete(task_id)
        if task is None:
            return jsonify(error="Task not found."), 404
        return jsonify(task.to_dict())

    @app.delete("/api/tasks/<int:task_id>")
    def api_delete(task_id: int):
        if not store.delete(task_id):
            return jsonify(error="Task not found."), 404
        return jsonify(deleted=task_id)

    # ---------- Error handling ----------

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        if request.path.startswith("/api/") or request.path == "/health":
            return jsonify(error=exc.description or exc.name), exc.code
        message = "That page does not exist." if exc.code == 404 else (exc.description or exc.name)
        return render_template("error.html", code=exc.code, message=message), exc.code

    return app


app = create_app()

if __name__ == "__main__":
    # Development only. In Docker the app is served by Gunicorn.
    app.run(host="0.0.0.0", port=8000, debug=False)
