"""
get_or_create() / update_or_create() のテスト
"""

import pytest
from conftest import Author, Post


class TestGetOrCreate:
    async def test_creates_when_not_found(self, engine):
        """存在しない場合は新規作成し created=True を返す。"""
        author, created = await Author.get_or_create(
            email="new@example.com",
            defaults={"name": "New Author"},
        )
        assert created is True
        assert author.id is not None
        assert author.name == "New Author"
        assert author.email == "new@example.com"

    async def test_returns_existing_when_found(self, engine):
        """既存レコードがある場合は返し created=False を返す。"""
        existing = await Author.create(name="Alice", email="alice@example.com")
        author, created = await Author.get_or_create(
            email="alice@example.com",
            defaults={"name": "Should Not Apply"},
        )
        assert created is False
        assert author.id == existing.id
        assert author.name == "Alice"  # defaults は適用されない

    async def test_defaults_not_applied_to_existing(self, engine):
        """既存レコードがある場合 defaults は無視される。"""
        await Author.create(name="Original", email="orig@example.com")
        author, created = await Author.get_or_create(
            email="orig@example.com",
            defaults={"name": "Changed"},
        )
        assert created is False
        assert author.name == "Original"

    async def test_lookup_fields_included_in_created(self, engine):
        """lookup フィールドも新規作成に含まれる。"""
        author, created = await Author.get_or_create(
            name="Bob",
            email="bob@example.com",
        )
        assert created is True
        fetched = await Author.get(Author.email == "bob@example.com")
        assert fetched.name == "Bob"

    async def test_multiple_lookup_fields(self, engine):
        """複数の lookup フィールドで AND 検索する。"""
        await Author.create(name="Alice", email="alice@example.com")
        # 同じ name だが email が異なる → 新規作成
        author, created = await Author.get_or_create(
            name="Alice",
            email="alice2@example.com",
            defaults={"bio": "Another Alice"},
        )
        assert created is True

    async def test_no_duplicates_created(self, engine):
        """同じ条件で2回呼んでも重複しない。"""
        await Author.get_or_create(email="once@example.com", defaults={"name": "Once"})
        await Author.get_or_create(email="once@example.com", defaults={"name": "Once"})
        count = await Author.where(Author.email == "once@example.com").count()
        assert count == 1


class TestUpdateOrCreate:
    async def test_creates_when_not_found(self, engine):
        """存在しない場合は新規作成し created=True を返す。"""
        post, created = await Post.update_or_create(
            title="New Post",
            defaults={"views": 100, "published": True},
        )
        assert created is True
        assert post.id is not None
        assert post.views == 100

    async def test_updates_when_found(self, engine):
        """既存レコードがある場合は defaults で更新し created=False を返す。"""
        existing = await Post.create(title="Existing", views=0, published=False)
        post, created = await Post.update_or_create(
            title="Existing",
            defaults={"views": 999, "published": True},
        )
        assert created is False
        assert post.id == existing.id
        assert post.views == 999
        assert post.published == True  # noqa: E712

    async def test_update_persisted_to_db(self, engine):
        """更新内容が DB に保存されている。"""
        await Post.create(title="PersistMe", views=0)
        await Post.update_or_create(
            title="PersistMe",
            defaults={"views": 42},
        )
        fetched = await Post.get(Post.title == "PersistMe")
        assert fetched.views == 42

    async def test_lookup_fields_not_overwritten_by_defaults(self, engine):
        """lookup フィールドは defaults で上書きされない。"""
        await Post.create(title="StableTitle", views=0)
        post, created = await Post.update_or_create(
            title="StableTitle",
            defaults={"views": 1},
        )
        assert created is False
        assert post.title == "StableTitle"

    async def test_defaults_none_safe(self, engine):
        """defaults=None でも動作する。"""
        post, created = await Post.update_or_create(
            title="NoDefaults",
        )
        assert created is True

    async def test_multiple_lookup_fields(self, engine):
        """複数の lookup フィールドで AND 検索して更新する。"""
        author = await Author.create(name="Alice", email="a@example.com")
        await Post.create(title="T1", views=0, author_id=author.id)

        post, created = await Post.update_or_create(
            title="T1",
            author_id=author.id,
            defaults={"views": 500},
        )
        assert created is False
        assert post.views == 500
