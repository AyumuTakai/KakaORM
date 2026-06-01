"""
FastAPI + KakaORM テスト戦略
============================

実装パターン:
- pytest + httpx による統合テスト
- in-memory SQLite
- Fixture パターン
- API エンドポイント テスト
- 関連データ（prefetch）のテスト

実行:
    pip install fastapi uvicorn "kakaorm[aiosqlite]" pytest pytest-asyncio httpx2
    pytest examples/fastapi_testing.py -v
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from contextlib import asynccontextmanager

import kakaorm
from kakaorm import Model, StrColumn, IntColumn, ForeignKey, has_many, belongs_to
from kakaorm.migration import Migrator
from fastapi import FastAPI, HTTPException, Depends
from typing import Annotated


# ============================================================================
# テスト用モデル
# ============================================================================

class User(Model):
    """ユーザーモデル"""
    name = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)

    posts = has_many("Post", foreign_key="user_id")

    class Meta:
        table_name = "user"


class Post(Model):
    """投稿モデル"""
    title = StrColumn(nullable=False)
    content = StrColumn(nullable=True)
    user_id = ForeignKey(User, nullable=False)

    author = belongs_to(User, foreign_key="user_id")

    class Meta:
        table_name = "post"


# ============================================================================
# テスト用リクエスト/レスポンススキーマ
# ============================================================================

class UserCreate(BaseModel):
    name: str
    email: str


class PostCreate(BaseModel):
    title: str
    content: str | None = None
    user_id: int


# ============================================================================
# テスト用 FastAPI アプリケーション
# ============================================================================

def create_app(engine):
    """テスト用アプリケーション生成"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine
        yield
        # テスト後のクリーンアップは pytest が管理

    app = FastAPI(lifespan=lifespan)

    async def get_engine():
        return app.state.engine

    # ============================================================================
    # ユーザーエンドポイント
    # ============================================================================

    @app.get("/users", response_model=list[User])
    async def list_users(engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        return await User.all()

    @app.get("/users/{user_id}", response_model=User)
    async def get_user(user_id: int, engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        user = await User.get_or_none(User.id == user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.post("/users", response_model=User, status_code=201)
    async def create_user(body: UserCreate, engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        try:
            return await User.create(**body.model_dump())
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=400, detail="Email already exists")
            raise HTTPException(status_code=400, detail=str(e))

    @app.patch("/users/{user_id}", response_model=User)
    async def update_user(user_id: int, body: UserCreate, engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        user = await User.get_or_none(User.id == user_id)
        if user is None:
            raise HTTPException(status_code=404)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(user, field, value)
        await user.save()
        return user

    @app.delete("/users/{user_id}", status_code=204)
    async def delete_user(user_id: int, engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        user = await User.get_or_none(User.id == user_id)
        if user is None:
            raise HTTPException(status_code=404)
        await user.delete()

    # ============================================================================
    # 投稿エンドポイント
    # ============================================================================

    @app.get("/posts", response_model=list[Post])
    async def list_posts(engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        return await Post.all().prefetch("author").execute()

    @app.post("/posts", response_model=Post, status_code=201)
    async def create_post(body: PostCreate, engine: Annotated[kakaorm.Engine, Depends(get_engine)] = None):
        return await Post.create(**body.model_dump())

    return app


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture
async def test_engine():
    """In-memory SQLite engine for testing"""
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")

    # マイグレーション実行
    plan = await Migrator(engine).plan([User, Post])
    if not plan.is_empty():
        await plan.apply()

    yield engine

    # クリーンアップ
    await engine.disconnect()


@pytest.fixture
def app():
    """FastAPI アプリケーション（同期版）"""
    import asyncio

    async def _setup():
        engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
        plan = await Migrator(engine).plan([User, Post])
        if not plan.is_empty():
            await plan.apply()
        return engine

    loop = asyncio.new_event_loop()
    engine = loop.run_until_complete(_setup())
    application = create_app(engine)

    yield application, loop, engine

    loop.run_until_complete(engine.disconnect())
    loop.close()


@pytest.fixture
def client(app):
    """FastAPI TestClient（lifespan 起動込み）"""
    application, _loop, _engine = app
    with TestClient(application) as c:
        yield c


# ============================================================================
# テストケース
# ============================================================================

class TestUserAPI:
    """ユーザー API のテスト"""

    def test_list_users_empty(self, client):
        """空の場合"""
        response = client.get("/users")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_user(self, client):
        """ユーザー作成"""
        response = client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Alice"
        assert data["email"] == "alice@example.com"
        assert data["id"] is not None

    def test_create_user_duplicate_email(self, client):
        """メールアドレス重複エラー"""
        # 1つ目の作成
        client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )

        # 2つ目は失敗
        response = client.post(
            "/users",
            json={"name": "Alice 2", "email": "alice@example.com"}
        )
        assert response.status_code == 400
        assert "Email already exists" in response.json()["detail"]

    def test_list_users_with_data(self, client):
        """ユーザー一覧（データあり）"""
        # Setup
        client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        client.post(
            "/users",
            json={"name": "Bob", "email": "bob@example.com"}
        )

        # Test
        response = client.get("/users")
        assert response.status_code == 200
        users = response.json()
        assert len(users) == 2
        assert users[0]["name"] == "Alice"
        assert users[1]["name"] == "Bob"

    def test_get_user(self, client):
        """ユーザー取得"""
        # Setup
        create_response = client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        user_id = create_response.json()["id"]

        # Test
        response = client.get(f"/users/{user_id}")
        assert response.status_code == 200
        user = response.json()
        assert user["name"] == "Alice"
        assert user["id"] == user_id

    def test_get_user_not_found(self, client):
        """ユーザー取得（404）"""
        response = client.get("/users/999")
        assert response.status_code == 404

    def test_update_user(self, client):
        """ユーザー更新"""
        # Setup
        create_response = client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        user_id = create_response.json()["id"]

        # Update
        response = client.patch(
            f"/users/{user_id}",
            json={"name": "Alice Updated", "email": "alice@example.com"}
        )
        assert response.status_code == 200
        user = response.json()
        assert user["name"] == "Alice Updated"

    def test_delete_user(self, client):
        """ユーザー削除"""
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


class TestPostAPI:
    """投稿 API のテスト"""

    def test_create_post(self, client):
        """投稿作成"""
        # Setup: ユーザー作成
        user_response = client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        user_id = user_response.json()["id"]

        # Test: 投稿作成
        response = client.post(
            "/posts",
            json={
                "title": "Test Post",
                "content": "Test content",
                "user_id": user_id
            }
        )
        assert response.status_code == 201
        post = response.json()
        assert post["title"] == "Test Post"
        assert post["user_id"] == user_id

    def test_list_posts_with_author_prefetch(self, client):
        """投稿一覧（著者情報含む、prefetch テスト）"""
        # Setup
        user_response = client.post(
            "/users",
            json={"name": "Alice", "email": "alice@example.com"}
        )
        user_id = user_response.json()["id"]

        client.post(
            "/posts",
            json={
                "title": "Post 1",
                "content": "...",
                "user_id": user_id
            }
        )
        client.post(
            "/posts",
            json={
                "title": "Post 2",
                "content": "...",
                "user_id": user_id
            }
        )

        # Test: prefetch で著者情報が含まれる
        response = client.get("/posts")
        assert response.status_code == 200
        posts = response.json()
        assert len(posts) == 2
        # prefetch されているので author_id が含まれる
        assert posts[0]["user_id"] == user_id


class TestTransactionAPI:
    """トランザクション関連のテスト"""

    def test_concurrent_user_creation(self, client):
        """並行ユーザー作成（通常は OK）"""
        responses = []
        for i in range(5):
            response = client.post(
                "/users",
                json={"name": f"User {i}", "email": f"user{i}@example.com"}
            )
            responses.append(response)

        # 全て成功
        assert all(r.status_code == 201 for r in responses)

        # 確認
        list_response = client.get("/users")
        assert len(list_response.json()) == 5


# ============================================================================
# メイン（直接実行時）
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
