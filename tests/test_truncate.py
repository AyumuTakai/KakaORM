"""
TRUNCATE テスト
===============
Model.truncate() が全行削除とシーケンスリセットを行うことを確認する。
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import IntColumn, Model, StrColumn


# ── モデル定義 ──────────────────────────────────────────────────

class Widget(Model):
    name = StrColumn(nullable=False)

    class Meta:
        table_name = "widget"


# ── フィクスチャ ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Widget)
    yield eng
    await eng.disconnect()


# ── テスト ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_truncate_removes_all_rows(engine):
    await Widget.create(name="A")
    await Widget.create(name="B")
    await Widget.create(name="C")

    count_before = await Widget.all().count()
    assert count_before == 3

    await Widget.truncate()

    count_after = await Widget.all().count()
    assert count_after == 0


@pytest.mark.asyncio
async def test_truncate_resets_sequence(engine):
    """truncate 後に挿入すると id が 1 から再採番されること。"""
    await Widget.create(name="first")
    await Widget.create(name="second")

    await Widget.truncate(restart_identity=True)

    w = await Widget.create(name="after_truncate")
    assert w.id == 1


@pytest.mark.asyncio
async def test_truncate_without_restart_identity(engine):
    """restart_identity=False の場合、全行削除のみ（シーケンスはリセットしない）。"""
    await Widget.create(name="x")
    await Widget.truncate(restart_identity=False)

    count = await Widget.all().count()
    assert count == 0


@pytest.mark.asyncio
async def test_truncate_empty_table(engine):
    """空テーブルに対する truncate はエラーにならない。"""
    await Widget.truncate()
    count = await Widget.all().count()
    assert count == 0


@pytest.mark.asyncio
async def test_truncate_then_insert(engine):
    """truncate 後の INSERT が正常に動作すること。"""
    for i in range(5):
        await Widget.create(name=f"item{i}")

    await Widget.truncate()

    new = await Widget.create(name="new_item")
    assert new.id is not None

    all_items = await Widget.all().execute()
    assert len(all_items) == 1
    assert all_items[0].name == "new_item"
