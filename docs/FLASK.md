# KakaORM — Flask Integration Guide

[日本語](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.ja.md) | [← README](https://github.com/AyumuTakai/KakaORM/blob/main/README.md)

---

## Requirements & Installation

Flask 2.0+ supports async view functions natively. KakaORM's fully async API integrates with Flask using `asyncio.run()` for startup/shutdown and the `async def` view syntax.

```bash
# SQLite (development / testing)
pip install "flask[async]" "kakaorm[aiosqlite]"

# PostgreSQL (asyncpg)
pip install "flask[async]" "kakaorm[asyncpg]"

# PostgreSQL (psycopg3)
pip install "flask[async]" "kakaorm[psycopg3]" "psycopg[binary]"

# MySQL / MariaDB
pip install "flask[async]" "kakaorm[aiomysql]"
```

---

## Engine Lifecycle

Flask does not have a built-in async lifespan hook like FastAPI. The recommended pattern is to call `asyncio.run()` at module level for startup and register `atexit` for shutdown.

```python
import asyncio
import atexit
import kakaorm
from kakaorm.migration import Migrator

async def _startup() -> kakaorm.Engine:
    """Connect to the DB and bring the schema up to date."""
    engine = await kakaorm.connect("sqlite+aiosqlite:///./app.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    return engine

engine = asyncio.run(_startup())
atexit.register(lambda: asyncio.run(engine.disconnect()))
```

This runs synchronously before Flask accepts any requests, ensuring the engine is ready when the first request arrives. `atexit` handles cleanup when the process exits.

### Using .env (python-dotenv)

For production or multi-environment setups, load the database URL from an environment variable:

```bash
pip install python-dotenv
```

```python
# .env
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

async def _startup() -> kakaorm.Engine:
    engine = await kakaorm.connect(DATABASE_URL)
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    return engine

engine = asyncio.run(_startup())
atexit.register(lambda: asyncio.run(engine.disconnect()))
```

---

## Complete TODO API Example

The following is a complete, runnable TODO REST API based on `examples/flask_todo.py`.

```python
"""
Flask + KakaORM — TODO list API
================================

Requirements:
    pip install "flask[async]" "kakaorm[aiosqlite]"

Start:
    python examples/flask_todo.py
    # or
    flask --app examples/flask_todo run

Endpoints:
    GET    /todos              List all (ordered by priority desc)
    GET    /todos/<id>         Get one
    POST   /todos              Create  {"title": "...", "priority": 0}
    PATCH  /todos/<id>         Update  {"title": "...", "done": true}
    DELETE /todos/<id>         Delete
"""

import asyncio
import atexit

import kakaorm
from flask import Flask, abort, jsonify, request
from kakaorm import BoolColumn, IntColumn, Model, StrColumn
from kakaorm.migration import Migrator

app = Flask(__name__)

# ── Model ─────────────────────────────────────────────────────────────────────

class Todo(Model):
    title    = StrColumn(nullable=False)
    done     = BoolColumn(nullable=False, default=False)
    priority = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "todo"

# ── Engine lifecycle ──────────────────────────────────────────────────────────

async def _startup() -> kakaorm.Engine:
    """Connect to the DB and apply pending migrations."""
    engine = await kakaorm.connect("sqlite+aiosqlite:///./flask_todo.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    return engine

engine = asyncio.run(_startup())
atexit.register(lambda: asyncio.run(engine.disconnect()))

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/todos")
async def list_todos():
    """List all todos, ordered by priority descending."""
    todos = await Todo.all().order_by(Todo.priority.desc)
    return jsonify([t.model_dump() for t in todos])


@app.get("/todos/<int:todo_id>")
async def get_todo(todo_id: int):
    """Retrieve a single todo by ID."""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        abort(404, description=f"Todo {todo_id} not found")
    return jsonify(todo.model_dump())


@app.post("/todos")
async def create_todo():
    """Create a new todo.

    Request body (JSON):
        title    (str, required)
        priority (int, optional, default 0)
    """
    data = request.get_json(silent=True) or {}
    if not data.get("title"):
        abort(400, description="'title' is required")
    todo = await Todo.create(
        title=data["title"],
        priority=int(data.get("priority", 0)),
    )
    return jsonify(todo.model_dump()), 201


@app.patch("/todos/<int:todo_id>")
async def update_todo(todo_id: int):
    """Partially update a todo.

    Request body (JSON, all fields optional):
        title (str)
        done  (bool)
    """
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        abort(404, description=f"Todo {todo_id} not found")
    data = request.get_json(silent=True) or {}
    if "title" in data:
        todo.title = str(data["title"])
    if "done" in data:
        todo.done = bool(data["done"])
    await todo.save()
    return jsonify(todo.model_dump())


@app.delete("/todos/<int:todo_id>")
async def delete_todo(todo_id: int):
    """Delete a todo by ID."""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        abort(404, description=f"Todo {todo_id} not found")
    await todo.delete()
    return "", 204

# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
def handle_error(e):
    return jsonify(error=str(e.description)), e.code

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
```

---

## Error Handling

Flask's `abort()` raises an `HTTPException`. Register `@app.errorhandler` for each status code you want to return as JSON:

```python
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def handle_error(e):
    return jsonify(error=str(e.description)), e.code
```

For unhandled exceptions from KakaORM (e.g. `NotFound`), add a generic handler:

```python
from kakaorm.exceptions import NotFound

@app.errorhandler(NotFound)
def handle_not_found(e):
    return jsonify(error="Record not found"), 404
```

---

## Testing with pytest

Use `pytest` with `pytest-flask` for HTTP-level tests, and an in-memory SQLite engine for isolation.

```bash
pip install pytest pytest-flask "kakaorm[aiosqlite]"
```

```python
# tests/conftest.py
import asyncio
import pytest
import kakaorm
from kakaorm.migration import Migrator
from myapp import app, Todo  # import your Flask app and models

@pytest.fixture(scope="session")
def test_engine():
    async def _setup():
        engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
        plan = await Migrator(engine).plan([Todo])
        if not plan.is_empty():
            await plan.apply()
        return engine
    return asyncio.run(_setup())

@pytest.fixture
def client(test_engine):
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
```

```python
# tests/test_todos.py
def test_create_todo(client):
    resp = client.post("/todos", json={"title": "Buy milk"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["title"] == "Buy milk"
    assert data["done"] is False

def test_get_missing_todo(client):
    resp = client.get("/todos/9999")
    assert resp.status_code == 404

def test_update_todo(client):
    resp = client.post("/todos", json={"title": "Walk dog"})
    todo_id = resp.get_json()["id"]

    resp = client.patch(f"/todos/{todo_id}", json={"done": True})
    assert resp.status_code == 200
    assert resp.get_json()["done"] is True

def test_delete_todo(client):
    resp = client.post("/todos", json={"title": "Temp"})
    todo_id = resp.get_json()["id"]

    resp = client.delete(f"/todos/{todo_id}")
    assert resp.status_code == 204

    resp = client.get(f"/todos/{todo_id}")
    assert resp.status_code == 404
```

---

## Differences from FastAPI

| Aspect | FastAPI | Flask |
|--------|---------|-------|
| Engine lifecycle | `lifespan` context manager | `asyncio.run()` at module level + `atexit` |
| Response serialization | `response_model` (automatic) | `jsonify(obj.model_dump())` (manual) |
| Input validation | Pydantic `BaseModel` in function signature | `request.get_json()` + manual validation |
| OpenAPI / Swagger | Built-in at `/docs` | Requires extension (e.g. `flask-openapi3`) |
| Async support | Native throughout | Requires `flask[async]` extra |
| Error handling | `HTTPException` with `detail` | `abort()` + `@app.errorhandler` |

KakaORM's model methods (`create`, `all`, `where`, `save`, `delete`, etc.) work identically in both frameworks since they are pure async Python.
