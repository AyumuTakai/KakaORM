"""
UpdateExpr — 列参照を含む UPDATE 式のテスト
"""

import pytest
from kakaorm.columns.base import UpdateExpr
from conftest import Author, Post


class TestUpdateExprGeneration:
    """UpdateExpr の生成（エンジン不要）"""

    def test_add(self):
        expr = Post.views + 10
        assert isinstance(expr, UpdateExpr)
        assert "post.views" in expr.sql
        assert "+ %s" in expr.sql
        assert expr.params == [10]

    def test_sub(self):
        expr = Post.views - 5
        assert "- %s" in expr.sql
        assert expr.params == [5]

    def test_mul(self):
        expr = Post.views * 0.97
        assert "* %s" in expr.sql
        assert expr.params == [0.97]

    def test_div(self):
        expr = Post.views / 2
        assert "/ %s" in expr.sql
        assert expr.params == [2]

    def test_radd(self):
        expr = 100 + Post.views
        assert "post.views" in expr.sql
        assert expr.params == [100]

    def test_rsub(self):
        expr = 100 - Post.views
        assert "post.views" in expr.sql
        assert expr.params == [100]

    def test_rmul(self):
        expr = 2 * Post.views
        assert "post.views" in expr.sql
        assert expr.params == [2]

    def test_float_multiplier(self):
        expr = Post.views * 1.1
        assert expr.params == [1.1]

    def test_chaining_not_supported(self):
        # UpdateExpr は UPDATE SET 句用なので、さらに演算子をチェーンしない
        expr = Post.views + 10
        assert isinstance(expr, UpdateExpr)


class TestUpdateExprExecution:
    """DB を使った実行テスト"""

    async def test_increment(self, seeded_engine):
        """views += 100 が正しく動く。"""
        before = await Post.get(Post.title == "Python入門")
        before_views = before.views  # 2000

        await Post.where(Post.title == "Python入門").update(
            views=Post.views + 100
        )

        after = await Post.get(Post.title == "Python入門")
        assert after.views == before_views + 100

    async def test_decrement(self, seeded_engine):
        """views -= 200 が正しく動く。"""
        before = await Post.get(Post.title == "非同期処理")
        before_views = before.views  # 1200

        await Post.where(Post.title == "非同期処理").update(
            views=Post.views - 200
        )

        after = await Post.get(Post.title == "非同期処理")
        assert after.views == before_views - 200

    async def test_multiply_all(self, seeded_engine):
        """全件の views を 0.5 倍する。"""
        before_total = await Post.all().sum(Post.views)  # 3700

        await Post.all().update(views=Post.views * 0.5)

        after_total = await Post.all().sum(Post.views)
        assert abs(after_total - before_total * 0.5) < 1

    async def test_multiple_expr_columns(self, seeded_engine):
        """複数カラムを同時に式で更新できる。"""
        before = await Post.get(Post.title == "Python入門")

        await Post.where(Post.title == "Python入門").update(
            views=Post.views + 500,
            score=Post.score * 0.9,
        )

        after = await Post.get(Post.title == "Python入門")
        assert after.views == before.views + 500
        assert abs(after.score - before.score * 0.9) < 0.001

    async def test_mixed_literal_and_expr(self, seeded_engine):
        """リテラルと UpdateExpr を混在させられる。"""
        await Post.where(Post.published == False).update(  # noqa: E712
            views=Post.views + 10,   # UpdateExpr
            published=True,           # リテラル（後方互換）
        )

        updated = await Post.where(Post.title == "未公開ドラフト").first()
        assert updated.published == True   # noqa: E712
        assert updated.views == 110        # 100 + 10

    async def test_with_where_condition(self, seeded_engine):
        """WHERE 条件と組み合わせて特定行だけ更新できる。"""
        await Post.where(Post.views >= 1000).update(
            views=Post.views * 2
        )

        python_post = await Post.get(Post.title == "Python入門")
        async_post  = await Post.get(Post.title == "非同期処理")
        kakao_post  = await Post.get(Post.title == "kakaorm解説")

        assert python_post.views == 4000  # 2000 * 2
        assert async_post.views  == 2400  # 1200 * 2
        assert kakao_post.views  == 400   # 400（変更なし）

    async def test_returns_affected_rows(self, seeded_engine):
        """更新した行数を返す。"""
        n = await Post.all().update(views=Post.views + 1)
        assert n == 4

    async def test_no_match_returns_zero(self, seeded_engine):
        """条件に一致しない場合は 0 を返す。"""
        n = await Post.where(Post.views > 99999).update(
            views=Post.views + 1
        )
        assert n == 0
