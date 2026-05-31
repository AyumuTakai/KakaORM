"""
トランザクション / ロールバック テスト
"""

import pytest
from conftest import Author, Post


class TestTransactionCommit:
    async def test_commit_on_success(self, engine):
        """正常終了でデータが永続化される。"""
        async with engine.transaction():
            await Author.create(name="Committed", email="committed@example.com")

        result = await Author.get_or_none(Author.name == "Committed")
        assert result is not None

    async def test_multiple_operations_committed(self, engine):
        """複数操作がすべてコミットされる。"""
        async with engine.transaction():
            alice = await Author.create(name="Alice", email="alice@example.com")
            await Post.create(title="Post1", views=10, author_id=alice.id)
            await Post.create(title="Post2", views=20, author_id=alice.id)

        posts = await Post.filter(Post.author_id == alice.id)
        assert len(posts) == 2

    async def test_update_committed(self, engine):
        """UPDATE もトランザクション内でコミットされる。"""
        author = await Author.create(name="Before", email="before@example.com")

        async with engine.transaction():
            await Author.filter(Author.id == author.id).update(name="After")

        updated = await Author.get(Author.id == author.id)
        assert updated.name == "After"


class TestTransactionRollback:
    async def test_rollback_on_exception(self, engine):
        """例外発生時にロールバックされ、データが残らない。"""
        try:
            async with engine.transaction():
                await Author.create(name="ShouldBeGone", email="gone@example.com")
                raise RuntimeError("意図的なエラー")
        except RuntimeError:
            pass

        result = await Author.get_or_none(Author.name == "ShouldBeGone")
        assert result is None

    async def test_partial_rollback(self, engine):
        """途中まで成功した操作もすべてロールバックされる。"""
        try:
            async with engine.transaction():
                await Author.create(name="Partial1", email="p1@example.com")
                await Author.create(name="Partial2", email="p2@example.com")
                raise ValueError("途中でエラー")
        except ValueError:
            pass

        assert await Author.filter(Author.name == "Partial1").count() == 0
        assert await Author.filter(Author.name == "Partial2").count() == 0

    async def test_exception_propagates(self, engine):
        """ロールバック後に例外が呼び出し元に伝播する。"""
        with pytest.raises(RuntimeError, match="test error"):
            async with engine.transaction():
                await Author.create(name="Fail", email="fail@example.com")
                raise RuntimeError("test error")

    async def test_subsequent_operations_work_after_rollback(self, engine):
        """ロールバック後もエンジンは正常に使用できる。"""
        try:
            async with engine.transaction():
                raise RuntimeError("rollback this")
        except RuntimeError:
            pass

        # ロールバック後に正常な INSERT ができる
        author = await Author.create(name="AfterRollback", email="after@example.com")
        assert author.id is not None


class TestTransactionIsolation:
    async def test_data_visible_within_transaction(self, engine):
        """トランザクション内で作成したデータは同トランザクション内で参照できる。"""
        async with engine.transaction():
            author = await Author.create(name="InTx", email="intx@example.com")
            fetched = await Author.get(Author.id == author.id)
            assert fetched.name == "InTx"

    async def test_update_and_read_within_transaction(self, engine):
        """トランザクション内で UPDATE した値を即座に読み返せる。"""
        author = await Author.create(name="Original", email="orig@example.com")

        async with engine.transaction():
            await Author.filter(Author.id == author.id).update(name="Modified")
            refetch = await Author.get(Author.id == author.id)
            assert refetch.name == "Modified"

    async def test_delete_and_count_within_transaction(self, engine):
        """トランザクション内の DELETE が同トランザクション内の COUNT に反映される。"""
        await Author.create(name="ToDelete", email="del@example.com")

        async with engine.transaction():
            await Author.filter(Author.name == "ToDelete").delete()
            count = await Author.filter(Author.name == "ToDelete").count()
            assert count == 0

    async def test_mixed_crud_in_transaction(self, engine):
        """INSERT / UPDATE / DELETE の混合操作がアトミックにコミットされる。"""
        existing = await Author.create(name="Existing", email="ex@example.com")

        async with engine.transaction():
            new_author = await Author.create(name="New", email="new@example.com")
            await Author.filter(Author.id == existing.id).update(name="Updated")
            await Post.create(title="TxPost", views=0, author_id=new_author.id)

        assert await Author.filter(Author.name == "Updated").count() == 1
        assert await Author.filter(Author.name == "New").count() == 1
        assert await Post.filter(Post.title == "TxPost").count() == 1
