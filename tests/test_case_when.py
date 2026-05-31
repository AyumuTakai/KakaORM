"""
CASE WHEN 式テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn, Case, When


class Item(Model):
    name  = StrColumn(nullable=False)
    price = IntColumn(nullable=False)
    stock = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "item"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Item)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    await Item.create(name="Luxury",  price=15000, stock=5)
    await Item.create(name="Standard", price=5000,  stock=20)
    await Item.create(name="Budget",   price=800,   stock=100)
    await Item.create(name="Mid",      price=3000,  stock=10)
    return engine


class TestCaseInSelect:
    async def test_case_in_select_returns_dicts(self, seeded):
        """CASE を select() に使うと list[dict] が返ること。"""
        rows = await Item.all().select(
            Item.name,
            Case(
                When(Item.price >= 10000, then="premium"),
                When(Item.price >= 3000,  then="standard"),
                default="budget",
            ).label("tier"),
        )
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    async def test_case_values_correct(self, seeded):
        """CASE 式が正しい値を返すこと。"""
        rows = await Item.all().order_by(Item.price.desc).select(
            Item.name,
            Case(
                When(Item.price >= 10000, then="premium"),
                When(Item.price >= 3000,  then="standard"),
                default="budget",
            ).label("tier"),
        )
        by_name = {r["name"]: r["tier"] for r in rows}
        assert by_name["Luxury"]   == "premium"
        assert by_name["Standard"] == "standard"
        assert by_name["Mid"]      == "standard"
        assert by_name["Budget"]   == "budget"

    async def test_case_without_label(self, seeded):
        """label() なしでも select() に使えること。"""
        rows = await Item.all().select(
            Item.name,
            Case(When(Item.stock == 0, then="sold_out"), default="in_stock"),
        )
        assert len(rows) == 4

    async def test_case_with_none_default(self, seeded):
        """default なし (NULL) の CASE 式が動作すること。"""
        rows = await Item.all().select(
            Item.name,
            Case(When(Item.price >= 10000, then="premium")).label("tier"),
        )
        by_name = {r["name"]: r["tier"] for r in rows}
        assert by_name["Luxury"] == "premium"
        assert by_name["Budget"] is None


class TestCaseInUpdate:
    async def test_case_in_update_set(self, seeded):
        """CASE を update() の SET 値に使えること。"""
        updated = await Item.all().update(
            stock=Case(
                When(Item.price >= 10000, then=1),
                When(Item.price >= 3000,  then=5),
                default=50,
            )
        )
        assert updated == 4

        luxury = await Item.get(Item.name == "Luxury")
        standard = await Item.get(Item.name == "Standard")
        budget = await Item.get(Item.name == "Budget")

        assert luxury.stock == 1
        assert standard.stock == 5
        assert budget.stock == 50

    async def test_case_update_with_filter(self, seeded):
        """filter() と組み合わせた CASE UPDATE が動作すること。"""
        await Item.filter(Item.price >= 5000).update(
            name=Case(
                When(Item.price >= 10000, then="LUXURY"),
                default="STANDARD",
            )
        )
        luxury = await Item.get(Item.name == "LUXURY")
        std    = await Item.get(Item.name == "STANDARD")
        assert luxury is not None
        assert std is not None


class TestCaseRepr:
    def test_case_repr(self):
        c = Case(When(Item.price >= 100, then="ok"), default="ng")
        assert "CASE" in repr(c)
        assert "WHEN" in repr(c)
