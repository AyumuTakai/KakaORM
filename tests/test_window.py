"""
ウィンドウ関数テスト
====================
ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, 集計ウィンドウ
"""

from __future__ import annotations

import pytest

from kakaorm import (
    RowNumber,
    Rank,
    DenseRank,
    Lag,
    Lead,
    Sum,
    Avg,
    Count,
    Max,
    Min,
)
from tests.conftest import Author, Post


@pytest.mark.asyncio
class TestWindowFunctions:
    """ウィンドウ関数のテスト"""

    async def test_row_number_basic(self, engine):
        """ROW_NUMBER() の基本テスト"""
        # サンプルデータ
        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)
        await Post.create(title="Post 3", views=150)

        # ROW_NUMBER
        rows = await (
            Post.all()
            .select(Post.title, RowNumber().over(order_by=[Post.views.desc]).label("rn"))
            .execute()
        )

        assert len(rows) == 3
        # 最初の row は dict になる（ウィンドウ関数を含む）
        if isinstance(rows[0], dict):
            assert rows[0]["rn"] == 1
            assert rows[1]["rn"] == 2
            assert rows[2]["rn"] == 3

    async def test_rank_with_ties(self, engine):
        """RANK() の同一値のテスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=100)
        await Post.create(title="Post 3", views=150)

        rows = await (
            Post.all()
            .select(Post.title, Rank().over(order_by=[Post.views.desc]).label("rank"))
            .execute()
        )

        assert len(rows) == 3

    async def test_dense_rank(self, engine):
        """DENSE_RANK() のテスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=100)
        await Post.create(title="Post 3", views=150)

        rows = await (
            Post.all()
            .select(Post.title, DenseRank().over(order_by=[Post.views.desc]).label("drank"))
            .execute()
        )

        assert len(rows) == 3

    async def test_window_with_partition(self, engine):
        """PARTITION BY を使ったウィンドウ関数"""

        await Post.create(title="A1", views=100)
        await Post.create(title="A2", views=200)
        await Post.create(title="B1", views=150)

        rows = await (
            Post.all()
            .select(
                Post.author_id,
                Post.title,
                RowNumber()
                .over(
                    partition_by=[Post.author_id],
                    order_by=[Post.views.desc]
                )
                .label("rn")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_lag_basic(self, engine):
        """LAG() の基本テスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)
        await Post.create(title="Post 3", views=150)

        rows = await (
            Post.all()
            .select(
                Post.title,
                Post.views,
                Lag(Post.views).over(order_by=[Post.views.asc]).label("prev_views")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_lag_with_default(self, engine):
        """LAG() のデフォルト値テスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)

        rows = await (
            Post.all()
            .select(
                Post.title,
                Lag(Post.views, offset=1, default=0)
                .over(order_by=[Post.views.asc])
                .label("prev_views")
            )
            .execute()
        )

        assert len(rows) == 2

    async def test_lead_basic(self, engine):
        """LEAD() の基本テスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)
        await Post.create(title="Post 3", views=150)

        rows = await (
            Post.all()
            .select(
                Post.title,
                Post.views,
                Lead(Post.views).over(order_by=[Post.views.asc]).label("next_views")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_lag_lead_order_by(self, engine):
        """LAG/LEAD の ORDER BY テスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)

        rows = await (
            Post.all()
            .select(
                Post.title,
                Post.views,
                Lag(Post.views).over(order_by=[Post.id.asc]).label("prev_views"),
                Lead(Post.views).over(order_by=[Post.id.asc]).label("next_views")
            )
            .execute()
        )

        assert len(rows) == 2

    async def test_sum_over_partition(self, engine):
        """SUM() OVER (PARTITION BY) ウィンドウ集計"""

        await Post.create(title="A1", views=100)
        await Post.create(title="A2", views=200)
        await Post.create(title="B1", views=150)

        rows = await (
            Post.all()
            .select(
                Post.author_id,
                Post.title,
                Post.views,
                Sum(Post.views)
                .over(partition_by=[Post.author_id])
                .label("author_total")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_avg_over_partition(self, engine):
        """AVG() OVER (PARTITION BY) ウィンドウ集計"""

        await Post.create(title="A1", views=100)
        await Post.create(title="A2", views=200)
        await Post.create(title="B1", views=150)

        rows = await (
            Post.all()
            .select(
                Post.author_id,
                Post.views,
                Avg(Post.views)
                .over(partition_by=[Post.author_id])
                .label("author_avg")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_min_max_over(self, engine):
        """MIN() / MAX() OVER ウィンドウ集計"""

        await Post.create(title="A1", views=100)
        await Post.create(title="A2", views=200)
        await Post.create(title="B1", views=150)

        rows = await (
            Post.all()
            .select(
                Post.author_id,
                Post.views,
                Min(Post.views)
                .over(partition_by=[Post.author_id])
                .label("author_min"),
                Max(Post.views)
                .over(partition_by=[Post.author_id])
                .label("author_max")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_multiple_windows(self, engine):
        """複数のウィンドウ関数を組み合わせたテスト"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)
        await Post.create(title="Post 3", views=150)

        rows = await (
            Post.all()
            .select(
                Post.title,
                Post.views,
                RowNumber().over(order_by=[Post.views.desc]).label("global_rn"),
                RowNumber()
                .over(partition_by=[Post.author_id], order_by=[Post.views.desc])
                .label("author_rn")
            )
            .execute()
        )

        assert len(rows) == 3

    async def test_window_with_where_clause(self, engine):
        """WHERE 句と組み合わせたウィンドウ関数"""

        await Post.create(title="Post 1", views=100)
        await Post.create(title="Post 2", views=200)
        await Post.create(title="Post 3", views=50)

        rows = await (
            Post.where(Post.views >= 100)
            .select(
                Post.title,
                Post.views,
                RowNumber().over(order_by=[Post.views.desc]).label("rn")
            )
            .execute()
        )

        # views >= 100 を満たすのは Post 1, Post 2
        assert len(rows) == 2
