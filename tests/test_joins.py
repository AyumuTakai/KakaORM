"""
JOIN テスト（INNER / LEFT / RIGHT）
"""

from kakaorm import Count, Sum
from conftest import Author, Post


class TestInnerJoin:
    async def test_inner_join_basic(self, seeded_engine):
        rows = await (
            Post.all()
                .join(Author, on=Post.author_id == Author.id)
                .select(Post.title, Post.views, Author.name)
        )
        assert isinstance(rows, list)
        assert len(rows) == 4
        assert "title" in rows[0]
        assert "name" in rows[0]

    async def test_inner_join_with_filter(self, seeded_engine):
        rows = await (
            Post.filter(Post.published == True)  # noqa: E712
                .join(Author, on=Post.author_id == Author.id)
                .select(Post.title, Post.views, Author.name)
                .order_by(Post.views.desc)
        )
        assert len(rows) == 3
        assert rows[0]["views"] == 2000

    async def test_inner_join_returns_dict(self, seeded_engine):
        rows = await (
            Post.all()
                .join(Author, on=Post.author_id == Author.id)
        )
        assert isinstance(rows[0], dict)

    async def test_inner_join_author_name_present(self, seeded_engine):
        rows = await (
            Post.filter(Post.title == "Python入門")
                .join(Author, on=Post.author_id == Author.id)
                .select(Post.title, Author.name)
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"


class TestLeftJoin:
    async def test_left_join_includes_all_posts(self, seeded_engine):
        rows = await (
            Post.all()
                .left_join(Author, on=Post.author_id == Author.id)
                .select(Post.title, Author.name)
        )
        assert len(rows) == 4

    async def test_left_join_sql(self):
        sql, _ = Post.all().left_join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "LEFT JOIN" in sql
        assert "ON post.author_id = author.id" in sql


class TestRightJoin:
    def test_right_join_sql(self):
        sql, _ = Post.all().right_join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "RIGHT JOIN" in sql


class TestJoinWithGroupBy:
    async def test_join_group_by(self, seeded_engine):
        rows = await (
            Post.filter(Post.published == True)  # noqa: E712
                .join(Author, on=Post.author_id == Author.id)
                .select(Author.name, Count(Post.id).label("post_count"))
                .group_by(Author.name)
                .order_by(Count(Post.id).desc)
        )
        assert len(rows) >= 1
        assert rows[0]["post_count"] >= 1

    async def test_join_group_by_sum(self, seeded_engine):
        rows = await (
            Post.all()
                .join(Author, on=Post.author_id == Author.id)
                .select(Author.name, Sum(Post.views).label("total_views"))
                .group_by(Author.name)
                .order_by(Sum(Post.views).desc)
        )
        names = [r["name"] for r in rows]
        assert "Alice" in names
