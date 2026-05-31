"""
pytest 共有フィクスチャ
========================
全テストで使うモデル定義とデータベースフィクスチャを提供する。
"""

import os
import sys

import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kakaorm
from kakaorm import (
    BoolColumn,
    FloatColumn,
    ForeignKey,
    IntColumn,
    Model,
    StrColumn,
)

# ── モデル定義（全テストで共有）────────────────────────────────

class Author(Model):
    name  = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    bio   = StrColumn(nullable=True)

    class Meta:
        table_name = "author"


class Post(Model):
    title     = StrColumn(nullable=False)
    body      = StrColumn(nullable=True)
    views     = IntColumn(nullable=False, default=0)
    published = BoolColumn(nullable=False, default=False)
    score     = FloatColumn(nullable=True)
    author_id = ForeignKey(Author, nullable=True)

    class Meta:
        table_name = "post"


# ── フィクスチャ ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    """テストごとに新規のインメモリ SQLite DB を用意する。"""
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Author)
    await eng.create_table(Post)
    yield eng
    await eng.disconnect()


@pytest_asyncio.fixture
async def seeded_engine(engine):
    """
    集計・JOIN テスト用の初期データ付きエンジン。

    Authors: Alice (id=1), Bob (id=2)
    Posts:
      - Python入門    published=True  views=2000 score=4.5  author=Alice
      - 非同期処理    published=True  views=1200 score=4.0  author=Alice
      - kakaorm解説   published=True  views=400  score=3.5  author=Alice
      - 未公開ドラフト published=False views=100  score=None author=Bob
    """
    alice = await Author.create(name="Alice", email="alice@example.com", bio="Tech writer")
    bob   = await Author.create(name="Bob",   email="bob@example.com")

    await Post.create(title="Python入門",    published=True,  views=2000, score=4.5, author_id=alice.id)
    await Post.create(title="非同期処理",    published=True,  views=1200, score=4.0, author_id=alice.id)
    await Post.create(title="kakaorm解説",   published=True,  views=400,  score=3.5, author_id=alice.id)
    await Post.create(title="未公開ドラフト", published=False, views=100,  score=None, author_id=bob.id)

    return engine
