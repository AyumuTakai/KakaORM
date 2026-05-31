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
from kakaorm import DateColumn, DecimalColumn, IntColumn, Model, StrColumn, TimeColumn


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


# ── フィクスチャ ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Product)
    await eng.create_table(Event)
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
