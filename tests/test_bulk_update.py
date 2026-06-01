"""
bulk_update() — 一括 UPDATE テスト
"""

import pytest
from conftest import Author, Post


class TestBulkUpdateBasic:
    async def test_empty_list_returns_empty(self, engine):
        """空リストを渡すと空リストが返る。"""
        result = await Author.bulk_update([])
        assert result == []

    async def test_returns_same_instances(self, engine):
        """渡したインスタンスリストと同一オブジェクトを返す。"""
        instances = [await Author.create(name=f"User{i}", email=f"u{i}@example.com") for i in range(3)]
        result = await Author.bulk_update(instances, fields=["name"])
        assert result is instances

    async def test_updates_all_records(self, engine):
        """全インスタンスの変更が DB に反映される。"""
        instances = [await Author.create(name=f"Before{i}", email=f"a{i}@example.com") for i in range(5)]
        for inst in instances:
            inst.name = f"After{inst.id}"
        await Author.bulk_update(instances, fields=["name"])

        for inst in instances:
            fetched = await Author.get(Author.id == inst.id)
            assert fetched.name == f"After{inst.id}"

    async def test_updates_specified_fields_only(self, engine):
        """fields に指定したフィールドのみ更新され、他は変わらない。"""
        author = await Author.create(name="Original", email="orig@example.com", bio="Keep this")
        author.name = "Changed"
        author.bio = "Should not change"
        await Author.bulk_update([author], fields=["name"])

        fetched = await Author.get(Author.id == author.id)
        assert fetched.name == "Changed"
        assert fetched.bio == "Keep this"

    async def test_updates_all_fields_when_no_fields_specified(self, engine):
        """fields=None の場合は全フィールドを更新する。"""
        author = await Author.create(name="Before", email="all@example.com", bio="Old bio")
        author.name = "After"
        author.bio = "New bio"
        await Author.bulk_update([author])

        fetched = await Author.get(Author.id == author.id)
        assert fetched.name == "After"
        assert fetched.bio == "New bio"

    async def test_updates_multiple_fields(self, engine):
        """複数フィールドを同時に更新できる。"""
        posts = [
            await Post.create(title=f"Post{i}", views=0, published=False)
            for i in range(3)
        ]
        for post in posts:
            post.views = 999
            post.published = True
        await Post.bulk_update(posts, fields=["views", "published"])

        for post in posts:
            fetched = await Post.get(Post.id == post.id)
            assert fetched.views == 999
            assert fetched.published == True  # noqa: E712

    async def test_no_engine_raises(self):
        """エンジン未接続の場合は RuntimeError を送出する。"""
        import kakaorm
        original = Author._engine
        Author._engine = None
        try:
            with pytest.raises(RuntimeError):
                await Author.bulk_update([Author(name="x", email="x@x.com")], fields=["name"])
        finally:
            Author._engine = original


class TestBulkUpdateBatching:
    async def test_batch_size_splits_correctly(self, engine):
        """batch_size で分割しても全件更新される。"""
        instances = [await Author.create(name=f"Name{i}", email=f"b{i}@example.com") for i in range(10)]
        for inst in instances:
            inst.name = f"Updated{inst.id}"
        await Author.bulk_update(instances, fields=["name"], batch_size=3)

        for inst in instances:
            fetched = await Author.get(Author.id == inst.id)
            assert fetched.name == f"Updated{inst.id}"

    async def test_batch_size_one(self, engine):
        """batch_size=1 でも正常に動作する。"""
        instances = [await Author.create(name=f"C{i}", email=f"c{i}@example.com") for i in range(5)]
        for inst in instances:
            inst.name = "SingleBatch"
        await Author.bulk_update(instances, fields=["name"], batch_size=1)

        count = await Author.where(Author.name == "SingleBatch").count()
        assert count == 5


class TestBulkUpdateTransaction:
    async def test_bulk_update_in_transaction_commits(self, engine):
        """トランザクション内の bulk_update がコミットされる。"""
        instances = [await Author.create(name=f"Tx{i}", email=f"tx{i}@example.com") for i in range(3)]
        for inst in instances:
            inst.name = "Committed"
        async with engine.transaction():
            await Author.bulk_update(instances, fields=["name"])

        for inst in instances:
            fetched = await Author.get(Author.id == inst.id)
            assert fetched.name == "Committed"

    async def test_bulk_update_in_transaction_rollback(self, engine):
        """トランザクション例外で bulk_update もロールバックされる。"""
        instances = [await Author.create(name=f"Rb{i}", email=f"rb{i}@example.com") for i in range(3)]
        original_names = [inst.name for inst in instances]

        try:
            async with engine.transaction():
                for inst in instances:
                    inst.name = "ShouldRollback"
                await Author.bulk_update(instances, fields=["name"])
                raise ValueError("force rollback")
        except ValueError:
            pass

        for inst, original_name in zip(instances, original_names):
            fetched = await Author.get(Author.id == inst.id)
            assert fetched.name == original_name
