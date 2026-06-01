"""
ArchiveModel のテスト
=====================
アーカイブ削除・復元・物理削除・QuerySet フィルタ・autogenerate 連携を検証する。
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import IntColumn, StrColumn, Migrator, VersionedMigrator
from kakaorm.archive import ArchiveModel


class Event(ArchiveModel):
    title    = StrColumn(nullable=False)
    priority = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "event"


@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Event)
    await eng.create_archive_table(Event)
    yield eng
    await eng.disconnect()


@pytest_asyncio.fixture
async def seeded(engine):
    """3件作成し、うち1件をアーカイブ削除済みにして返す。"""
    e1 = await Event.create(title="First",  priority=1)
    e2 = await Event.create(title="Second", priority=2)
    e3 = await Event.create(title="Third",  priority=3)
    await e2.delete()
    return {"engine": engine, "e1": e1, "e2": e2, "e3": e3}


# ── アーカイブテーブルの存在確認 ───────────────────────────────

def test_archive_table_name():
    assert Event._archive_table_name() == "archive_event"


# ── デフォルト: アーカイブ済みを除外 ──────────────────────────

@pytest.mark.asyncio
async def test_all_excludes_archived(seeded):
    events = await Event.all()
    titles = {e.title for e in events}
    assert titles == {"First", "Third"}


@pytest.mark.asyncio
async def test_where_excludes_archived(seeded):
    events = await Event.where(Event.priority >= 1)
    titles = {e.title for e in events}
    assert "Second" not in titles


@pytest.mark.asyncio
async def test_count_excludes_archived(seeded):
    count = await Event.all().count()
    assert count == 2


@pytest.mark.asyncio
async def test_first_excludes_archived(seeded):
    event = await Event.first()
    assert event is not None
    assert event.title == "First"


# ── include_deleted(): UNION ALL で全件 ───────────────────────

@pytest.mark.asyncio
async def test_include_deleted_all(seeded):
    events = await Event.include_deleted()
    assert len(events) == 3


@pytest.mark.asyncio
async def test_include_deleted_count(seeded):
    count = await Event.include_deleted().count()
    assert count == 3


@pytest.mark.asyncio
async def test_include_deleted_chained_where(seeded):
    events = await Event.include_deleted().where(Event.priority >= 2)
    titles = {e.title for e in events}
    assert titles == {"Second", "Third"}


# ── only_deleted(): アーカイブのみ ─────────────────────────────

@pytest.mark.asyncio
async def test_only_deleted(seeded):
    events = await Event.only_deleted()
    assert len(events) == 1
    assert events[0].title == "Second"


@pytest.mark.asyncio
async def test_only_deleted_count(seeded):
    count = await Event.only_deleted().count()
    assert count == 1


# ── delete(): アーカイブへ移動 ─────────────────────────────────

@pytest.mark.asyncio
async def test_instance_delete_moves_to_archive(engine):
    event = await Event.create(title="ToArchive", priority=0)
    await event.delete()

    # メインテーブルから消える
    results = await Event.all()
    assert all(e.title != "ToArchive" for e in results)

    # アーカイブテーブルに現れる
    archived = await Event.only_deleted()
    assert any(e.title == "ToArchive" for e in archived)


@pytest.mark.asyncio
async def test_queryset_delete_archives_matching(engine):
    await Event.create(title="A", priority=10)
    await Event.create(title="B", priority=20)
    count = await Event.where(Event.priority == 10).delete()
    assert count == 1

    remaining = await Event.all()
    assert len(remaining) == 1
    assert remaining[0].title == "B"

    archived = await Event.only_deleted()
    assert len(archived) == 1
    assert archived[0].title == "A"


# ── restore(): アーカイブから復元 ─────────────────────────────

@pytest.mark.asyncio
async def test_instance_restore(seeded):
    e2 = seeded["e2"]
    await e2.restore()

    events = await Event.all()
    titles = {e.title for e in events}
    assert "Second" in titles

    archived = await Event.only_deleted()
    assert len(archived) == 0


@pytest.mark.asyncio
async def test_queryset_restore(engine):
    await Event.create(title="X", priority=0)
    await Event.create(title="Y", priority=0)
    await Event.all().delete()

    assert await Event.all().count() == 0
    assert await Event.only_deleted().count() == 2

    await Event.only_deleted().restore()

    assert await Event.all().count() == 2
    assert await Event.only_deleted().count() == 0


# ── purge(): アーカイブから物理削除 ───────────────────────────

@pytest.mark.asyncio
async def test_purge_removes_from_archive(seeded):
    await Event.only_deleted().purge()

    assert await Event.only_deleted().count() == 0
    assert await Event.include_deleted().count() == 2  # First と Third だけ残る


# ── get() / get_or_none() ─────────────────────────────────────

@pytest.mark.asyncio
async def test_get_excludes_archived(seeded):
    e2 = seeded["e2"]
    with pytest.raises(Event.NotFound):
        await Event.get(Event.id == e2.id)


@pytest.mark.asyncio
async def test_get_or_none_excludes_archived(seeded):
    e2 = seeded["e2"]
    result = await Event.get_or_none(Event.id == e2.id)
    assert result is None


@pytest.mark.asyncio
async def test_include_deleted_find_archived(seeded):
    e2 = seeded["e2"]
    result = await Event.include_deleted().where(Event.id == e2.id).first()
    assert result is not None
    assert result.title == "Second"


# ── autogenerate(): アーカイブテーブルを含む差分検出 ───────────

@pytest.mark.asyncio
async def test_autogenerate_creates_archive_table(tmp_path):
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    try:
        migrator = VersionedMigrator(eng)
        path = await migrator.autogenerate([Event], str(tmp_path), name="init_event")

        assert path is not None
        content = path.read_text()

        # メインテーブルの CREATE を含む
        assert "event" in content
        # アーカイブテーブルの CREATE も含む
        assert "archive_event" in content
        # archived_at カラムも含む
        assert "archived_at" in content
    finally:
        await eng.disconnect()


@pytest.mark.asyncio
async def test_autogenerate_no_diff_when_tables_exist(tmp_path):
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    try:
        await eng.create_table(Event)
        await eng.create_archive_table(Event)

        migrator = VersionedMigrator(eng)
        path = await migrator.autogenerate([Event], str(tmp_path), name="noop")

        assert path is None  # 差分なし → ファイル生成なし
    finally:
        await eng.disconnect()
