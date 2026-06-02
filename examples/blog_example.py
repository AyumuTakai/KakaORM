"""
kakaorm 使用例 — ブログシステム
==================================
実際のアプリケーションでの使い方を示す。

動かし方:
    pip install "kakaorm[aiosqlite]"
    python examples/blog_example.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kakaorm
from kakaorm import (
    BoolColumn,
    DateTimeColumn,
    ForeignKey,
    IntColumn,
    Model,
    StrColumn,
    has_many,
    belongs_to,
)
from kakaorm.migration import Migrator

# ── モデル定義 ────────────────────────────────────────────────


class Author(Model):
    """ブログ著者モデル。"""

    name  = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    bio   = StrColumn(nullable=True)

    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"


class Tag(Model):
    """記事タグ。"""

    name = StrColumn(nullable=False, unique=True)

    class Meta:
        table_name = "tag"


class Post(Model):
    """ブログ記事。"""

    title      = StrColumn(nullable=False)
    body       = StrColumn(nullable=True)
    published  = BoolColumn(nullable=False, default=False)
    views      = IntColumn(nullable=False, default=0)
    author_id  = ForeignKey(Author, nullable=True)
    created_at = DateTimeColumn(auto_now_add=True, nullable=False)
    updated_at = DateTimeColumn(auto_now=True, nullable=True)

    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"


# ── アプリケーションロジック ──────────────────────────────────


async def main():
    print("━━━ kakaorm Blog Example ━━━\n")

    # 1. 接続 & マイグレーション
    print("[ 1. DB接続・テーブル作成 ]")
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    migrator = Migrator(engine)
    migrator.validate_relationships([Author, Tag, Post])
    plan = await migrator.run([Author, Tag, Post])
    print(f"   適用: {len(plan.statements)} statements")
    print()

    # 2. 著者を作成
    print("[ 2. 著者の作成 ]")
    alice = await Author.create(name="Alice", email="alice@example.com", bio="Tech writer")
    bob   = await Author.create(name="Bob",   email="bob@example.com")
    print(f"   作成: {alice}, {bob}")
    print()

    # 3. 記事を bulk_create で一括作成
    print("[ 3. 記事の一括作成 (bulk_create) ]")
    new_posts = [
        Post(title="Python 非同期入門", body="...", published=True,  views=1500, author_id=alice.id),
        Post(title="kakaorm 設計解説",  body="...", published=True,  views=800,  author_id=alice.id),
        Post(title="SQLAlchemy 比較",   body="...", published=False, views=0,    author_id=bob.id),
        Post(title="未完成の記事",      body="",    published=False, views=0,    author_id=bob.id),
    ]
    posts = await Post.bulk_create(new_posts)
    print(f"   作成: {len(posts)} 記事")
    # auto_now_add が適用されていることを確認
    print(f"   created_at サンプル: {posts[0].created_at}")
    print()

    # 4. クエリ例
    print("[ 4. クエリ例 ]")

    # 公開済みの記事を閲覧数順に取得
    published_posts = await Post.where(Post.published == True).order_by(Post.views.desc)
    print(f"   公開済み記事: {[p.title for p in published_posts]}")

    # 閲覧数 1000 以上の記事
    popular = await Post.where(Post.views >= 1000)
    print(f"   人気記事 (1000以上): {[p.title for p in popular]}")

    # Alice の記事数
    alice_count = await Post.where(Post.author_id == alice.id).count()
    print(f"   Aliceの記事数: {alice_count}")

    # タイトルで部分一致検索
    python_posts = await Post.where(Post.title.like("%Python%"))
    print(f"   「Python」を含む記事: {[p.title for p in python_posts]}")

    # 複合条件: 公開済み AND 閲覧数 > 500
    good_posts = await Post.where(
        (Post.published == True) & (Post.views > 500)
    ).order_by(Post.views.desc)
    print(f"   公開済み&人気: {[p.title for p in good_posts]}")

    # 未公開の記事が存在するか
    has_drafts = await Post.where(Post.published == False).exists()
    print(f"   下書きあり: {has_drafts}")
    print()

    # 5. リレーション操作
    print("[ 5. リレーション (belongs_to / has_many) ]")

    # belongs_to: 記事の著者を取得
    post = await Post.get(Post.title == "Python 非同期入門")
    author = await post.author
    print(f"   「{post.title}」の著者: {author.name}")

    # has_many: 著者の記事一覧を取得
    alice_posts = await alice.posts
    print(f"   Alice の記事: {[p.title for p in alice_posts]}")
    print()

    # 6. 更新と削除
    print("[ 6. 更新・削除 ]")

    # 特定の記事を更新（auto_now が updated_at を自動更新）
    post.views += 100
    await post.save()
    updated = await Post.get(Post.id == post.id)
    print(f"   更新後の閲覧数: {updated.views}")
    print(f"   updated_at: {updated.updated_at}")

    # 未公開記事を一括で published=True に
    count = await Post.where(Post.published == False).update(published=True)
    print(f"   一括公開: {count} 件")

    # 特定の記事を削除
    draft = await Post.get_or_none(Post.title == "未完成の記事")
    if draft:
        await draft.delete()
        print("   「未完成の記事」を削除")

    # 最終的な記事数
    final_count = await Post.all().count()
    print(f"   最終記事数: {final_count}")
    print()

    # 7. async for ストリーミング
    print("[ 7. async for ループ ]")
    async for p in Post.all().order_by(Post.views.desc).limit(3):
        status = "✓" if p.published else "✗"
        print(f"   {status} {p.title} ({p.views} views)")
    print()

    # 8. マイグレーション差分チェック（冪等性確認）
    print("[ 8. マイグレーション差分チェック ]")
    plan2 = await migrator.run([Author, Tag, Post])
    print(f"   差分: {'なし（冪等）' if plan2.is_empty() else plan2.sql}")
    print()

    await engine.disconnect()
    print("━━━ 完了 ━━━")


if __name__ == "__main__":
    asyncio.run(main())
