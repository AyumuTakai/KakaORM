"""
SoftDeleteModel のテスト
========================
論理削除・復元・物理削除（purge）・QuerySet フィルタの動作を検証する。
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import StrColumn, IntColumn
from kakaorm.soft_delete import SoftDeleteModel


class News(SoftDeleteModel):
    title = StrColumn(nullable=False)
    views = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "article"


@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(News)
    yield eng
    await eng.disconnect()


@pytest_asyncio.fixture
async def seeded(engine):
    """3件作成し、うち1件を論理削除済みにして返す。"""
    a1 = await News.create(title="First",  views=100)
    a2 = await News.create(title="Second", views=200)
    a3 = await News.create(title="Third",  views=300)
    await a2.delete()
    return {"engine": engine, "a1": a1, "a2": a2, "a3": a3}


# ── deleted_at カラムの存在確認 ────────────────────────────────

def test_deleted_at_column_defined():
    assert "deleted_at" in News._meta.columns


# ── デフォルト: 論理削除済みを除外 ────────────────────────────

@pytest.mark.asyncio
async def test_all_excludes_deleted(seeded):
    articles = await News.all()
    titles = {a.title for a in articles}
    assert titles == {"First", "Third"}
    assert "Second" not in titles


@pytest.mark.asyncio
async def test_where_excludes_deleted(seeded):
    articles = await News.where(News.views >= 100)
    titles = {a.title for a in articles}
    assert "Second" not in titles


@pytest.mark.asyncio
async def test_count_excludes_deleted(seeded):
    count = await News.all().count()
    assert count == 2


@pytest.mark.asyncio
async def test_first_excludes_deleted(seeded):
    article = await News.first()
    assert article is not None
    assert article.title == "First"


# ── include_deleted(): 全件取得 ────────────────────────────────

@pytest.mark.asyncio
async def test_include_deleted_all(seeded):
    articles = await News.include_deleted()
    assert len(articles) == 3


@pytest.mark.asyncio
async def test_include_deleted_count(seeded):
    count = await News.include_deleted().count()
    assert count == 3


@pytest.mark.asyncio
async def test_include_deleted_chained_where(seeded):
    articles = await News.include_deleted().where(News.views >= 200)
    titles = {a.title for a in articles}
    assert titles == {"Second", "Third"}


# ── only_deleted(): 削除済みのみ ───────────────────────────────

@pytest.mark.asyncio
async def test_only_deleted(seeded):
    articles = await News.only_deleted()
    assert len(articles) == 1
    assert articles[0].title == "Second"


@pytest.mark.asyncio
async def test_only_deleted_count(seeded):
    count = await News.only_deleted().count()
    assert count == 1


# ── delete(): 論理削除 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_instance_delete_sets_deleted_at(engine):
    article = await News.create(title="ToDelete", views=0)
    assert article.deleted_at is None
    await article.delete()
    assert article.deleted_at is not None


@pytest.mark.asyncio
async def test_instance_delete_hides_from_all(engine):
    article = await News.create(title="ToDelete", views=0)
    await article.delete()
    results = await News.all()
    assert all(a.title != "ToDelete" for a in results)


@pytest.mark.asyncio
async def test_queryset_delete_soft_deletes(engine):
    await News.create(title="A", views=10)
    await News.create(title="B", views=20)
    deleted_count = await News.where(News.views == 10).delete()
    assert deleted_count == 1
    remaining = await News.all()
    assert len(remaining) == 1
    assert remaining[0].title == "B"


# ── restore(): 論理削除の取り消し ─────────────────────────────

@pytest.mark.asyncio
async def test_instance_restore(seeded):
    a2 = seeded["a2"]
    assert a2.deleted_at is not None
    await a2.restore()
    assert a2.deleted_at is None

    articles = await News.all()
    titles = {a.title for a in articles}
    assert "Second" in titles


@pytest.mark.asyncio
async def test_queryset_restore(engine):
    await News.create(title="X", views=0)
    await News.create(title="Y", views=0)
    await News.all().delete()
    assert await News.all().count() == 0

    await News.only_deleted().restore()
    assert await News.all().count() == 2


# ── purge(): 物理削除 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_purge_removes_physically(seeded):
    await News.only_deleted().purge()

    # 論理削除済みも含めて0件
    count = await News.include_deleted().count()
    assert count == 2  # First と Third だけ残る


# ── get() / get_or_none(): 削除済み除外 ───────────────────────

@pytest.mark.asyncio
async def test_get_excludes_deleted(seeded):
    a2 = seeded["a2"]
    with pytest.raises(News.NotFound):
        await News.get(News.id == a2.id)


@pytest.mark.asyncio
async def test_get_or_none_excludes_deleted(seeded):
    a2 = seeded["a2"]
    result = await News.get_or_none(News.id == a2.id)
    assert result is None


@pytest.mark.asyncio
async def test_include_deleted_get(seeded):
    a2 = seeded["a2"]
    result = await News.include_deleted().where(News.id == a2.id).first()
    assert result is not None
    assert result.title == "Second"
