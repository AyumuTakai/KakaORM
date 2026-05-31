"""
CHECK 制約テスト
================
Column(check="...") で生成した DDL が CREATE TABLE に反映されることと、
制約違反時に DB がエラーを発生させることを確認する。
"""

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import IntColumn, Model, StrColumn
from kakaorm.columns.types import DecimalColumn, FloatColumn


# ── モデル定義 ──────────────────────────────────────────────────

class Product(Model):
    name  = StrColumn(nullable=False)
    price = IntColumn(nullable=False, check="price >= 0")
    stock = IntColumn(nullable=False, default=0, check="stock >= 0")

    class Meta:
        table_name = "product"


class Score(Model):
    value = FloatColumn(nullable=False, check="value BETWEEN 0.0 AND 100.0")

    class Meta:
        table_name = "score"


class Budget(Model):
    amount = DecimalColumn(10, 2, nullable=False, check="amount > 0")

    class Meta:
        table_name = "budget"


# ── フィクスチャ ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Product)
    await eng.create_table(Score)
    await eng.create_table(Budget)
    yield eng
    await eng.disconnect()


# ── DDL 生成テスト ─────────────────────────────────────────────

def test_check_in_ddl_fragment():
    col = IntColumn(nullable=False, check="price >= 0")
    col._name = "price"
    assert "CHECK (price >= 0)" in col.ddl_fragment()


def test_check_with_unique():
    col = StrColumn(unique=True, check="length(name) > 0")
    col._name = "name"
    frag = col.ddl_fragment()
    assert "UNIQUE" in frag
    assert "CHECK (length(name) > 0)" in frag


def test_check_decimal_ddl():
    col = DecimalColumn(10, 2, nullable=False, check="amount > 0")
    col._name = "amount"
    frag = col.ddl_fragment()
    assert "NUMERIC(10,2)" in frag
    assert "NOT NULL" in frag
    assert "CHECK (amount > 0)" in frag


def test_no_check_by_default():
    col = IntColumn(nullable=False)
    col._name = "x"
    assert "CHECK" not in col.ddl_fragment()


# ── DB 動作テスト ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_insert(engine):
    p = await Product.create(name="Widget", price=100, stock=50)
    assert p.id is not None
    assert p.price == 100


@pytest.mark.asyncio
async def test_check_violation_raises(engine):
    """CHECK 制約違反は DB レベルでエラーになること。"""
    with pytest.raises(Exception):
        await Product.create(name="Invalid", price=-1, stock=0)


@pytest.mark.asyncio
async def test_check_stock_violation(engine):
    with pytest.raises(Exception):
        await Product.create(name="Invalid", price=10, stock=-5)


@pytest.mark.asyncio
async def test_check_float_between(engine):
    s = await Score.create(value=85.5)
    assert s.value == 85.5


@pytest.mark.asyncio
async def test_check_float_violation(engine):
    with pytest.raises(Exception):
        await Score.create(value=101.0)


@pytest.mark.asyncio
async def test_check_decimal_ok(engine):
    from decimal import Decimal
    b = await Budget.create(amount=Decimal("999.99"))
    assert b.amount == Decimal("999.99")


@pytest.mark.asyncio
async def test_check_decimal_violation(engine):
    from decimal import Decimal
    with pytest.raises(Exception):
        await Budget.create(amount=Decimal("0"))
