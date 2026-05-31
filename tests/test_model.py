"""
モデル定義・ColumnMeta・QuerySet SQL 生成のユニットテスト
（DB 接続不要）
"""

import pytest
from conftest import Author, Post


class TestColumnMetaOperators:
    def test_eq(self):
        clause = Post.views == 100
        assert "views" in clause.sql and "= %s" in clause.sql
        assert clause.params == [100]

    def test_ne(self):
        clause = Post.views != 100
        assert "!=" in clause.sql
        assert clause.params == [100]

    def test_gte(self):
        clause = Post.views >= 100
        assert ">=" in clause.sql
        assert clause.params == [100]

    def test_lte(self):
        clause = Post.views <= 100
        assert "<=" in clause.sql

    def test_gt(self):
        clause = Post.views > 100
        assert "> %s" in clause.sql

    def test_lt(self):
        clause = Post.views < 100
        assert "< %s" in clause.sql

    def test_and(self):
        clause = (Post.views >= 10) & (Post.published == True)  # noqa: E712
        assert "AND" in clause.sql

    def test_or(self):
        clause = (Post.views >= 10) | (Post.published == True)  # noqa: E712
        assert "OR" in clause.sql

    def test_invert(self):
        clause = ~(Post.views >= 10)
        assert "NOT" in clause.sql

    def test_is_null(self):
        clause = Post.score == None  # noqa: E711
        assert "IS NULL" in clause.sql
        assert clause.params == []

    def test_is_not_null(self):
        clause = Post.score != None  # noqa: E711
        assert "IS NOT NULL" in clause.sql

    def test_like(self):
        clause = Author.name.like("A%")
        assert "LIKE" in clause.sql
        assert clause.params == ["A%"]

    def test_ilike(self):
        clause = Author.name.ilike("a%")
        assert "ILIKE" in clause.sql

    def test_in(self):
        clause = Post.views.in_([1, 2, 3])
        assert "IN" in clause.sql
        assert len(clause.params) == 3

    def test_not_in(self):
        clause = Post.views.not_in([1, 2])
        assert "NOT IN" in clause.sql

    def test_between(self):
        clause = Post.score.between(1.0, 5.0)
        assert "BETWEEN" in clause.sql
        assert clause.params == [1.0, 5.0]

    def test_asc(self):
        assert "ASC" in Post.views.asc

    def test_desc(self):
        assert "DESC" in Post.views.desc

    def test_column_compare(self):
        cc = Post.author_id == Author.id
        assert hasattr(cc, "sql")
        assert "post.author_id" in cc.sql
        assert "author.id" in cc.sql


class TestQuerySetSqlGeneration:
    def test_select_all(self):
        sql, _ = Post.all()._build_sql()
        assert "SELECT *" in sql
        assert "FROM post" in sql

    def test_where(self):
        sql, params = Post.where(Post.views >= 100)._build_sql()
        assert "WHERE" in sql
        assert "views" in sql
        assert 100 in params

    def test_multiple_wheres_and(self):
        sql, _ = Post.where(Post.views >= 10).where(Post.published == True)._build_sql()  # noqa: E712
        assert "AND" in sql

    def test_order_by(self):
        sql, _ = Post.all().order_by(Post.views.desc)._build_sql()
        assert "ORDER BY" in sql

    def test_limit_offset(self):
        sql, _ = Post.all().limit(10).offset(5)._build_sql()
        assert "LIMIT 10" in sql
        assert "OFFSET 5" in sql

    def test_select_cols(self):
        sql, _ = Post.all().select(Post.title, Post.views)._build_sql()
        assert "SELECT post.title, post.views" in sql
        assert "*" not in sql

    def test_group_by(self):
        from kakaorm import Count
        sql, _ = Post.all().select(Post.author_id, Count(Post.id)).group_by(Post.author_id)._build_sql()
        assert "GROUP BY" in sql
        assert "COUNT" in sql

    def test_having(self):
        from kakaorm import Count
        sql, params = (
            Post.all()
                .select(Post.author_id, Count(Post.id).label("cnt"))
                .group_by(Post.author_id)
                .having(Count(Post.id) >= 2)
                ._build_sql()
        )
        assert "HAVING" in sql
        assert 2 in params

    def test_inner_join(self):
        sql, _ = Post.all().join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "INNER JOIN" in sql
        assert "ON post.author_id = author.id" in sql

    def test_left_join(self):
        sql, _ = Post.all().left_join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "LEFT JOIN" in sql

    def test_right_join(self):
        sql, _ = Post.all().right_join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "RIGHT JOIN" in sql

    def test_join_uses_qualified_wildcard(self):
        sql, _ = Post.all().join(Author, on=Post.author_id == Author.id)._build_sql()
        assert "post.*" in sql

    def test_complex_query(self):
        sql, params = (
            Post.where(Post.views >= 100)
                .order_by(Post.views.desc)
                .limit(10)
                .offset(5)
                ._build_sql()
        )
        assert "SELECT" in sql
        assert "WHERE" in sql
        assert "ORDER BY" in sql
        assert "LIMIT 10" in sql
        assert "OFFSET 5" in sql
        assert 100 in params


class TestModelInstantiation:
    def test_defaults(self):
        post = Post(title="Test")
        assert post.title == "Test"
        assert post.published == False  # noqa: E712
        assert post.views == 0

    def test_unknown_field_raises(self):
        with pytest.raises(TypeError):
            Post(unknown_field="oops")

    def test_to_dict(self):
        post = Post(title="Dict Test", views=5)
        d = post.to_dict()
        assert d["title"] == "Dict Test"
        assert d["views"] == 5
        assert "published" in d
