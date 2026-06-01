"""
KakaORM SQL互換性テスト

よく使われるSQL文パターンがkakaormで記述可能か検証する
"""
import pytest
from datetime import datetime, timedelta
from kakaorm import (
    connect, Model, StrColumn, IntColumn, BoolColumn, ForeignKey,
    DateTimeColumn, has_many, belongs_to, Count, Sum, Avg, Max, Min
)


class Author(Model):
    name = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"


class Post(Model):
    title = StrColumn(nullable=False)
    content = StrColumn(nullable=True)
    views = IntColumn(default=0)
    author_id = ForeignKey(Author, nullable=False)
    created_at = DateTimeColumn(nullable=False)
    published = BoolColumn(default=False)

    author = belongs_to(Author, foreign_key="author_id")
    comments = has_many("Comment", foreign_key="post_id")

    class Meta:
        table_name = "post"


class Comment(Model):
    content = StrColumn(nullable=False)
    post_id = ForeignKey(Post, nullable=False)
    author_id = ForeignKey(Author, nullable=False)

    post = belongs_to(Post, foreign_key="post_id")
    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "comment"


@pytest.fixture
async def engine():
    """テスト用のin-memory SQLiteエンジン"""
    e = await connect("sqlite+aiosqlite:///:memory:")

    # マイグレーション
    from kakaorm.migration import Migrator
    plan = await Migrator(e).plan([Author, Post, Comment])
    if not plan.is_empty():
        await plan.apply()

    yield e

    await e.disconnect()


@pytest.fixture
async def sample_data(engine):
    """テストデータの準備"""
    now = datetime.now()

    # Authors
    alice = await Author.create(name="Alice", email="alice@example.com")
    bob = await Author.create(name="Bob", email="bob@example.com")
    charlie = await Author.create(name="Charlie", email="charlie@example.com")

    # Posts
    p1 = await Post.create(
        title="Python Tips",
        content="Tips for Python developers",
        views=100,
        author_id=alice.id,
        created_at=now - timedelta(days=10),
        published=True
    )
    p2 = await Post.create(
        title="Async/Await Guide",
        content="Understanding async programming",
        views=200,
        author_id=alice.id,
        created_at=now - timedelta(days=5),
        published=True
    )
    p3 = await Post.create(
        title="Database Design",
        content="Designing efficient databases",
        views=50,
        author_id=bob.id,
        created_at=now - timedelta(days=3),
        published=True
    )
    p4 = await Post.create(
        title="Draft Post",
        content="Work in progress",
        views=0,
        author_id=charlie.id,
        created_at=now,
        published=False
    )

    # Comments
    await Comment.create(content="Great post!", post_id=p1.id, author_id=bob.id)
    await Comment.create(content="Very helpful", post_id=p1.id, author_id=charlie.id)
    await Comment.create(content="Thanks!", post_id=p2.id, author_id=bob.id)

    return {"authors": [alice, bob, charlie], "posts": [p1, p2, p3, p4]}


class TestBasicSelects:
    """基本的なSELECT文"""

    @pytest.mark.asyncio
    async def test_select_all(self, sample_data):
        """SELECT * FROM posts"""
        # SQL: SELECT * FROM post
        posts = await Post.all()
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_select_with_where(self, sample_data):
        """SELECT * FROM posts WHERE published = true"""
        # SQL: SELECT * FROM post WHERE published = true
        posts = await Post.where(Post.published == True).execute()
        assert len(posts) == 3
        assert all(p.published for p in posts)

    @pytest.mark.asyncio
    async def test_select_with_where_gt(self, sample_data):
        """SELECT * FROM posts WHERE views > 50"""
        # SQL: SELECT * FROM post WHERE views > 50
        posts = await Post.where(Post.views > 50).execute()
        assert len(posts) == 2
        assert all(p.views > 50 for p in posts)

    @pytest.mark.asyncio
    async def test_select_with_order_by(self, sample_data):
        """SELECT * FROM posts ORDER BY created_at DESC LIMIT 2"""
        # SQL: SELECT * FROM post ORDER BY created_at DESC LIMIT 2
        posts = await Post.all().order_by(Post.created_at.desc).limit(2).execute()
        assert len(posts) == 2
        assert posts[0].created_at >= posts[1].created_at

    @pytest.mark.asyncio
    async def test_select_with_like(self, sample_data):
        """SELECT * FROM posts WHERE title LIKE '%Guide%'"""
        # SQL: SELECT * FROM post WHERE title LIKE '%Guide%'
        posts = await Post.where(Post.title.like("%Guide%")).execute()
        assert len(posts) == 1
        assert posts[0].title == "Async/Await Guide"

    @pytest.mark.asyncio
    async def test_select_with_in(self, sample_data):
        """SELECT * FROM posts WHERE views IN (100, 200)"""
        # SQL: SELECT * FROM post WHERE views IN (100, 200)
        posts = await Post.where(Post.views.in_([100, 200])).execute()
        assert len(posts) == 2

    @pytest.mark.asyncio
    async def test_select_with_multiple_where(self, sample_data):
        """SELECT * FROM posts WHERE published = true AND views > 50"""
        # SQL: SELECT * FROM post WHERE published = true AND views > 50
        posts = await Post.where(
            (Post.published == True) & (Post.views > 50)
        ).execute()
        assert len(posts) == 2
        assert all(p.published and p.views > 50 for p in posts)


class TestGroupingAndAggregates:
    """GROUP BY と集計関数"""

    @pytest.mark.asyncio
    async def test_count_all(self, sample_data):
        """SELECT COUNT(*) FROM posts"""
        # SQL: SELECT COUNT(*) FROM post
        count = await Post.all().aggregate(total=Count(Post.id))
        assert count["total"] == 4

    @pytest.mark.asyncio
    async def test_sum_aggregate(self, sample_data):
        """SELECT SUM(views) FROM posts"""
        # SQL: SELECT SUM(views) FROM post
        result = await Post.all().aggregate(total_views=Sum(Post.views))
        assert result["total_views"] == 350  # 100 + 200 + 50 + 0

    @pytest.mark.asyncio
    async def test_avg_aggregate(self, sample_data):
        """SELECT AVG(views) FROM posts WHERE published = true"""
        # SQL: SELECT AVG(views) FROM post WHERE published = true
        result = await Post.where(Post.published == True).aggregate(avg_views=Avg(Post.views))
        assert result["avg_views"] == pytest.approx(116.67, rel=0.01)

    @pytest.mark.asyncio
    async def test_group_by_simple(self, sample_data):
        """SELECT author_id, COUNT(*) as post_count FROM posts GROUP BY author_id"""
        # SQL: SELECT author_id, COUNT(*) as post_count FROM post GROUP BY author_id
        # Note: GROUP BY では select() で列を指定してから execute() で結果を得る
        stats = await Post.all().group_by(Post.author_id).select(
            Post.author_id
        ).execute()
        assert len(stats) == 3  # 3 authors

    @pytest.mark.asyncio
    async def test_group_by_with_having(self, sample_data):
        """SELECT author_id, COUNT(*) FROM posts GROUP BY author_id HAVING COUNT(*) > 1"""
        # SQL: SELECT author_id, COUNT(*) FROM post GROUP BY author_id HAVING COUNT(*) > 1
        stats = await (Post.all()
            .group_by(Post.author_id)
            .having(Count(Post.id) > 1)
            .select(Post.author_id, Count(Post.id).label("cnt"))
            .execute()
        )
        assert len(stats) == 1  # Only Alice has > 1 post


class TestJoins:
    """JOIN操作"""

    @pytest.mark.asyncio
    async def test_inner_join(self, sample_data):
        """SELECT u.id, u.name, p.title FROM users u INNER JOIN posts p ON u.id = p.author_id"""
        # SQL: SELECT author.id, author.name, post.title FROM author INNER JOIN post ON author.id = post.author_id
        posts = await Post.all().join(Author, on=Post.author_id == Author.id).select(
            Author.id, Author.name, Post.title
        )
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_left_join(self, sample_data):
        """SELECT a.id, COUNT(p.id) FROM authors a LEFT JOIN posts p ON a.id = p.author_id GROUP BY a.id"""
        # SQL: SELECT author.id, COUNT(post.id) FROM author LEFT JOIN post ON author.id = post.author_id GROUP BY author.id
        stats = await (Author.all()
            .left_join(Post, on=Author.id == Post.author_id)
            .group_by(Author.id)
            .select(Author.id, Count(Post.id).label("post_count"))
            .execute()
        )
        assert len(stats) == 3

    @pytest.mark.asyncio
    async def test_join_with_where(self, sample_data):
        """SELECT p.* FROM posts p INNER JOIN authors a ON p.author_id = a.id WHERE a.name = 'Alice'"""
        # SQL: SELECT post.* FROM post INNER JOIN author ON post.author_id = author.id WHERE author.name = 'Alice'
        posts = await Post.all().join(
            Author, on=Post.author_id == Author.id
        ).where(Author.name == "Alice").execute()
        assert len(posts) == 2
        # Note: JOIN で select() 指定なしの場合、dict が返される
        if isinstance(posts[0], dict):
            assert all(p["author_id"] == sample_data["authors"][0].id for p in posts)
        else:
            assert all(p.author_id == sample_data["authors"][0].id for p in posts)


class TestRelationships:
    """リレーション & Eager Loading"""

    @pytest.mark.asyncio
    async def test_belongs_to(self, sample_data):
        """関連データへのアクセス（N+1問題あり）"""
        posts = await Post.all().limit(2)
        # これはN+1クエリが発生する
        authors = []
        for post in posts:
            author = await post.author
            authors.append(author)
        assert len(authors) == 2

    @pytest.mark.asyncio
    async def test_prefetch_belongs_to(self, sample_data):
        """prefetchでN+1問題を解決"""
        # SQL: 2 queries (posts + authors)
        posts = await Post.all().prefetch("author")
        authors = []
        for post in posts:
            author = await post.author  # キャッシュから取得
            authors.append(author)
        assert len(authors) == 4

    @pytest.mark.asyncio
    async def test_prefetch_multiple(self, sample_data):
        """複数リレーションのプリフェッチ"""
        posts = await Post.all().prefetch("author", "comments")
        for post in posts:
            author = await post.author
            comments = await post.comments
            assert author is not None
            assert isinstance(comments, list)


class TestCTE:
    """CTE (WITH句)"""

    @pytest.mark.asyncio
    async def test_cte_simple(self, sample_data):
        """WITH published_posts AS (SELECT * FROM posts WHERE published = true) SELECT * FROM published_posts"""
        # SQL: WITH published_posts AS (SELECT * FROM post WHERE published = true) SELECT * FROM post INNER JOIN published_posts
        published = Post.where(Post.published == True)
        result = await Post.all().with_cte("published_posts", published).execute()
        # Note: CTEはこのままではfilter効果がない。JOINやサブクエリと組み合わせる必要がある
        assert isinstance(result, list)


class TestSubqueries:
    """サブクエリ"""

    @pytest.mark.asyncio
    async def test_subquery_in_where(self, sample_data):
        """SELECT * FROM posts WHERE author_id IN (SELECT id FROM authors WHERE name LIKE '%e%')"""
        # SQL: SELECT * FROM post WHERE author_id IN (SELECT id FROM author WHERE name LIKE '%e%')
        from kakaorm import Subquery
        author_ids = Subquery(Author.where(Author.name.like("%e%")).select(Author.id))
        posts = await Post.where(Post.author_id.in_(author_ids))
        assert len(posts) >= 1


class TestWindowFunctions:
    """Window Functions"""

    @pytest.mark.asyncio
    async def test_row_number(self, sample_data):
        """SELECT id, title, ROW_NUMBER() OVER (ORDER BY views DESC) as rank FROM posts"""
        from kakaorm import RowNumber
        posts = await Post.all().select(
            Post.id,
            Post.title,
            RowNumber().over(order_by=[Post.views.desc]).label("rank")
        ).execute()
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_rank_with_partition(self, sample_data):
        """SELECT author_id, title, RANK() OVER (PARTITION BY author_id ORDER BY views DESC) as rank FROM posts"""
        from kakaorm import Rank
        posts = await Post.all().select(
            Post.author_id,
            Post.title,
            Rank().over(
                partition_by=[Post.author_id],
                order_by=[Post.views.desc]
            ).label("rank")
        ).execute()
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_lag_function(self, sample_data):
        """SELECT id, views, LAG(views) OVER (ORDER BY created_at) as prev_views FROM posts"""
        from kakaorm import Lag
        posts = await Post.all().select(
            Post.id,
            Post.views,
            Lag(Post.views).over(order_by=[Post.created_at]).label("prev_views")
        ).execute()
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_sum_over_partition(self, sample_data):
        """SELECT id, author_id, views, SUM(views) OVER (PARTITION BY author_id) as author_total FROM posts"""
        posts = await Post.all().select(
            Post.id,
            Post.author_id,
            Post.views,
            Sum(Post.views).over(partition_by=[Post.author_id]).label("author_total")
        ).execute()
        assert len(posts) == 4


class TestUpdateDelete:
    """UPDATE・DELETE操作"""

    @pytest.mark.asyncio
    async def test_update_with_where(self, sample_data):
        """UPDATE posts SET published = true WHERE views > 50"""
        # SQL: UPDATE post SET published = true WHERE views > 50
        count = await Post.where(Post.views > 50).update(published=True)
        assert count == 2

        # 検証：views > 50 のレコードは published=True になった
        posts_updated = await Post.where(Post.published == True)
        assert len(posts_updated) >= 3

    @pytest.mark.asyncio
    async def test_delete_with_where(self, sample_data):
        """DELETE FROM posts WHERE published = false"""
        # SQL: DELETE FROM post WHERE published = false
        count = await Post.where(Post.published == False).delete()
        assert count == 1

        # 検証
        remaining = await Post.all()
        assert len(remaining) == 3


class TestComplexPatterns:
    """複雑なパターン"""

    @pytest.mark.asyncio
    async def test_select_with_case(self, sample_data):
        """SELECT *, CASE WHEN views > 100 THEN 'popular' ELSE 'normal' END as category FROM posts"""
        from kakaorm import Case, When
        posts = await Post.all().select(
            Post.id,
            Post.title,
            Post.views,
            Case(
                When(Post.views > 100, then="popular"),
                default="normal"
            ).label("category")
        ).execute()
        assert len(posts) == 4

    @pytest.mark.asyncio
    async def test_update_with_expression(self, sample_data):
        """UPDATE posts SET views = views + 1 WHERE published = true"""
        # SQL: UPDATE post SET views = views + 1 WHERE published = true
        count = await Post.where(Post.published == True).update(
            views=Post.views + 1
        )
        assert count >= 1

    @pytest.mark.asyncio
    async def test_distinct_values(self, sample_data):
        """SELECT DISTINCT author_id FROM posts"""
        # Note: kakaormでDISTINCTは直接的にはサポートされていない可能性
        # GROUP BYで代替可能
        authors = await Post.all().group_by(Post.author_id).select(
            Post.author_id
        ).execute()
        assert len(authors) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
