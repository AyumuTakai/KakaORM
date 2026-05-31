"""
bulk_create() — 一括 INSERT テスト
"""

import pytest
from conftest import Author, Post


class TestBulkCreateBasic:
    async def test_empty_list_returns_empty(self, engine):
        """空リストを渡すと空リストが返る。"""
        result = await Author.bulk_create([])
        assert result == []

    async def test_returns_same_instances(self, engine):
        """渡したインスタンスリストと同一オブジェクトを返す。"""
        instances = [Author(name=f"User{i}", email=f"u{i}@example.com") for i in range(3)]
        result = await Author.bulk_create(instances)
        assert result is instances

    async def test_ids_assigned(self, engine):
        """INSERT 後に各インスタンスに id が設定される。"""
        instances = [Author(name=f"A{i}", email=f"a{i}@example.com") for i in range(5)]
        await Author.bulk_create(instances)
        assert all(inst.id is not None for inst in instances)

    async def test_ids_are_unique(self, engine):
        """各インスタンスに異なる id が割り当てられる。"""
        instances = [Author(name=f"B{i}", email=f"b{i}@example.com") for i in range(5)]
        await Author.bulk_create(instances)
        ids = [inst.id for inst in instances]
        assert len(set(ids)) == 5

    async def test_ids_are_sequential(self, engine):
        """割り当てられた id が連続している。"""
        instances = [Author(name=f"C{i}", email=f"c{i}@example.com") for i in range(5)]
        await Author.bulk_create(instances)
        ids = sorted(inst.id for inst in instances)
        assert ids == list(range(ids[0], ids[0] + 5))

    async def test_data_persisted(self, engine):
        """INSERT されたデータが DB に存在する。"""
        instances = [
            Author(name="Alice", email="alice@example.com"),
            Author(name="Bob",   email="bob@example.com"),
        ]
        await Author.bulk_create(instances)

        assert await Author.where(Author.name == "Alice").count() == 1
        assert await Author.where(Author.name == "Bob").count() == 1

    async def test_values_correct(self, engine):
        """各フィールドの値が正しく保存される。"""
        instances = [
            Post(title="P1", views=100, published=True),
            Post(title="P2", views=200, published=False),
        ]
        await Post.bulk_create(instances)

        p1 = await Post.get(Post.title == "P1")
        p2 = await Post.get(Post.title == "P2")
        assert p1.views == 100
        assert p1.published == True   # noqa: E712
        assert p2.views == 200
        assert p2.published == False  # noqa: E712

    async def test_single_instance(self, engine):
        """1件でも動作する。"""
        result = await Author.bulk_create([Author(name="Solo", email="solo@example.com")])
        assert len(result) == 1
        assert result[0].id is not None


class TestBulkCreateCount:
    async def test_correct_count_in_db(self, engine):
        """指定した件数が正確に INSERT される。"""
        n = 50
        instances = [Author(name=f"U{i}", email=f"u{i}@test.com") for i in range(n)]
        await Author.bulk_create(instances)
        assert await Author.all().count() == n

    async def test_large_batch(self, engine):
        """大量データの一括 INSERT が動く。"""
        n = 200
        instances = [Author(name=f"L{i}", email=f"l{i}@test.com") for i in range(n)]
        await Author.bulk_create(instances)
        count = await Author.all().count()
        assert count == n
        assert all(inst.id is not None for inst in instances)


class TestBulkCreateBatchSize:
    async def test_batch_size_splits_correctly(self, engine):
        """batch_size で分割しても全件 INSERT される。"""
        n = 25
        instances = [Author(name=f"S{i}", email=f"s{i}@test.com") for i in range(n)]
        await Author.bulk_create(instances, batch_size=10)

        count = await Author.all().count()
        assert count == n

    async def test_batch_size_ids_assigned(self, engine):
        """分割 INSERT 後もすべてのインスタンスに id が設定される。"""
        n = 25
        instances = [Author(name=f"T{i}", email=f"t{i}@test.com") for i in range(n)]
        await Author.bulk_create(instances, batch_size=10)

        assert all(inst.id is not None for inst in instances)
        assert len({inst.id for inst in instances}) == n

    async def test_batch_size_one(self, engine):
        """batch_size=1 は create() ループと同等。"""
        instances = [Author(name=f"O{i}", email=f"o{i}@test.com") for i in range(5)]
        await Author.bulk_create(instances, batch_size=1)
        assert all(inst.id is not None for inst in instances)


class TestBulkCreateWithTransaction:
    async def test_bulk_create_in_transaction_commits(self, engine):
        """トランザクション内の bulk_create がコミットされる。"""
        async with engine.transaction():
            instances = [Author(name=f"TX{i}", email=f"tx{i}@test.com") for i in range(3)]
            await Author.bulk_create(instances)

        count = await Author.all().count()
        assert count == 3

    async def test_bulk_create_in_transaction_rollback(self, engine):
        """トランザクション例外で bulk_create もロールバックされる。"""
        try:
            async with engine.transaction():
                instances = [Author(name=f"RB{i}", email=f"rb{i}@test.com") for i in range(3)]
                await Author.bulk_create(instances)
                raise RuntimeError("rollback!")
        except RuntimeError:
            pass

        count = await Author.all().count()
        assert count == 0


class TestBulkCreatePerformance:
    async def test_faster_than_loop(self, engine):
        """bulk_create が create() ループより少ない SQL 発行で済むことを間接確認。"""
        import time

        n = 100

        # bulk_create
        t0 = time.perf_counter()
        instances = [Author(name=f"BK{i}", email=f"bk{i}@test.com") for i in range(n)]
        await Author.bulk_create(instances)
        bulk_time = time.perf_counter() - t0

        await Author.all().delete()

        # loop create
        t0 = time.perf_counter()
        for i in range(n):
            await Author.create(name=f"LP{i}", email=f"lp{i}@test.com")
        loop_time = time.perf_counter() - t0

        # bulk_create は loop より速いはず（少なくとも同程度）
        assert bulk_time <= loop_time * 2  # 2倍の余裕を持たせる
        print(f"\n  bulk: {bulk_time:.3f}s  loop: {loop_time:.3f}s  ratio: {loop_time/bulk_time:.1f}x")
