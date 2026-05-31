"""
kakaorm + FastAPI — TODO リスト API
=====================================
シンプルな TODO リスト CRUD API のサンプル。

依存パッケージ:
    pip install fastapi uvicorn aiosqlite

起動:
    python examples/fastapi_todo.py

エンドポイント:
    GET    /todos          全件取得
    POST   /todos          新規作成
    GET    /todos/{id}     1件取得
    PATCH  /todos/{id}     部分更新
    DELETE /todos/{id}     削除
"""

import os
import sys
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kakaorm
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from kakaorm import BoolColumn, Model, StrColumn
from kakaorm.migration import Migrator
from pydantic import BaseModel  # リクエストボディ用スキーマにのみ使用

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ── モデル定義 ────────────────────────────────────────────────

class Todo(Model):
    title = StrColumn(nullable=False)
    description = StrColumn(nullable=True)
    completed = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "todo"


# ── リクエストボディ用 Pydantic スキーマ ─────────────────────
# レスポンスには Todo モデルをそのまま使用するため、
# リクエスト（入力バリデーション）用のスキーマのみ定義する。

class TodoCreate(BaseModel):
    title: str
    description: str | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    completed: bool | None = None


# ── アプリケーション ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = await kakaorm.connect("sqlite+aiosqlite:///./todo.db")
    migrator = Migrator(engine)
    plan = await migrator.plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    yield
    await engine.disconnect()


app = FastAPI(title="kakaorm TODO API", version="0.1.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── エンドポイント ────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/todos", response_model=list[Todo])
async def list_todos():
    """全 TODO を取得する。"""
    return await Todo.all()


@app.post("/todos", response_model=Todo, status_code=201)
async def create_todo(body: TodoCreate):
    """新しい TODO を作成する。"""
    return await Todo.create(**body.model_dump())


@app.get("/todos/{todo_id}", response_model=Todo)
async def get_todo(todo_id: int):
    """指定 ID の TODO を取得する。"""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


@app.patch("/todos/{todo_id}", response_model=Todo)
async def update_todo(todo_id: int, body: TodoUpdate):
    """TODO を部分更新する。"""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(todo, field, value)
    await todo.save()
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: int):
    """TODO を削除する。"""
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    await todo.delete()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "fastapi_todo:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=os.path.dirname(os.path.abspath(__file__)),
    )
