"""
CRUD 統合テスト（aiosqlite in-memory）
"""

import pytest
from conftest import Author, Post


class TestCreate:
    async def test_create_returns_instance_with_id(self, engine):
        author = await Author.create(name="Alice", email="alice@example.com")
        assert author.id is not None
        assert author.name == "Alice"

    async def test_create_default_values(self, engine):
        post = await Post.create(title="Draft")
        assert post.published == False  # noqa: E712
        assert post.views == 0


class TestGet:
    async def test_get_by_id(self, engine):
        author = await Author.create(name="Bob", email="bob@example.com")
        fetched = await Author.get(Author.id == author.id)
        assert fetched.name == "Bob"

    async def test_get_by_email(self, engine):
        await Author.create(name="Carol", email="carol@example.com")
        fetched = await Author.get(Author.email == "carol@example.com")
        assert fetched.name == "Carol"

    async def test_get_not_found_raises(self, engine):
        with pytest.raises(Author.NotFound):
            await Author.get(Author.id == 99999)

    async def test_get_or_none_returns_none(self, engine):
        result = await Author.get_or_none(Author.id == 99999)
        assert result is None

    async def test_get_or_none_returns_instance(self, engine):
        author = await Author.create(name="Dave", email="dave@example.com")
        result = await Author.get_or_none(Author.id == author.id)
        assert result is not None
        assert result.name == "Dave"

    async def test_first(self, engine):
        await Author.create(name="E1", email="e1@example.com")
        await Author.create(name="E2", email="e2@example.com")
        first = await Author.first()
        assert first is not None

    async def test_last(self, engine):
        await Author.create(name="F1", email="f1@example.com")
        await Author.create(name="F2", email="f2@example.com")
        last = await Author.last()
        assert last is not None


class TestFilter:
    async def test_where_returns_matching(self, engine):
        await Author.create(name="Grace", email="grace@example.com")
        await Author.create(name="Heidi", email="heidi@example.com")
        results = await Author.where(Author.name == "Grace")
        assert len(results) == 1
        assert results[0].name == "Grace"

    async def test_where_all(self, engine):
        await Author.create(name="Ivan", email="ivan@example.com")
        await Author.create(name="Judy", email="judy@example.com")
        results = await Author.all()
        assert len(results) >= 2

    async def test_count(self, engine):
        await Author.create(name="Karl", email="karl@example.com")
        await Author.create(name="Laura", email="laura@example.com")
        n = await Author.all().count()
        assert n >= 2

    async def test_exists_true(self, engine):
        await Author.create(name="Exists", email="exists@example.com")
        assert await Author.where(Author.name == "Exists").exists() is True

    async def test_exists_false(self, engine):
        assert await Author.where(Author.name == "NoSuchUser12345").exists() is False

    async def test_order_by(self, engine):
        await Post.create(title="Z", views=10)
        await Post.create(title="A", views=20)
        posts = await Post.all().order_by(Post.views.asc)
        assert posts[0].views <= posts[-1].views

    async def test_limit(self, engine):
        for i in range(5):
            await Post.create(title=f"P{i}", views=i)
        posts = await Post.all().limit(3)
        assert len(posts) == 3

    async def test_offset(self, engine):
        for i in range(5):
            await Post.create(title=f"Q{i}", views=i)
        all_posts  = await Post.all().order_by(Post.views.asc)
        offset_posts = await Post.all().order_by(Post.views.asc).offset(2)
        assert offset_posts[0].views == all_posts[2].views

    async def test_like(self):
        clause = Author.name.like("Al%")
        assert "LIKE" in clause.sql

    async def test_in(self, engine):
        await Post.create(title="InTest1", views=1)
        await Post.create(title="InTest2", views=2)
        posts = await Post.where(Post.views.in_([1, 2]))
        assert len(posts) == 2

    async def test_async_for(self, engine):
        await Post.create(title="Iter1", views=10)
        await Post.create(title="Iter2", views=20)
        collected = []
        async for post in Post.where(Post.title.like("Iter%")):
            collected.append(post.title)
        assert len(collected) == 2


class TestUpdate:
    async def test_save_updates_record(self, engine):
        author = await Author.create(name="Mike", email="mike@example.com")
        author.name = "Michael"
        await author.save()
        refetched = await Author.get(Author.id == author.id)
        assert refetched.name == "Michael"

    async def test_bulk_update(self, engine):
        await Post.create(title="BulkA", views=0, published=False)
        await Post.create(title="BulkB", views=0, published=False)
        updated = await Post.where(Post.published == False).update(views=999)  # noqa: E712
        assert updated >= 2
        posts = await Post.where(Post.views == 999)
        assert len(posts) >= 2


class TestDelete:
    async def test_delete_instance(self, engine):
        author = await Author.create(name="ToDelete", email="del@example.com")
        pk = author.id
        await author.delete()
        result = await Author.get_or_none(Author.id == pk)
        assert result is None

    async def test_bulk_delete(self, engine):
        await Post.create(title="DelMe", views=0)
        before = await Post.where(Post.title == "DelMe").count()
        assert before >= 1
        deleted = await Post.where(Post.title == "DelMe").delete()
        assert deleted >= 1
        after = await Post.where(Post.title == "DelMe").count()
        assert after == 0
