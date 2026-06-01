"""
FastAPI + KakaORM 統合ガイド：ページング & フィルタリング
==========================================================

実装パターン:
- offset ベースのページング（page, limit）
- 複数条件フィルタリング
- 多列ソート
- PaginationResponse スキーマ

実行:
    pip install fastapi uvicorn "kakaorm[aiosqlite]" pydantic
    python examples/fastapi_pagination.py
    # http://localhost:8000/docs で Swagger UI を確認

テスト URL:
    http://localhost:8000/posts?page=1&limit=5&sort=-id,title
    http://localhost:8000/posts/search?status=published&author=Alice
"""

from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel, Field

import kakaorm
from kakaorm import Model, StrColumn, IntColumn, BoolColumn, ForeignKey, has_many, belongs_to
from kakaorm.migration import Migrator
from kakaorm.engine import Engine


# ============================================================================
# モデル定義
# ============================================================================

class Author(Model):
    """著者モデル"""
    name = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)

    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"


class Post(Model):
    """投稿モデル"""
    title = StrColumn(nullable=False)
    content = StrColumn(nullable=True)
    status = StrColumn(nullable=False, default="draft")  # draft, published, archived
    views = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(Author, nullable=False)

    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"


# ============================================================================
# Pydantic スキーマ
# ============================================================================

class PaginationResponse(BaseModel):
    """ページングレスポンス"""
    items: list[dict]  # KakaORM モデルの dict 表現
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool


# ============================================================================
# FastAPI ライフサイクル
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown"""
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    plan = await Migrator(engine).plan([Author, Post])
    if not plan.is_empty():
        await plan.apply()

    app.state.engine = engine

    # サンプルデータ作成
    alice = await Author.create(name="Alice", email="alice@example.com")
    bob = await Author.create(name="Bob", email="bob@example.com")

    await Post.create(
        title="Python Tips",
        content="...",
        status="published",
        views=100,
        author_id=alice.id,
    )
    await Post.create(
        title="FastAPI Guide",
        content="...",
        status="published",
        views=200,
        author_id=alice.id,
    )
    await Post.create(
        title="Draft Post",
        content="...",
        status="draft",
        views=0,
        author_id=bob.id,
    )
    await Post.create(
        title="SQL Performance",
        content="...",
        status="published",
        views=150,
        author_id=bob.id,
    )

    yield

    await engine.disconnect()


# ============================================================================
# FastAPI
# ============================================================================

app = FastAPI(
    title="KakaORM Pagination Example",
    description="ページング、フィルタリング、ソート",
    version="1.0.0",
    lifespan=lifespan,
)


async def get_engine() -> Engine:
    return app.state.engine


# ============================================================================
# ページング & フィルタリングエンドポイント
# ============================================================================

@app.get("/posts", response_model=PaginationResponse, tags=["Posts"])
async def list_posts_paginated(
    page: int = Query(1, ge=1, description="ページ番号（1から開始）"),
    page_size: int = Query(10, ge=1, le=100, description="1ページあたりの件数"),
    sort: str = Query("id", description="ソート：'id' または '-id'（降順）, 複数可"),
    engine: Annotated[Engine, Depends(get_engine)] = None,
):
    """
    投稿一覧をページング取得

    クエリパラメータ:
    - page: ページ番号（デフォルト: 1）
    - page_size: 1ページの件数（デフォルト: 10, 最大: 100）
    - sort: ソート指定（デフォルト: 'id'）

    例:
    - GET /posts?page=1&page_size=5&sort=title
    - GET /posts?page=2&page_size=10&sort=-views,title
    """
    skip = (page - 1) * page_size

    # 総件数を取得
    total = await Post.all().count()

    # Query を構築
    query = Post.all()

    # ソート処理（複数列対応）
    sort_fields = sort.split(",")
    for field_spec in sort_fields:
        field_name = field_spec.lstrip("-")
        is_desc = field_spec.startswith("-")

        if not hasattr(Post, field_name):
            raise HTTPException(status_code=400, detail=f"Invalid sort field: {field_name}")

        col = getattr(Post, field_name)
        query = query.order_by(col.desc if is_desc else col.asc)

    # ページング + prefetch
    posts = await (
        query
        .prefetch("author")
        .offset(skip)
        .limit(page_size)
        .execute()
    )

    # レスポンス構築
    pages = (total + page_size - 1) // page_size

    return PaginationResponse(
        items=[p.model_dump() for p in posts],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


@app.get("/posts/search", tags=["Posts"])
async def search_posts(
    title: Optional[str] = Query(None, description="タイトル検索（部分一致）"),
    status: Optional[str] = Query(None, description="ステータス（draft, published, archived）"),
    author_name: Optional[str] = Query(None, description="著者名検索"),
    min_views: int = Query(0, ge=0, description="最小ビュー数"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    engine: Annotated[Engine, Depends(get_engine)] = None,
):
    """
    複合条件検索

    クエリパラメータ:
    - title: タイトル（LIKE 検索）
    - status: ステータス
    - author_name: 著者名
    - min_views: 最小ビュー数
    - page: ページ番号
    - page_size: 1ページの件数

    例:
    - GET /posts/search?status=published&min_views=50
    - GET /posts/search?title=python&author_name=Alice
    """
    skip = (page - 1) * page_size

    # Query を段階的に構築
    query = Post.all()

    if title:
        # LIKE 検索（SQLite では icontains が利用可能）
        # Note: SQLite では case-insensitive は設定が必要
        query = query.where(Post.title.contains(title))

    if status:
        query = query.where(Post.status == status)

    if min_views > 0:
        query = query.where(Post.views >= min_views)

    # 著者名フィルタ（prefetch 前に WHERE で絞る場合は JOIN 必要）
    # ここでは簡略化のため、取得後のフィルタリング
    posts_all = await query.prefetch("author").execute()

    if author_name:
        posts_all = [
            p for p in posts_all
            if p.author and author_name.lower() in p.author.name.lower()
        ]

    # 総件数（フィルタ後）
    total = len(posts_all)

    # ページング
    posts = posts_all[skip : skip + page_size]

    pages = (total + page_size - 1) // page_size

    return {
        "items": [p.model_dump() for p in posts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


@app.get("/posts/stats", tags=["Stats"])
async def get_stats(
    engine: Annotated[Engine, Depends(get_engine)] = None,
):
    """
    統計情報を取得（GROUP BY + 集計）

    返値:
    - total_posts: 総投稿数
    - published_posts: 公開投稿数
    - total_views: 総ビュー数
    - avg_views: 平均ビュー数
    """
    all_posts = await Post.all()

    total = len(all_posts)
    published = len([p for p in all_posts if p.status == "published"])
    total_views = sum(p.views for p in all_posts)
    avg_views = total_views / total if total > 0 else 0

    return {
        "total_posts": total,
        "published_posts": published,
        "total_views": total_views,
        "avg_views": round(avg_views, 2),
    }


@app.get("/authors/{author_id}/posts", tags=["Authors"])
async def get_author_posts(
    author_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    engine: Annotated[Engine, Depends(get_engine)] = None,
):
    """著者の投稿一覧（ページング）"""
    author = await Author.get_or_none(Author.id == author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found")

    skip = (page - 1) * page_size

    # 著者の投稿を取得
    total = await Post.where(Post.author_id == author_id).count()
    posts = await (
        Post.where(Post.author_id == author_id)
        .offset(skip)
        .limit(page_size)
        .execute()
    )

    pages = (total + page_size - 1) // page_size

    return {
        "author": author.model_dump(),
        "items": [PostResponse.from_orm(p) for p in posts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


# ============================================================================
# メイン
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
