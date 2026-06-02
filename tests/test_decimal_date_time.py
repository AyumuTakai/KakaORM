"""
DecimalColumn / DateColumn / TimeColumn のテスト
================================================
- DB ラウンドトリップ（Python → DB → Python）
- NULL 処理
- ORM クエリ（where / create / update）での動作確認
"""

import datetime
import os
import sys
from decimal import Decimal

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kakaorm
from kakaorm import DateColumn, DateTimeColumn, DecimalColumn, IntColumn, Model, StrColumn, TimeColumn


# ── テスト用モデル ───────────────────────────────────────────────

class Product(Model):
    name      = StrColumn(nullable=False)
    price     = DecimalColumn(10, 2, nullable=False)
    tax_rate  = DecimalColumn(5, 4, nullable=True)

    class Meta:
        table_name = "product"


class Event(Model):
    title      = StrColumn(nullable=False)
    event_date = DateColumn(nullable=False)
    start_time = TimeColumn(nullable=True)

    class Meta:
        table_name = "event"


class Log(Model):
    message    = StrColumn(nullable=False)
    created_at = DateTimeColumn(nullable=False)
    updated_at = DateTimeColumn(nullable=True)

    class Meta:
        table_name = "log"


# ── フィクスチャ ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Product)
    await eng.create_table(Event)
    await eng.create_table(Log)
    yield eng
    await eng.disconnect()


# ── DecimalColumn テスト ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_decimal_round_trip(engine):
    p = await Product.create(name="Widget", price=Decimal("19.99"), tax_rate=Decimal("0.0800"))
    fetched = await Product.get(Product.id == p.id)
    assert fetched.price == Decimal("19.99")
    assert fetched.tax_rate == Decimal("0.0800")


@pytest.mark.asyncio
async def test_decimal_precision(engine):
    """小数精度が損なわれないことを確認する。"""
    p = await Product.create(name="Precise", price=Decimal("1234567.89"), tax_rate=Decimal("0.1250"))
    fetched = await Product.get(Product.id == p.id)
    assert fetched.price == Decimal("1234567.89")
    assert fetched.tax_rate == Decimal("0.1250")


@pytest.mark.asyncio
async def test_decimal_null(engine):
    p = await Product.create(name="NoTax", price=Decimal("9.99"), tax_rate=None)
    fetched = await Product.get(Product.id == p.id)
    assert fetched.price == Decimal("9.99")
    assert fetched.tax_rate is None


@pytest.mark.asyncio
async def test_decimal_where(engine):
    await Product.create(name="Cheap", price=Decimal("5.00"), tax_rate=None)
    await Product.create(name="Expensive", price=Decimal("99.99"), tax_rate=None)
    cheap = await Product.where(Product.price == Decimal("5.00"))
    assert len(cheap) == 1
    assert cheap[0].name == "Cheap"


@pytest.mark.asyncio
async def test_decimal_update(engine):
    p = await Product.create(name="Widget", price=Decimal("10.00"), tax_rate=None)
    p.price = Decimal("12.50")
    await p.save()
    fetched = await Product.get(Product.id == p.id)
    assert fetched.price == Decimal("12.50")


# ── DateColumn テスト ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_date_round_trip(engine):
    d = datetime.date(2024, 6, 15)
    e = await Event.create(title="PyCon", event_date=d, start_time=None)
    fetched = await Event.get(Event.id == e.id)
    assert fetched.event_date == d
    assert isinstance(fetched.event_date, datetime.date)


@pytest.mark.asyncio
async def test_date_where(engine):
    d1 = datetime.date(2024, 1, 1)
    d2 = datetime.date(2024, 12, 31)
    await Event.create(title="New Year", event_date=d1, start_time=None)
    await Event.create(title="Year End", event_date=d2, start_time=None)
    results = await Event.where(Event.event_date == d1)
    assert len(results) == 1
    assert results[0].title == "New Year"


@pytest.mark.asyncio
async def test_date_update(engine):
    e = await Event.create(title="TBD", event_date=datetime.date(2024, 1, 1), start_time=None)
    e.event_date = datetime.date(2024, 3, 20)
    await e.save()
    fetched = await Event.get(Event.id == e.id)
    assert fetched.event_date == datetime.date(2024, 3, 20)


# ── TimeColumn テスト ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_time_round_trip(engine):
    t = datetime.time(9, 30, 0)
    e = await Event.create(title="Morning", event_date=datetime.date(2024, 4, 1), start_time=t)
    fetched = await Event.get(Event.id == e.id)
    assert fetched.start_time == t
    assert isinstance(fetched.start_time, datetime.time)


@pytest.mark.asyncio
async def test_time_null(engine):
    e = await Event.create(title="AllDay", event_date=datetime.date(2024, 5, 1), start_time=None)
    fetched = await Event.get(Event.id == e.id)
    assert fetched.start_time is None


@pytest.mark.asyncio
async def test_time_update(engine):
    e = await Event.create(
        title="Workshop",
        event_date=datetime.date(2024, 6, 10),
        start_time=datetime.time(10, 0, 0),
    )
    e.start_time = datetime.time(14, 30, 0)
    await e.save()
    fetched = await Event.get(Event.id == e.id)
    assert fetched.start_time == datetime.time(14, 30, 0)


# ── 混合テスト ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_types_together(engine):
    """Decimal / Date / Time が同一レコードで正しく動作することを確認する。"""
    e = await Event.create(
        title="Conference",
        event_date=datetime.date(2025, 9, 15),
        start_time=datetime.time(8, 45, 0),
    )
    p = await Product.create(name="Badge", price=Decimal("3500.00"), tax_rate=Decimal("0.1000"))

    ev = await Event.get(Event.id == e.id)
    pr = await Product.get(Product.id == p.id)

    assert ev.event_date == datetime.date(2025, 9, 15)
    assert ev.start_time == datetime.time(8, 45, 0)
    assert pr.price == Decimal("3500.00")
    assert pr.tax_rate == Decimal("0.1000")


# ── DateTimeColumn テスト ────────────────────────────────────────

@pytest.mark.asyncio
async def test_datetime_round_trip(engine):
    dt = datetime.datetime(2026, 6, 2, 0, 38, 3, 768346)
    log = await Log.create(message="hello", created_at=dt, updated_at=None)
    fetched = await Log.get(Log.id == log.id)
    assert isinstance(fetched.created_at, datetime.datetime)
    assert fetched.created_at == dt


@pytest.mark.asyncio
async def test_datetime_null(engine):
    dt = datetime.datetime(2026, 1, 1, 12, 0, 0)
    log = await Log.create(message="nullable", created_at=dt, updated_at=None)
    fetched = await Log.get(Log.id == log.id)
    assert fetched.updated_at is None


@pytest.mark.asyncio
async def test_datetime_update(engine):
    dt1 = datetime.datetime(2026, 1, 1, 0, 0, 0)
    dt2 = datetime.datetime(2026, 6, 2, 15, 30, 0)
    log = await Log.create(message="upd", created_at=dt1, updated_at=None)
    log.created_at = dt2
    await log.save()
    fetched = await Log.get(Log.id == log.id)
    assert isinstance(fetched.created_at, datetime.datetime)
    assert fetched.created_at == dt2


@pytest.mark.asyncio
async def test_datetime_where(engine):
    dt1 = datetime.datetime(2026, 1, 1, 0, 0, 0)
    dt2 = datetime.datetime(2026, 6, 2, 0, 0, 0)
    await Log.create(message="first", created_at=dt1, updated_at=None)
    await Log.create(message="second", created_at=dt2, updated_at=None)
    results = await Log.where(Log.created_at == dt1)
    assert len(results) == 1
    assert results[0].message == "first"


# ── DDL 変換テスト ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_datetime_ddl_uses_datetime_type(engine):
    """SQLite の CREATE TABLE で DATETIME 型が使われることを確認する。"""
    rows = await engine.fetch(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='log'"
    )
    assert rows, "log テーブルが見つかりません"
    ddl = rows[0]["sql"]
    assert "DATETIME" in ddl, f"DDL に DATETIME が含まれていません: {ddl}"
    assert "TIMESTAMP" not in ddl, f"DDL に未変換の TIMESTAMP が残っています: {ddl}"
