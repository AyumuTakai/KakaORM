"""
サブクエリ テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn, BoolColumn, ForeignKey
from kakaorm.query import Subquery


class SqAuthor(Model):
    name      = StrColumn(nullable=False)
    is_active = BoolColumn(nullable=False, default=True)

    class Meta:
        table_name = "sq_author"


class SqPost(Model):
    title     = StrColumn(nullable=False)
    views     = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(SqAuthor, nullable=True)

    class Meta:
        table_name = "sq_post"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(SqAuthor)
    await eng.create_table(SqPost)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    alice = await SqAuthor.create(name="Alice", is_active=True)
    bob   = await SqAuthor.create(name="Bob",   is_active=False)
    charlie = await SqAuthor.create(name="Charlie", is_active=True)

    await SqPost.create(title="Alice Post 1", author_id=alice.id,   views=100)
    await SqPost.create(title="Alice Post 2", author_id=alice.id,   views=200)
    await SqPost.create(title="Bob Post",     author_id=bob.id,     views=50)
    await SqPost.create(title="Charlie Post", author_id=charlie.id, views=300)
    return {"alice": alice, "bob": bob, "charlie": charlie}


class TestInSubquery:
    async def test_in_with_queryset(self, seeded):
        """QuerySet を直接 in_() に渡せること。"""
        active_ids = SqAuthor.where(SqAuthor.is_active == True).select(SqAuthor.id)
        posts = await SqPost.where(SqPost.author_id.in_(active_ids))
        titles = {p.title for p in posts}
        assert "Alice Post 1" in titles
        assert "Alice Post 2" in titles
        assert "Charlie Post" in titles
        assert "Bob Post" not in titles

    async def test_in_with_subquery_wrapper(self, seeded):
        """Subquery() でラップしても同じ結果になること。"""
        active_ids = SqAuthor.where(SqAuthor.is_active == True).select(SqAuthor.id)
        posts = await SqPost.where(SqPost.author_id.in_(Subquery(active_ids)))
        assert len(posts) == 3

    async def test_not_in_with_queryset(self, seeded):
        """not_in() にサブクエリを渡せること。"""
        active_ids = SqAuthor.where(SqAuthor.is_active == True).select(SqAuthor.id)
        posts = await SqPost.where(SqPost.author_id.not_in(active_ids))
        assert len(posts) == 1
        assert posts[0].title == "Bob Post"

    async def test_subquery_with_where_and_select(self, seeded):
        """サブクエリ側に WHERE と SELECT を組み合わせられること。"""
        high_view_ids = (
            SqAuthor.where(SqAuthor.is_active == True)
                    .select(SqAuthor.id)
        )
        # 高 views の記事の author_id が high_view_ids に含まれるもの
        posts = await (
            SqPost.where(SqPost.views >= 200)
                  .where(SqPost.author_id.in_(high_view_ids))
        )
        assert len(posts) == 2
        titles = {p.title for p in posts}
        assert "Alice Post 2" in titles
        assert "Charlie Post" in titles

    async def test_subquery_params_passed_correctly(self, seeded):
        """サブクエリのバインドパラメータが正しく伝播すること。"""
        # is_active == True の著者 (バインドパラメータあり) の ID に絞り込む
        active_ids = SqAuthor.where(SqAuthor.is_active == True).select(SqAuthor.id)
        count = await SqPost.where(SqPost.author_id.in_(active_ids)).count()
        assert count == 3

    async def test_subquery_repr(self, seeded):
        qs = SqAuthor.where(SqAuthor.is_active == True).select(SqAuthor.id)
        sub = Subquery(qs)
        assert "Subquery" in repr(sub)
        assert "sq_author" in repr(sub)

    async def test_in_list_still_works(self, seeded):
        """リストを渡す従来の in_() が引き続き動作すること。"""
        posts = await SqPost.where(SqPost.views.in_([100, 200]))
        assert len(posts) == 2
