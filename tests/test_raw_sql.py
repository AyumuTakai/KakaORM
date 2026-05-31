"""
Raw SQL — engine.fetch() / execute() / fetchval() テスト
"""

import pytest
from conftest import Author, Post


class TestFetch:
    async def test_fetch_all(self, seeded_engine):
        """全件 SELECT が dict のリストで返る。"""
        rows = await seeded_engine.fetch("SELECT * FROM post")
        assert len(rows) == 4
        assert isinstance(rows[0], dict)

    async def test_fetch_with_param(self, seeded_engine):
        """プレースホルダー付き SELECT が動く。"""
        rows = await seeded_engine.fetch(
            "SELECT * FROM post WHERE published = %s", [1]
        )
        assert len(rows) == 3

    async def test_fetch_join(self, seeded_engine):
        """JOIN クエリが動く（ORM では現状 list[dict] が必要）。"""
        rows = await seeded_engine.fetch(
            "SELECT p.title, a.name"
            " FROM post p JOIN author a ON p.author_id = a.id"
            " WHERE p.views > %s"
            " ORDER BY p.views DESC",
            [500],
        )
        assert len(rows) == 2
        assert rows[0]["title"] == "Python入門"
        assert rows[0]["name"] == "Alice"

    async def test_fetch_subquery(self, seeded_engine):
        """サブクエリを含む SELECT が動く。"""
        rows = await seeded_engine.fetch(
            "SELECT * FROM post"
            " WHERE author_id IN (SELECT id FROM author WHERE name = %s)",
            ["Alice"],
        )
        assert len(rows) == 3

    async def test_fetch_no_params(self, seeded_engine):
        """パラメータなしで呼べる。"""
        rows = await seeded_engine.fetch("SELECT id FROM author")
        assert len(rows) == 2

    async def test_fetch_returns_empty_list(self, engine):
        """一致なしのとき空リストを返す。"""
        rows = await engine.fetch(
            "SELECT * FROM author WHERE name = %s", ["NoSuchPerson"]
        )
        assert rows == []


class TestExecute:
    async def test_execute_update(self, seeded_engine):
        """UPDATE の影響行数が返る。"""
        affected = await seeded_engine.execute(
            "UPDATE post SET views = 0 WHERE published = %s", [0]
        )
        assert affected == 1

    async def test_execute_delete(self, seeded_engine):
        """DELETE の影響行数が返る。"""
        affected = await seeded_engine.execute(
            "DELETE FROM post WHERE title = %s", ["未公開ドラフト"]
        )
        assert affected == 1
        remaining = await Post.all().count()
        assert remaining == 3

    async def test_execute_no_match_returns_zero(self, seeded_engine):
        """条件に一致なしのとき 0 を返す。"""
        affected = await seeded_engine.execute(
            "UPDATE post SET views = 0 WHERE views > %s", [99999]
        )
        assert affected == 0

    async def test_execute_update_expr(self, seeded_engine):
        """算術式を含む UPDATE も動く。"""
        await seeded_engine.execute(
            "UPDATE post SET views = views * 2 WHERE published = %s", [1]
        )
        rows = await seeded_engine.fetch(
            "SELECT views FROM post WHERE title = %s", ["Python入門"]
        )
        assert rows[0]["views"] == 4000  # 2000 * 2


class TestFetchval:
    async def test_count(self, seeded_engine):
        """COUNT(*) をスカラーで返す。"""
        n = await seeded_engine.fetchval("SELECT COUNT(*) FROM post")
        assert n == 4

    async def test_count_with_where(self, seeded_engine):
        """条件付き COUNT が動く。"""
        n = await seeded_engine.fetchval(
            "SELECT COUNT(*) FROM post WHERE published = %s", [1]
        )
        assert n == 3

    async def test_max(self, seeded_engine):
        """MAX 集計が動く。"""
        mx = await seeded_engine.fetchval("SELECT MAX(views) FROM post")
        assert mx == 2000

    async def test_sum(self, seeded_engine):
        """SUM 集計が動く。"""
        total = await seeded_engine.fetchval("SELECT SUM(views) FROM post")
        assert total == 3700

    async def test_no_rows_returns_none(self, engine):
        """一致なしのとき None を返す。"""
        val = await engine.fetchval(
            "SELECT MAX(views) FROM post WHERE views > %s", [99999]
        )
        # SQLite: MAX() on empty set → None
        assert val is None


class TestRawSqlWithTransaction:
    async def test_fetch_in_transaction(self, seeded_engine):
        """トランザクション内で fetch が動く。"""
        async with seeded_engine.transaction():
            rows = await seeded_engine.fetch("SELECT * FROM post")
        assert len(rows) == 4

    async def test_execute_in_transaction_commit(self, seeded_engine):
        """トランザクション内の execute がコミットされる。"""
        async with seeded_engine.transaction():
            await seeded_engine.execute(
                "UPDATE post SET views = 9999 WHERE title = %s", ["Python入門"]
            )

        val = await seeded_engine.fetchval(
            "SELECT views FROM post WHERE title = %s", ["Python入門"]
        )
        assert val == 9999

    async def test_execute_in_transaction_rollback(self, seeded_engine):
        """トランザクション内の execute が例外でロールバックされる。"""
        try:
            async with seeded_engine.transaction():
                await seeded_engine.execute(
                    "UPDATE post SET views = 0 WHERE title = %s", ["Python入門"]
                )
                raise RuntimeError("rollback!")
        except RuntimeError:
            pass

        val = await seeded_engine.fetchval(
            "SELECT views FROM post WHERE title = %s", ["Python入門"]
        )
        assert val == 2000  # 変更されていない


class TestRawSqlComplexQueries:
    async def test_case_when(self, seeded_engine):
        """CASE WHEN 式が動く（ORM 未対応機能の代替）。"""
        rows = await seeded_engine.fetch(
            "SELECT title,"
            " CASE WHEN views >= 1000 THEN 'popular' ELSE 'normal' END AS rank"
            " FROM post ORDER BY views DESC"
        )
        assert rows[0]["rank"] == "popular"
        assert rows[-1]["rank"] == "normal"

    async def test_subquery_in_where(self, seeded_engine):
        """NOT IN サブクエリが動く（ORM 未対応機能の代替）。"""
        rows = await seeded_engine.fetch(
            "SELECT * FROM author"
            " WHERE id NOT IN (SELECT author_id FROM post WHERE published = %s)",
            [1],
        )
        # Alice は公開済み記事あり → NOT IN で除外される
        names = [r["name"] for r in rows]
        assert "Alice" not in names
        assert "Bob" in names
