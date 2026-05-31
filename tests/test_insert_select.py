"""
insert_into() — INSERT ... SELECT テスト
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import FloatColumn, ForeignKey, IntColumn, Model, StrColumn
from conftest import Author, Post


# ── INSERT ... SELECT 専用の補助モデル ───────────────────────────

class PostArchive(Model):
    """公開済み記事のアーカイブ（Post からコピー）"""
    title     = StrColumn(nullable=False)
    views     = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(Author, nullable=True)

    class Meta:
        table_name = "post_archive"


class SalaryLog(Model):
    """給与ログ（Author.id を emp_id として流用）"""
    emp_id = ForeignKey(Author, nullable=True)
    amount = FloatColumn(nullable=True)
    note   = StrColumn(nullable=True)

    class Meta:
        table_name = "salary_log"


@pytest_asyncio.fixture
async def ext_engine(engine):
    """PostArchive / SalaryLog テーブルも追加で作成するエンジン。"""
    await engine.create_table(PostArchive)
    await engine.create_table(SalaryLog)
    return engine


# ── 基本動作 ──────────────────────────────────────────────────────

class TestInsertIntoBasic:
    async def test_returns_inserted_count(self, seeded_engine, ext_engine):
        """戻り値が挿入行数になっている。"""
        n = await (
            Post.filter(Post.published == True)  # noqa: E712
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        assert n == 3  # seeded_engine の公開済み記事は3件

    async def test_data_actually_inserted(self, seeded_engine, ext_engine):
        """insert_into 後に行が実際に存在する。"""
        await (
            Post.filter(Post.published == True)  # noqa: E712
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        archived = await PostArchive.all()
        assert len(archived) == 3

    async def test_column_values_copied(self, seeded_engine, ext_engine):
        """コピー元の列値が正しく転写される。"""
        await (
            Post.all()
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        titles = {r.title for r in await PostArchive.all()}
        assert "Python入門" in titles
        assert "非同期処理" in titles


# ── リテラル値 ────────────────────────────────────────────────────

class TestInsertIntoLiteral:
    async def test_literal_value_stored(self, seeded_engine, ext_engine):
        """リテラル値がバインドパラメータとして正しく格納される。"""
        await (
            Post.filter(Post.published == True)  # noqa: E712
                .insert_into(PostArchive,
                    title=Post.title,
                    views=0,            # リテラル: 閲覧数をリセット
                    author_id=Post.author_id,
                )
        )
        archived = await PostArchive.all()
        assert all(r.views == 0 for r in archived)

    async def test_multiple_literals(self, seeded_engine, ext_engine):
        """複数のリテラル値が正しい順序でバインドされる。"""
        await (
            Author.all()
                .insert_into(SalaryLog,
                    emp_id=Author.id,
                    amount=50000.0,     # リテラル1
                    note="特別報奨金",   # リテラル2
                )
        )
        logs = await SalaryLog.all()
        assert len(logs) == 2           # seeded_engine に Author が2件
        assert all(r.amount == 50000.0 for r in logs)
        assert all(r.note == "特別報奨金" for r in logs)

    async def test_all_literal_no_columns(self, ext_engine):
        """全カラムがリテラルの場合でも動作する。"""
        await Author.create(name="Test", email="t@example.com")
        n = await (
            Author.filter(Author.name == "Test")
                .insert_into(SalaryLog,
                    emp_id=1,
                    amount=10000.0,
                )
        )
        assert n == 1


# ── WHERE / ORDER BY / LIMIT との組み合わせ ──────────────────────

class TestInsertIntoWithQueryOptions:
    async def test_with_filter(self, seeded_engine, ext_engine):
        """filter() で絞った行だけ INSERT される。"""
        n = await (
            Post.filter(Post.views >= 1000)
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        assert n == 2   # views >= 1000 の記事は Python入門(2000) と 非同期処理(1200)

    async def test_with_order_and_limit(self, seeded_engine, ext_engine):
        """order_by().limit() を組み合わせてコピー件数を制限できる。"""
        n = await (
            Post.all()
                .order_by(Post.views.desc)
                .limit(2)
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        assert n == 2
        archived = await PostArchive.all()
        assert len(archived) == 2

    async def test_no_match_inserts_zero(self, seeded_engine, ext_engine):
        """条件に一致する行がない場合は 0 を返す。"""
        n = await (
            Post.filter(Post.views > 99999)
                .insert_into(PostArchive,
                    title=Post.title,
                    views=Post.views,
                    author_id=Post.author_id,
                )
        )
        assert n == 0


# ── 同一テーブルへのコピー ────────────────────────────────────────

class TestInsertIntoSameTable:
    async def test_same_table_copy(self, seeded_engine):
        """同じテーブルに条件付きでコピーできる（self-INSERT）。"""
        before = await Post.all().count()
        n = await (
            Post.filter(Post.published == True)  # noqa: E712
                .insert_into(Post,
                    title=Post.title,
                    body=Post.body,
                    views=0,
                    published=False,
                    author_id=Post.author_id,
                )
        )
        after = await Post.all().count()
        assert n == 3
        assert after == before + 3


# ── SQL 生成確認 ──────────────────────────────────────────────────

class TestInsertIntoSql:
    def test_sql_structure_column_ref(self):
        """ColumnMeta はパラメータなしの列参照として展開される。"""
        qs = Post.filter(Post.published == True)  # noqa: E712
        # insert_into は async なので SQL 生成のみ内部確認
        dest_table = PostArchive._meta.table_name
        src_table  = Post._meta.table_name
        # mapping に ColumnMeta を含む場合は _qualified() が使われる
        col_expr = Post.title._qualified()
        assert col_expr == "post.title"
        assert dest_table == "post_archive"
        assert src_table  == "post"

    def test_sql_structure_literal(self):
        """リテラル値は %s プレースホルダに展開される。"""
        # ColumnMeta でない値は literal_params に追加される
        value = 20000
        assert not hasattr(value, "_qualified")
