"""
Flask + KakaORM — TODO リスト API
===================================

Flask 2.0 以降の async ビュー機能を使った REST API サンプルです。

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
    """DB に接続し、スキーマを最新状態に保つ。"""
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
