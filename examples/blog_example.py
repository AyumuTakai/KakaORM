"""
kakaorm 使用例 — ブログシステム
==================================
実際のアプリケーションでの使い方を示す。

動かし方:
    pip install aiosqlite
    python examples/blog_example.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kakaorm
from kakaorm import BoolColumn, DateTimeColumn, ForeignKey, IntColumn, Model, StrColumn
from kakaorm.migration import Migrator

# ── モデル定義 ────────────────────────────────────────────────


class Author(Model):
    """ブログ著者モデル。"""

    name = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    bio = StrColumn(nullable=True)

    class Meta:
        table_name = "author"


class Tag(Model):
    """記事タグ。"""

    name = StrColumn(nullable=False, unique=True)

    class Meta:
        table_name = "tag"


class Post(Model):
    """ブログ記事。"""

    title = StrColumn(nullable=False)
    body = StrColumn(nullable=True)
    published = BoolColumn(nullable=False, default=False)
    views = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(Author, nullable=True)

    class Meta:
        table_name = "post"


# ── アプリケーションロジック ──────────────────────────────────


async def main():
    print("━━━ kakaorm Blog Example ━━━\n")

    # 1. 接続 & マイグレーション
    print("[ 1. DB接続・テーブル作成 ]")
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    migrator = Migrator(engine)
    plan = await migrator.plan([Author, Tag, Post])
    print(f"   プラン: {len(plan.statements)} statements")
    await plan.apply()
    print()

    # 2. 著者を作成
    print("[ 2. 著者の作成 ]")
    alice = await Author.create(
        name="Alice", email="alice@example.com", bio="Tech writer"
    )
    bob = await Author.create(name="Bob", email="bob@example.com")
    print(f"   作成: {alice}, {bob}")
    print()

    # 3. 記事を作成
    print("[ 3. 記事の作成 ]")
    posts = [
        await Post.create(
            title="Python 非同期入門",
            body="...",
            published=True,
            views=1500,
            author_id=alice.id,
        ),
        await Post.create(
            title="kakaorm 設計解説",
            body="...",
            published=True,
            views=800,
            author_id=alice.id,
        ),
        await Post.create(
            title="SQLAlchemy 比較",
            body="...",
            published=False,
            views=0,
            author_id=bob.id,
        ),
        await Post.create(
            title="未完成の記事", body="", published=False, views=0, author_id=bob.id
        ),
    ]
    print(f"   作成: {len(posts)} 記事")
    print()

    # 4. クエリ例
    print("[ 4. クエリ例 ]")

    # 公開済みの記事を閲覧数順に取得
    published = await Post.where(Post.published == True).order_by(Post.views.desc)
    print(f"   公開済み記事: {[p.title for p in published]}")

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

    # 5. 更新と削除
    print("[ 5. 更新・削除 ]")

    # 特定の記事を更新
    post = await Post.get(Post.title == "Python 非同期入門")
    post.views += 100
    await post.save()
    updated = await Post.get(Post.id == post.id)
    print(f"   更新後の閲覧数: {updated.views}")

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

    # 6. async for ストリーミング
    print("[ 6. async for ループ ]")
    async for post in Post.all().order_by(Post.views.desc).limit(3):
        status = "✓" if post.published else "✗"
        print(f"   {status} {post.title} ({post.views} views)")
    print()

    # 7. マイグレーション差分チェック
    print("[ 7. マイグレーション差分チェック ]")
    plan2 = await migrator.plan([Author, Tag, Post])
    print(f"   差分: {'なし' if plan2.is_empty() else plan2.sql}")
    print()

    await engine.disconnect()
    print("━━━ 完了 ━━━")


if __name__ == "__main__":
    asyncio.run(main())
