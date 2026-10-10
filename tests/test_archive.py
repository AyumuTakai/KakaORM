"""
ArchiveModel のテスト
=====================
アーカイブ削除・復元・物理削除・QuerySet フィルタ・autogenerate 連携を検証する。
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import ForeignKey, IntColumn, StrColumn, Migrator, VersionedMigrator
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


# ── 外部キー: アーカイブテーブルの FK 除去とカスケードアーカイブ ──


class ArPost(ArchiveModel):
    title = StrColumn(nullable=False)

    class Meta:
        table_name = "ar_post"


class ArComment(ArchiveModel):
    post_id   = ForeignKey("ar_post", on_delete="CASCADE")
    parent_id = ForeignKey("ar_comment", on_delete="CASCADE", nullable=True)
    body      = StrColumn(nullable=False)

    class Meta:
        table_name = "ar_comment"


class ArLike(ArchiveModel):
    post_id = ForeignKey("ar_post", on_delete="SET NULL", nullable=True)

    class Meta:
        table_name = "ar_like"


@pytest_asyncio.fixture
async def fk_engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    for m in (ArPost, ArComment, ArLike):
        await eng.create_table(m)
        await eng.create_archive_table(m)
    yield eng
    await eng.disconnect()


async def _table_sql(eng, name):
    rows = await eng._fetch("SELECT sql FROM sqlite_master WHERE name = %s", [name])
    return rows[0]["sql"]


@pytest.mark.asyncio
async def test_archive_table_has_no_foreign_keys(fk_engine):
    assert "REFERENCES" in await _table_sql(fk_engine, "ar_comment")
    assert "REFERENCES" not in await _table_sql(fk_engine, "archive_ar_comment")


@pytest.mark.asyncio
async def test_autogenerate_archive_table_has_no_foreign_keys(tmp_path):
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    try:
        migrator = VersionedMigrator(eng)
        path = await migrator.autogenerate([ArPost, ArComment], str(tmp_path), name="fk")
        content = path.read_text()
        [archive_ddl] = [
            line for line in content.splitlines()
            if "CREATE TABLE IF NOT EXISTS [archive_ar_comment]" in line
        ]
        assert "REFERENCES" not in archive_ddl
    finally:
        await eng.disconnect()


@pytest.mark.asyncio
async def test_archiving_parent_keeps_already_archived_children(fk_engine):
    post = await ArPost.create(title="p")
    c = await ArComment.create(post_id=post.id, body="old")
    await c.delete()

    await post.delete()

    archived = await ArComment.only_deleted()
    assert [x.body for x in archived] == ["old"]


@pytest.mark.asyncio
async def test_archiving_parent_cascades_to_active_children(fk_engine):
    post  = await ArPost.create(title="p")
    other = await ArPost.create(title="other")
    c1    = await ArComment.create(post_id=post.id, body="c1")
    reply = await ArComment.create(post_id=post.id, parent_id=c1.id, body="reply")
    keep  = await ArComment.create(post_id=other.id, body="keep")

    assert await ArPost.where(ArPost.id == post.id).delete() == 1

    assert [x.id for x in await ArComment.all()] == [keep.id]
    archived = sorted(x.id for x in await ArComment.only_deleted())
    assert archived == sorted([c1.id, reply.id])

    # 親を戻せば子も個別に復元できる
    await post.restore()
    await c1.restore()
    await reply.restore()
    assert await ArComment.where(ArComment.post_id == post.id).count() == 2
    assert await ArComment.only_deleted().count() == 0


@pytest.mark.asyncio
async def test_archiving_parent_does_not_cascade_non_cascade_fk(fk_engine):
    post = await ArPost.create(title="p")
    like = await ArLike.create(post_id=post.id)

    await post.delete()

    rows = await ArLike.all()
    assert [x.id for x in rows] == [like.id]
    assert rows[0].post_id is None  # メインテーブルの SET NULL が効く
    assert await ArLike.only_deleted().count() == 0
