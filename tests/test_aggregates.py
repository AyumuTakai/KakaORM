"""
集計関数 / GROUP BY / HAVING テスト
"""

from kakaorm import Avg, Count, Max, Min, Sum
from conftest import Author, Post


class TestScalarAggregates:
    async def test_sum(self, seeded_engine):
        total = await Post.all().sum(Post.views)
        assert total == 3700

    async def test_avg(self, seeded_engine):
        avg = await Post.all().avg(Post.views)
        assert avg is not None and avg > 0

    async def test_max(self, seeded_engine):
        mx = await Post.all().max(Post.views)
        assert mx == 2000

    async def test_min(self, seeded_engine):
        mn = await Post.all().min(Post.views)
        assert mn == 100

    async def test_sum_with_where(self, seeded_engine):
        total = await Post.where(Post.published == True).sum(Post.views)  # noqa: E712
        assert total == 3600

    async def test_count(self, seeded_engine):
        n = await Post.all().count()
        assert n == 4

    async def test_count_with_where(self, seeded_engine):
        n = await Post.where(Post.published == True).count()  # noqa: E712
        assert n == 3


class TestAggregateMuti:
    async def test_aggregate_multi(self, seeded_engine):
        stats = await Post.where(Post.published == True).aggregate(  # noqa: E712
            total=Sum(Post.views),
            maximum=Max(Post.views),
            cnt=Count(Post.id),
        )
        assert stats["total"] == 3600
        assert stats["maximum"] == 2000
        assert stats["cnt"] == 3

    async def test_aggregate_all(self, seeded_engine):
        stats = await Post.all().aggregate(
            s=Sum(Post.views),
            mn=Min(Post.views),
            mx=Max(Post.views),
        )
        assert stats["s"] == 3700
        assert stats["mn"] == 100
        assert stats["mx"] == 2000


class TestGroupBy:
    async def test_group_by_author(self, seeded_engine):
        rows = await (
            Post.all()
                .select(Post.author_id, Count(Post.id).label("cnt"))
                .group_by(Post.author_id)
        )
        assert isinstance(rows, list)
        counts = {r["author_id"]: r["cnt"] for r in rows}
        assert counts[1] == 3   # Alice
        assert counts[2] == 1   # Bob

    async def test_group_by_having_gte(self, seeded_engine):
        rows = await (
            Post.all()
                .select(Post.author_id, Count(Post.id).label("cnt"))
                .group_by(Post.author_id)
                .having(Count(Post.id) >= 2)
        )
        assert len(rows) == 1
        assert rows[0]["author_id"] == 1

    async def test_group_by_sum_having(self, seeded_engine):
        rows = await (
            Post.where(Post.published == True)  # noqa: E712
                .select(Post.author_id, Sum(Post.views).label("total"))
                .group_by(Post.author_id)
                .having(Sum(Post.views) > 500)
                .order_by(Sum(Post.views).desc)
        )
        assert len(rows) >= 1
        assert rows[0]["total"] > 500

    async def test_select_agg_returns_dict(self, seeded_engine):
        rows = await Post.all().select(Count(Post.id).label("n"))
        assert isinstance(rows, list)
        assert rows[0]["n"] == 4

    async def test_avg_label(self, seeded_engine):
        rows = await (
            Post.all()
                .select(Post.author_id, Avg(Post.views).label("avg_views"))
                .group_by(Post.author_id)
        )
        assert all("avg_views" in r for r in rows)
