"""
Flask + KakaORM — TODO リスト (API + HTML UI)
=============================================

Flask 2.0 以降の async ビュー機能を使った REST API + HTML フロントエンドのサンプルです。

必要パッケージ:
    pip install "flask[async]" "kakaorm[aiosqlite]"

起動:
    python examples/flask_todo.py
    # または
    flask --app examples/flask_todo run

ブラウザで確認:
    http://localhost:5000/

API エンドポイント:
    GET    /              HTML UI
    GET    /todos         全件取得 (priority 降順)
    GET    /todos/<id>    1件取得
    POST   /todos         新規作成  {"title": "...", "priority": 0}
    PATCH  /todos/<id>    部分更新  {"title": "...", "done": true}
    DELETE /todos/<id>    削除
"""

import asyncio
import atexit

import kakaorm
from flask import Flask, abort, jsonify, render_template_string, request
from kakaorm import BoolColumn, IntColumn, Model, StrColumn
from kakaorm.migration import Migrator

app = Flask(__name__)

# ── HTML テンプレート ─────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>KakaORM TODO</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f0f2f5;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 2rem 1rem;
    }

    .container {
      width: 100%;
      max-width: 600px;
    }

    h1 {
      font-size: 1.8rem;
      font-weight: 700;
      color: #1a1a2e;
      margin-bottom: 1.5rem;
      display: flex;
      align-items: center;
      gap: .5rem;
    }

    /* ── 入力フォーム ── */
    .form-card {
      background: #fff;
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 2px 8px rgba(0,0,0,.08);
      margin-bottom: 1.5rem;
      display: flex;
      gap: .75rem;
      flex-wrap: wrap;
    }

    .form-card input[type="text"] {
      flex: 1;
      min-width: 160px;
      padding: .6rem .9rem;
      border: 1.5px solid #ddd;
      border-radius: 8px;
      font-size: 1rem;
      outline: none;
      transition: border-color .2s;
    }
    .form-card input[type="text"]:focus { border-color: #4f46e5; }

    .form-card select {
      padding: .6rem .75rem;
      border: 1.5px solid #ddd;
      border-radius: 8px;
      font-size: .9rem;
      background: #fff;
      cursor: pointer;
      outline: none;
    }

    .btn-add {
      padding: .6rem 1.2rem;
      background: #4f46e5;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background .2s;
      white-space: nowrap;
    }
    .btn-add:hover { background: #4338ca; }

    /* ── フィルタ ── */
    .filters {
      display: flex;
      gap: .5rem;
      margin-bottom: 1rem;
    }
    .filter-btn {
      padding: .35rem .9rem;
      border: 1.5px solid #ddd;
      border-radius: 20px;
      background: #fff;
      font-size: .85rem;
      cursor: pointer;
      transition: all .15s;
    }
    .filter-btn.active {
      background: #4f46e5;
      color: #fff;
      border-color: #4f46e5;
    }

    /* ── TODO リスト ── */
    #todo-list { display: flex; flex-direction: column; gap: .6rem; }

    .todo-item {
      background: #fff;
      border-radius: 10px;
      padding: .85rem 1rem;
      box-shadow: 0 1px 4px rgba(0,0,0,.07);
      display: flex;
      align-items: center;
      gap: .75rem;
      transition: opacity .2s;
    }
    .todo-item.done { opacity: .5; }

    .todo-item input[type="checkbox"] {
      width: 18px;
      height: 18px;
      accent-color: #4f46e5;
      cursor: pointer;
      flex-shrink: 0;
    }

    .todo-title {
      flex: 1;
      font-size: 1rem;
      word-break: break-all;
    }
    .todo-item.done .todo-title { text-decoration: line-through; color: #aaa; }

    .priority-badge {
      font-size: .75rem;
      font-weight: 600;
      padding: .2rem .55rem;
      border-radius: 12px;
      flex-shrink: 0;
    }
    .priority-high   { background: #fee2e2; color: #b91c1c; }
    .priority-medium { background: #fef3c7; color: #92400e; }
    .priority-low    { background: #e0e7ff; color: #3730a3; }

    .btn-delete {
      background: none;
      border: none;
      color: #ccc;
      font-size: 1.2rem;
      cursor: pointer;
      line-height: 1;
      padding: .1rem .3rem;
      border-radius: 4px;
      transition: color .15s;
      flex-shrink: 0;
    }
    .btn-delete:hover { color: #ef4444; }

    .empty-msg {
      text-align: center;
      color: #aaa;
      padding: 2rem;
      font-size: .95rem;
    }

    /* ── トースト通知 ── */
    #toast {
      position: fixed;
      bottom: 1.5rem;
      left: 50%;
      transform: translateX(-50%) translateY(60px);
      background: #1e1e2e;
      color: #fff;
      padding: .65rem 1.25rem;
      border-radius: 8px;
      font-size: .9rem;
      opacity: 0;
      transition: all .3s;
      pointer-events: none;
      z-index: 9999;
    }
    #toast.show {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>📝 KakaORM TODO</h1>

    <!-- 入力フォーム -->
    <div class="form-card">
      <input type="text" id="title-input" placeholder="新しいタスクを入力..." maxlength="200">
      <select id="priority-select">
        <option value="2">🔴 高</option>
        <option value="1">🟡 中</option>
        <option value="0" selected>🔵 低</option>
      </select>
      <button class="btn-add" onclick="addTodo()">追加</button>
    </div>

    <!-- フィルタ -->
    <div class="filters">
      <button class="filter-btn active" data-filter="all"   onclick="setFilter('all')">すべて</button>
      <button class="filter-btn"        data-filter="active" onclick="setFilter('active')">未完了</button>
      <button class="filter-btn"        data-filter="done"   onclick="setFilter('done')">完了</button>
    </div>

    <!-- TODO リスト -->
    <div id="todo-list"></div>
  </div>

  <div id="toast"></div>

  <script>
    let todos = [];
    let filter = 'all';

    // ── データ取得 ──────────────────────────────────────────────────────

    async function loadTodos() {
      const res = await fetch('/todos');
      todos = await res.json();
      render();
    }

    // ── CRUD ────────────────────────────────────────────────────────────

    async function addTodo() {
      const titleEl = document.getElementById('title-input');
      const title = titleEl.value.trim();
      if (!title) { toast('タイトルを入力してください'); return; }

      const priority = parseInt(document.getElementById('priority-select').value);
      const res = await fetch('/todos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, priority }),
      });
      if (!res.ok) { toast('作成に失敗しました'); return; }

      titleEl.value = '';
      await loadTodos();
      toast('追加しました');
    }

    async function toggleDone(id, done) {
      await fetch(`/todos/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done }),
      });
      await loadTodos();
    }

    async function deleteTodo(id) {
      await fetch(`/todos/${id}`, { method: 'DELETE' });
      await loadTodos();
      toast('削除しました');
    }

    // ── フィルタ ─────────────────────────────────────────────────────────

    function setFilter(f) {
      filter = f;
      document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === f);
      });
      render();
    }

    // ── 描画 ─────────────────────────────────────────────────────────────

    const PRIORITY_LABEL = { 2: ['高', 'high'], 1: ['中', 'medium'], 0: ['低', 'low'] };

    function render() {
      const list = document.getElementById('todo-list');

      const visible = todos.filter(t => {
        if (filter === 'active') return !t.done;
        if (filter === 'done')   return  t.done;
        return true;
      });

      if (visible.length === 0) {
        list.innerHTML = '<p class="empty-msg">タスクはありません 🎉</p>';
        return;
      }

      list.innerHTML = visible.map(t => {
        const [label, cls] = PRIORITY_LABEL[t.priority] ?? ['低', 'low'];
        return `
          <div class="todo-item ${t.done ? 'done' : ''}">
            <input type="checkbox" ${t.done ? 'checked' : ''}
                   onchange="toggleDone(${t.id}, this.checked)">
            <span class="todo-title">${escHtml(t.title)}</span>
            <span class="priority-badge priority-${cls}">${label}</span>
            <button class="btn-delete" onclick="deleteTodo(${t.id})" title="削除">×</button>
          </div>`;
      }).join('');
    }

    // ── ユーティリティ ────────────────────────────────────────────────────

    function escHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
              .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    let toastTimer;
    function toast(msg) {
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.classList.add('show');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
    }

    // Enter キーで追加
    document.getElementById('title-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') addTodo();
    });

    loadTodos();
  </script>
</body>
</html>"""


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


@app.get("/")
def index():
    """HTML UI を返す。"""
    return render_template_string(HTML)


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
