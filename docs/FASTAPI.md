# FastAPI + KakaORM 統合ガイド

KakaORM は FastAPI との統合を最初から想定して設計されています。このガイドでは、セットアップからテスト、本番運用までの実装パターンを段階別に解説します。

## なぜ KakaORM + FastAPI か？

- **完全非同期** — `async/await` ベースで FastAPI のイベントループと完全統合
- **Pydantic v2 統合** — KakaORM モデルを FastAPI の `response_model` に直接指定可能
- **型安全** — IDE の自動補完が正しく動作し、スキーマ定義が不要
- **N+1 最適化** — `prefetch()` で関連データを一括取得（SQL クエリ最小化）
- **トランザクション管理** — マルチステップの ACID 操作を簡潔に

---

## 1. セットアップ（最小構成）

### インストール

**SQLite の場合（開発・テスト向け）：**
```bash
pip install fastapi uvicorn kakaorm aiosqlite
```

**PostgreSQL の場合（asyncpg）：**
```bash
pip install fastapi uvicorn kakaorm asyncpg
```

**PostgreSQL の場合（psycopg3）：**
```bash
pip install fastapi uvicorn kakaorm "psycopg[binary]" psycopg-pool
```

**MySQL / MariaDB の場合：**
```bash
pip install fastapi uvicorn kakaorm aiomysql
```

接続 URL の形式：

| DB | URL 形式 |
|---|---|
| SQLite (ファイル) | `sqlite+aiosqlite:///./app.db` |
| SQLite (インメモリ) | `sqlite+aiosqlite:///:memory:` |
| PostgreSQL (asyncpg) | `postgresql+asyncpg://user:password@localhost/dbname` |
| PostgreSQL (psycopg3) | `postgresql+psycopg3://user:password@localhost/dbname` |
| MySQL / MariaDB | `mysql+aiomysql://user:password@localhost:3306/dbname` |

### モデル定義

```python
# models.py
from kakaorm import Model, StrColumn, BoolColumn, IntColumn, ForeignKey

class User(Model):
    name  = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    
    class Meta:
        table_name = "user"

class Post(Model):
    title    = StrColumn(nullable=False)
    content  = StrColumn(nullable=True)
    published = BoolColumn(default=False)
    user_id  = ForeignKey(User, nullable=False)
    
    class Meta:
        table_name = "post"
```

### FastAPI アプリケーション（基本形）

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
import kakaorm
from kakaorm.migration import Migrator
from models import User, Post

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Engine 初期化 + マイグレーション
    engine = await kakaorm.connect("sqlite+aiosqlite:///./app.db")
    plan = await Migrator(engine).plan([User, Post])
    if not plan.is_empty():
        await plan.apply()
    
    app.state.engine = engine
    
    yield
    
    # Shutdown: Engine 終了
    await engine.disconnect()

app = FastAPI(lifespan=lifespan)

# Engine は app.state.engine で取得可能
```

起動：
```bash
uvicorn main:app --reload
# http://localhost:8000/docs で Swagger UI を確認
```

---

## 2. 基本パターン（CRUD API）

### GET 全件取得

```python
@app.get("/users", response_model=list[User])
async def list_users():
    return await User.all()
```

**実行:**
```bash
curl http://localhost:8000/users
# [
#   {"id": 1, "name": "Alice", "email": "alice@example.com"},
#   {"id": 2, "name": "Bob", "email": "bob@example.com"}
# ]
```

### GET 単件取得

```python
from fastapi import HTTPException

@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    user = await User.get_or_none(User.id == user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### POST 新規作成

```python
from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    email: str

@app.post("/users", response_model=User, status_code=201)
async def create_user(body: UserCreate):
    # Pydantic → dict → KakaORM
    user = await User.create(**body.model_dump())
    return user
```

**実行:**
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Charlie", "email": "charlie@example.com"}'
# {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
```

### PATCH 更新

```python
class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None

@app.patch("/users/{user_id}", response_model=User)
async def update_user(user_id: int, body: UserUpdate):
    user = await User.get_or_none(User.id == user_id)
    if user is None:
        raise HTTPException(status_code=404)
    
    # 与えられたフィールドのみ更新
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await user.save()
    return user
```

### DELETE 削除

```python
@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int):
    user = await User.get_or_none(User.id == user_id)
    if user is None:
        raise HTTPException(status_code=404)
    await user.delete()
```

---

## 3. Pydantic 統合の詳細

### response_model の活用

KakaORM モデルは Pydantic v2 プロトコルを実装しているため、`response_model` に直接指定可能です：

```python
@app.get("/users", response_model=list[User])  # ✅ KakaORM モデル直接指定
async def list_users():
    return await User.all()
```

Swagger UI は自動的に JSON スキーマを生成します。

### model_dump（シリアライズ）

```python
user = await User.get(User.id == 1)

# 全フィールド
user.model_dump()
# {"id": 1, "name": "Alice", "email": "alice@example.com"}

# None を除外
user.model_dump(exclude_none=True)

# 特定フィールドを除外
user.model_dump(exclude={"email"})
# {"id": 1, "name": "Alice"}
```

### model_validate（デシリアライズ）

```python
# dict から
data = {"name": "Alice", "email": "alice@example.com"}
user = User.model_validate(data)

# 別インスタンスから
other_user = await User.get(User.id == 1)
copied = User.model_validate(other_user)
```

---

## 4. リレーション & Eager Loading（N+1 回避）

### リレーション定義

```python
from kakaorm import belongs_to, has_many

class User(Model):
    name = StrColumn(nullable=False)
    
    # 逆参照：ユーザーの投稿一覧
    posts = has_many(Post, foreign_key="user_id")
    
    class Meta:
        table_name = "user"

class Post(Model):
    title = StrColumn(nullable=False)
    user_id = ForeignKey(User, nullable=False)
    
    # 順参照：投稿の著者
    author = belongs_to(User, foreign_key="user_id")
    
    class Meta:
        table_name = "post"
```

### N+1 問題（非効率な例）

```python
@app.get("/users-with-posts", response_model=list[User])
async def list_users_with_posts():
    users = await User.all()  # SQL: 1 query
    
    # ⚠️ この for ループは各ユーザーに対して追加クエリを実行
    for user in users:
        posts = await user.posts  # SQL: N queries (N = user count)
    
    return users
    # 合計: N+1 queries（非常に非効率）
```

### prefetch で解決（効率的な例）

```python
@app.get("/users-with-posts", response_model=list[User])
async def list_users_with_posts():
    # prefetch で関連データを一括取得
    users = await User.all().prefetch("posts")
    # SQL: 2 queries (users + posts)
    
    for user in users:
        posts = await user.posts  # キャッシュから取得（追加クエリなし）
    
    return users
```

**パフォーマンス比較：**
| ケース | ユーザー数 | SQL クエリ数 |
|--------|-----------|------------|
| prefetch なし | 10 | 11 (1 + 10) |
| prefetch なし | 100 | 101 (1 + 100) |
| prefetch あり | 10 | 2 |
| prefetch あり | 100 | 2 |

### 複数リレーションのプリフェッチ

```python
# User → posts → comments という 3 階層のリレーション
users = await (
    User.all()
    .prefetch("posts", "comments")  # 複数リレーション
)

for user in users:
    posts = await user.posts        # キャッシュ
    comments = await user.comments  # キャッシュ
```

---

## 5. ページング & フィルタリング

### Offset ベースページング

```python
from fastapi import Query

@app.get("/posts")
async def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    skip = (page - 1) * limit
    
    total = await Post.count()
    posts = await (
        Post.all()
        .offset(skip)
        .limit(limit)
        .execute()
    )
    
    return {
        "items": posts,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }
```

**実行:**
```bash
curl "http://localhost:8000/posts?page=2&limit=10"
```

### フィルタリング（複数条件）

```python
@app.get("/posts/search")
async def search_posts(
    title: str | None = None,
    published: bool | None = None,
    user_id: int | None = None,
):
    query = Post.all()
    
    if title:
        query = query.where(Post.title.icontains(title))  # LIKE 検索
    
    if published is not None:
        query = query.where(Post.published == published)
    
    if user_id:
        query = query.where(Post.user_id == user_id)
    
    return await query.execute()
```

**実行:**
```bash
curl "http://localhost:8000/posts/search?title=python&published=true"
```

### ソート（複数列）

```python
@app.get("/posts/sorted")
async def sorted_posts(
    sort: str = Query("id"),  # "id,-created_at,title"
):
    query = Post.all()
    
    for field in sort.split(","):
        if field.startswith("-"):
            col = getattr(Post, field[1:])
            query = query.order_by(col.desc)
        else:
            col = getattr(Post, field)
            query = query.order_by(col.asc)
    
    return await query.execute()
```

**実行:**
```bash
curl "http://localhost:8000/posts/sorted?sort=-created_at,title"
```

---

## 6. エラーハンドリング

### KakaORM 例外の処理

```python
from fastapi import HTTPException

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    try:
        user = await User.get(User.id == user_id)
        return user
    except User.NotFound:
        raise HTTPException(status_code=404, detail="User not found")
    except User.MultipleResults:
        # データベース整合性エラー
        raise HTTPException(status_code=500, detail="Database error")
```

### Pydantic バリデーションエラー

FastAPI は自動的に Pydantic バリデーションエラーを `422 Unprocessable Entity` に変換します：

```python
class UserCreate(BaseModel):
    name: str
    email: str

@app.post("/users", response_model=User)
async def create_user(body: UserCreate):
    # body.email が無効形式の場合、自動的に 422 を返す
    user = await User.create(**body.model_dump())
    return user
```

**実行（エラー）:**
```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "invalid-email"}'
# 422 Unprocessable Entity
```

### カスタムエラーハンドラー

```python
from fastapi.responses import JSONResponse

@app.exception_handler(User.NotFound)
async def user_not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "User not found", "error_code": "USER_NOT_FOUND"},
    )
```

---

## 7. トランザクション管理

### 単一エンドポイント内のトランザクション

```python
@app.post("/users/with-post")
async def create_user_with_post(
    user_data: UserCreate,
    post_data: dict,
):
    engine = app.state.engine
    
    async with engine.transaction():
        # トランザクション内でのすべての操作
        user = await User.create(**user_data.model_dump())
        post = await Post.create(
            user_id=user.id,
            **post_data
        )
        
        return {
            "user": user.model_dump(),
            "post": post.model_dump(),
        }
        # トランザクション終了：自動 COMMIT
        # 例外発生時は自動 ROLLBACK
```

### トランザクション内での例外処理

```python
@app.post("/transfer")
async def transfer_credits(
    from_user_id: int,
    to_user_id: int,
    amount: int,
):
    engine = app.state.engine
    
    try:
        async with engine.transaction():
            from_user = await User.get(User.id == from_user_id)
            to_user = await User.get(User.id == to_user_id)
            
            if from_user.credits < amount:
                raise ValueError("Insufficient credits")
            
            from_user.credits -= amount
            to_user.credits += amount
            
            await from_user.save()
            await to_user.save()
            
            return {"status": "ok"}
    except ValueError as e:
        # トランザクション自動 ROLLBACK
        raise HTTPException(status_code=400, detail=str(e))
```

---

## 8. テスト戦略

### 最小構成テスト（pytest + httpx）

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
import kakaorm
from fastapi.testclient import TestClient
from main import app
from models import User, Post

@pytest.fixture
async def test_engine():
    """In-memory SQLite for testing"""
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    from kakaorm.migration import Migrator
    plan = await Migrator(engine).plan([User, Post])
    if not plan.is_empty():
        await plan.apply()
    
    yield engine
    
    await engine.disconnect()

@pytest.fixture
def client(test_engine):
    """FastAPI TestClient"""
    app.state.engine = test_engine
    return TestClient(app)
```

### API エンドポイントのテスト

```python
# tests/test_api.py
def test_list_users(client):
    response = client.get("/users")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_user(client):
    response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice"
    assert data["id"] is not None

def test_get_user_404(client):
    response = client.get("/users/999")
    assert response.status_code == 404

def test_update_user(client):
    # Setup
    create_response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    user_id = create_response.json()["id"]
    
    # Update
    response = client.patch(
        f"/users/{user_id}",
        json={"name": "Alice Updated"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Alice Updated"

def test_delete_user(client):
    # Setup
    create_response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    user_id = create_response.json()["id"]
    
    # Delete
    response = client.delete(f"/users/{user_id}")
    assert response.status_code == 204
    
    # Verify deleted
    get_response = client.get(f"/users/{user_id}")
    assert get_response.status_code == 404
```

### リレーション + Prefetch のテスト

```python
def test_list_users_with_posts_prefetch(client):
    # Setup: User + Post を作成
    user_response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    user_id = user_response.json()["id"]
    
    post_response = client.post(
        "/posts",
        json={
            "title": "Test Post",
            "user_id": user_id
        }
    )
    
    # Test: prefetch で関連データ取得
    response = client.get("/users-with-posts")
    assert response.status_code == 200
    users = response.json()
    
    assert len(users) == 1
    assert users[0]["posts"] is not None  # prefetch されている
```

---

## 9. 本番運用

### ロギング設定

```python
import logging
from fastapi.middleware import Middleware
from fastapi.middleware.base import BaseHTTPMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kakaorm")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import time
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            f"{request.method} {request.url.path} - "
            f"status={response.status_code} duration={duration:.2f}s"
        )
        return response

app = FastAPI(
    middleware=[Middleware(LoggingMiddleware)],
    lifespan=lifespan,
)
```

### 接続プーリング（PostgreSQL）

```python
import asyncpg

async def lifespan(app: FastAPI):
    # 接続プーリング設定
    engine = await kakaorm.connect(
        "postgresql+asyncpg://user:password@localhost/dbname",
        min_size=5,    # 最小接続数
        max_size=20,   # 最大接続数
    )
    
    app.state.engine = engine
    
    yield
    
    await engine.disconnect()
```

### マイグレーション管理（本番）

```bash
# 開発環境でマイグレーション生成
kakaorm makemigrations models.py --name add_user_bio

# マイグレーションファイルをバージョン管理
git add migrations/
git commit -m "Add user bio migration"

# 本番環境でマイグレーション適用
kakaorm migrate --db postgresql+asyncpg://prod-server/db
```

---

## 10. FAQ & トラブルシューティング

### Q1: Pydantic モデルと KakaORM モデルの使い分けは？

**A:** 
- **リクエスト:** Pydantic BaseModel（入力バリデーション）
- **レスポンス:** KakaORM Model（自動シリアライズ）

```python
# リクエスト
class UserCreate(BaseModel):
    name: str
    email: str

# レスポンス
@app.post("/users", response_model=User)  # KakaORM Model
async def create_user(body: UserCreate):  # Pydantic BaseModel
    user = await User.create(**body.model_dump())
    return user
```

### Q2: N+1 問題を自動検出できる？

**A:** 明示的な検出機能はありませんが、SQL ログを有効化して確認できます：

```python
import logging
logging.getLogger("sqlalchemy").setLevel(logging.DEBUG)

# または kakaorm のログレベル調整
logging.getLogger("kakaorm").setLevel(logging.DEBUG)
```

### Q3: トランザクション内でのエラーハンドリングは？

**A:** コンテキストマネージャで自動的にロールバック：

```python
async with engine.transaction():
    user = await User.create(...)
    raise Exception("Something wrong")  # 自動 ROLLBACK
```

### Q4: 複数エンジン（複数 DB）を使いたい場合は？

**A:** 各 engine を app.state に保存：

```python
app.state.engine_primary = await kakaorm.connect("postgresql://...")
app.state.engine_secondary = await kakaorm.connect("postgresql://...")

@app.get("/data")
async def get_data():
    # primary DB から取得
    data = await Model.all()  # engine_primary を使用
    return data
```

---

## サンプルコード

完全な実装例は `examples/` ディレクトリを参照してください：

- `fastapi_advanced.py` — 依存性注入、複数モデル、エラー処理
- `fastapi_pagination.py` — ページング & フィルタリング
- `fastapi_testing.py` — テスト戦略

```bash
# 実行
python examples/fastapi_advanced.py
# http://localhost:8000/docs
```

---

## 参考資料

- [FastAPI 公式ドキュメント](https://fastapi.tiangolo.com)
- [Pydantic v2](https://docs.pydantic.dev)
- [KakaORM README](../README.md)
