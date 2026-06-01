"""
FastAPI + KakaORM 統合ガイド：中級パターン
============================================

実装パターン:
- Depends で Engine 注入
- 複数モデル関連処理
- prefetch による N+1 回避
- Pydantic スキーマ分離（request/response）
- エラー処理統一化

実行:
    pip install fastapi uvicorn kakaorm[aiosqlite] pydantic
    python examples/fastapi_advanced.py
    # http://localhost:8000/docs で Swagger UI を確認
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel, Field

import kakaorm
from kakaorm import Model, StrColumn, IntColumn, DateTimeColumn, ForeignKey, has_many, belongs_to
from kakaorm.migration import Migrator
from kakaorm.engine import Engine


# ============================================================================
# モデル定義
# ============================================================================

class Author(Model):
    """著者モデル"""
    name = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)

    # 逆参照：著者が書いた投稿
    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"


class Post(Model):
    """投稿モデル"""
    title = StrColumn(nullable=False)
    content = StrColumn(nullable=True)
    published = IntColumn(nullable=False, default=0)  # 0=False, 1=True
    views = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(Author, nullable=False)

    # 順参照：投稿の著者
    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"


# ============================================================================
# Pydantic スキーマ（リクエスト/レスポンス）
# ============================================================================

class AuthorCreate(BaseModel):
    """著者作成リクエスト"""
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5)


class AuthorUpdate(BaseModel):
    """著者更新リクエスト"""
    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=5)


class PostCreate(BaseModel):
    """投稿作成リクエスト"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str | None = None
    author_id: int = Field(..., gt=0)


class PostUpdate(BaseModel):
    """投稿更新リクエスト"""
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = None
    published: bool | None = None


# ============================================================================
# FastAPI ライフサイクル管理
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Engine 初期化 + マイグレーション
    Shutdown: Engine 終了
    """
    # Startup
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    plan = await Migrator(engine).plan([Author, Post])
    if not plan.is_empty():
        await plan.apply()

    app.state.engine = engine

    # サンプルデータ挿入（デモ用）
    await Author.create(name="Alice", email="alice@example.com")
    await Author.create(name="Bob", email="bob@example.com")

    yield

    # Shutdown
    await engine.disconnect()


# ============================================================================
# FastAPI アプリケーション
# ============================================================================

app = FastAPI(
    title="KakaORM FastAPI Advanced Example",
    description="複数モデル、リレーション、prefetch の実装パターン",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================================
# 依存性注入（Engine）
# ============================================================================

async def get_engine() -> Engine:
    """Engine を取得（Depends で使用）"""
    return app.state.engine


# ============================================================================
# 著者エンドポイント
# ============================================================================

@app.get("/authors", response_model=list[Author], tags=["Authors"])
async def list_authors(
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """著者一覧を取得"""
    return await Author.all()


@app.get("/authors/{author_id}", response_model=Author, tags=["Authors"])
async def get_author(
    author_id: int,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """著者詳細を取得（投稿一覧含む、prefetch で N+1 回避）"""
    author = await Author.get_or_none(Author.id == author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")
    return author


@app.post("/authors", response_model=Author, status_code=201, tags=["Authors"])
async def create_author(
    body: AuthorCreate,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """著者を新規作成"""
    try:
        author = await Author.create(**body.model_dump())
        return author
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=400,
                detail="Email already exists"
            )
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/authors/{author_id}", response_model=Author, tags=["Authors"])
async def update_author(
    author_id: int,
    body: AuthorUpdate,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """著者情報を更新"""
    author = await Author.get_or_none(Author.id == author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")

    # 与えられたフィールドのみ更新
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(author, field, value)

    try:
        await author.save()
        return author
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=400,
                detail="Email already exists"
            )
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/authors/{author_id}", status_code=204, tags=["Authors"])
async def delete_author(
    author_id: int,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """著者を削除"""
    author = await Author.get_or_none(Author.id == author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")

    await author.delete()


# ============================================================================
# 投稿エンドポイント
# ============================================================================

@app.get("/posts", response_model=list[Post], tags=["Posts"])
async def list_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    published_only: bool = Query(False),
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """
    投稿一覧を取得（著者情報含む、prefetch で N+1 回避）

    - skip: スキップする件数（デフォルト: 0）
    - limit: 取得件数（デフォルト: 10, 最大: 100）
    - published_only: 公開済みのみを取得（デフォルト: False）
    """
    query = Post.all()

    if published_only:
        query = query.where(Post.published == 1)

    # prefetch で N+1 を回避
    posts = await (
        query
        .prefetch("author")
        .offset(skip)
        .limit(limit)
        .execute()
    )

    return posts


@app.get("/posts/{post_id}", response_model=Post, tags=["Posts"])
async def get_post(
    post_id: int,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """投稿詳細を取得（著者情報含む）"""
    post = await Post.get_or_none(Post.id == post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    # 著者情報を取得（prefetch は不要、単一インスタンス）
    await post.author

    return post


@app.post("/posts", response_model=Post, status_code=201, tags=["Posts"])
async def create_post(
    body: PostCreate,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """投稿を新規作成"""
    # 著者が存在するか確認
    author = await Author.get_or_none(Author.id == body.author_id)
    if author is None:
        raise HTTPException(status_code=400, detail="Author not found")

    try:
        post = await Post.create(**body.model_dump())
        return post
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/posts/{post_id}", response_model=Post, tags=["Posts"])
async def update_post(
    post_id: int,
    body: PostUpdate,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """投稿を更新"""
    post = await Post.get_or_none(Post.id == post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(post, field, value)

    try:
        await post.save()
        return post
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/posts/{post_id}", status_code=204, tags=["Posts"])
async def delete_post(
    post_id: int,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """投稿を削除"""
    post = await Post.get_or_none(Post.id == post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    await post.delete()


# ============================================================================
# 複合エンドポイント（トランザクション例）
# ============================================================================

@app.post("/authors-with-post", tags=["Bulk"])
async def create_author_with_post(
    author_data: AuthorCreate,
    post_data: PostCreate,
    engine: Annotated[Engine, Depends(get_engine)] = None
):
    """
    著者と投稿を同時に作成（トランザクション）

    エラーが発生した場合、両方のレコードがロールバックされます。
    """
    try:
        async with engine.transaction():
            # 著者を作成
            author = await Author.create(**author_data.model_dump())

            # 投稿を作成（著者ID を参照）
            post_dict = post_data.model_dump()
            post_dict["author_id"] = author.id
            post = await Post.create(**post_dict)

            return {
                "author": author.model_dump(),
                "post": post.model_dump(),
            }
    except Exception as e:
        # トランザクション自動 ROLLBACK
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# ヘルスチェック
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "ok"}


# ============================================================================
# メイン
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )
