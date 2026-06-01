# KakaORM — Flask 統合ガイド

[English](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.md) | [← README](https://github.com/AyumuTakai/KakaORM/blob/main/README.ja.md)

---

## 必要パッケージとインストール

Flask 2.0 以降は async ビュー関数をネイティブでサポートしています。KakaORM の完全非同期 API は、起動/終了に `asyncio.run()` を使い、`async def` ビュー構文で Flask と連携します。

```bash
# SQLite (開発・テスト向け)
pip install "flask[async]" "kakaorm[aiosqlite]"

# PostgreSQL (asyncpg)
pip install "flask[async]" "kakaorm[asyncpg]"

# PostgreSQL (psycopg3)
pip install "flask[async]" "kakaorm[psycopg3]" "psycopg[binary]"

# MySQL / MariaDB
pip install "flask[async]" "kakaorm[aiomysql]"
```

---

## エンジンのライフサイクル

Flask には FastAPI のような async lifespan フックがありません。推奨パターンは、起動時にモジュールレベルで `asyncio.run()` を呼び出し、終了時には `atexit` を登録する方法です。

```python
import asyncio
import atexit
import kakaorm
from kakaorm.migration import Migrator

async def _startup() -> kakaorm.Engine:
    """DB に接続し、スキーマを最新状態に保つ。"""
    engine = await kakaorm.connect("sqlite+aiosqlite:///./app.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    return engine

engine = asyncio.run(_startup())
atexit.register(lambda: asyncio.run(engine.disconnect()))
```

これは Flask がリクエストを受け付ける前に同期的に実行されるため、最初のリクエスト時にエンジンが確実に準備済みになります。`atexit` はプロセス終了時のクリーンアップを担います。

### .env を使った接続設定（python-dotenv）

本番環境や複数環境に対応するため、データベース URL を環境変数から読み込む方法が便利です。

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

## TODO API 完全実装例

以下は `examples/flask_todo.py` をベースにした、実際に動作する TODO REST API の完全なコードです。

```python
"""
Flask + KakaORM — TODO リスト API
===================================

必要パッケージ:
    pip install "flask[async]" "kakaorm[aiosqlite]"

起動:
    python examples/flask_todo.py
    # または
    flask --app examples/flask_todo run

エンドポイント:
    GET    /todos              全件取得 (priority 降順)
    GET    /todos/<id>         1件取得
    POST   /todos              新規作成  {"title": "...", "priority": 0}
    PATCH  /todos/<id>         部分更新  {"title": "...", "done": true}
    DELETE /todos/<id>         削除
"""

import asyncio
import atexit

import kakaorm
from flask import Flask, abort, jsonify, request
from kakaorm import BoolColumn, IntColumn, Model, StrColumn
from kakaorm.migration import Migrator

app = Flask(__name__)

# ── モデル定義 ────────────────────────────────────────────────────────────────

class Todo(Model):
    title    = StrColumn(nullable=False)
    done     = BoolColumn(nullable=False, default=False)
    priority = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "todo"

# ── エンジン初期化（アプリ起動時に 1 回） ────────────────────────────────────

async def _startup() -> kakaorm.Engine:
    """DB に接続し、未適用マイグレーションを適用する。"""
    engine = await kakaorm.connect("sqlite+aiosqlite:///./flask_todo.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    return engine

engine = asyncio.run(_startup())
atexit.register(lambda: asyncio.run(engine.disconnect()))

# ── ルート ────────────────────────────────────────────────────────────────────

@app.get("/todos")
async def list_todos():
    """全件取得 (priority 降順)。"""
    todos = await Todo.all().order_by(Todo.priority.desc)
    return jsonify([t.model_dump() for t in todos])


@app.get("/todos/<int:todo_id>")
async def get_todo(todo_id: int):
    """指定 ID の TODO を取得する。"""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        abort(404, description=f"Todo {todo_id} not found")
    return jsonify(todo.model_dump())


@app.post("/todos")
async def create_todo():
    """新規 TODO を作成する。

    リクエストボディ (JSON):
        title    (str, 必須)
        priority (int, 省略可, デフォルト 0)
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
    """TODO を部分更新する。

    リクエストボディ (JSON, すべて省略可):
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
    """指定 ID の TODO を削除する。"""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        abort(404, description=f"Todo {todo_id} not found")
    await todo.delete()
    return "", 204

# ── エラーハンドラ ────────────────────────────────────────────────────────────

@app.errorhandler(400)
@app.errorhandler(404)
def handle_error(e):
    return jsonify(error=str(e.description)), e.code

# ── 起動 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
```

---

## エラーハンドリング

Flask の `abort()` は `HTTPException` を発生させます。JSON レスポンスとして返したいステータスコードに対して `@app.errorhandler` を登録してください。

```python
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def handle_error(e):
    return jsonify(error=str(e.description)), e.code
```

KakaORM からの未処理例外（例: `NotFound`）に対応するには、汎用ハンドラを追加します。

```python
from kakaorm.exceptions import NotFound

@app.errorhandler(NotFound)
def handle_not_found(e):
    return jsonify(error="Record not found"), 404
```

---

## pytest でのテスト

`pytest` と `pytest-flask` を使い、分離のためにインメモリ SQLite エンジンを使用します。

```bash
pip install pytest pytest-flask "kakaorm[aiosqlite]"
```

```python
# tests/conftest.py
import asyncio
import pytest
import kakaorm
from kakaorm.migration import Migrator
from myapp import app, Todo  # Flask アプリとモデルをインポート

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
    resp = client.post("/todos", json={"title": "牛乳を買う"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["title"] == "牛乳を買う"
    assert data["done"] is False

def test_get_missing_todo(client):
    resp = client.get("/todos/9999")
    assert resp.status_code == 404

def test_update_todo(client):
    resp = client.post("/todos", json={"title": "犬の散歩"})
    todo_id = resp.get_json()["id"]

    resp = client.patch(f"/todos/{todo_id}", json={"done": True})
    assert resp.status_code == 200
    assert resp.get_json()["done"] is True

def test_delete_todo(client):
    resp = client.post("/todos", json={"title": "一時タスク"})
    todo_id = resp.get_json()["id"]

    resp = client.delete(f"/todos/{todo_id}")
    assert resp.status_code == 204

    resp = client.get(f"/todos/{todo_id}")
    assert resp.status_code == 404
```

---

## FastAPI との違い

| 観点 | FastAPI | Flask |
|------|---------|-------|
| エンジンライフサイクル | `lifespan` コンテキストマネージャ | モジュールレベルの `asyncio.run()` + `atexit` |
| レスポンスのシリアライズ | `response_model`（自動） | `jsonify(obj.model_dump())`（手動） |
| 入力バリデーション | 関数シグネチャの Pydantic `BaseModel` | `request.get_json()` + 手動バリデーション |
| OpenAPI / Swagger | `/docs` に組み込み | 拡張が必要（例: `flask-openapi3`） |
| 非同期サポート | 標準で対応 | `flask[async]` extra が必要 |
| エラーハンドリング | `detail` 付き `HTTPException` | `abort()` + `@app.errorhandler` |

KakaORM のモデルメソッド（`create`、`all`、`where`、`save`、`delete` など）はすべてピュアな非同期 Python のため、どちらのフレームワークでも同一の書き方で動作します。
