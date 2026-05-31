"""
ユーザー定義主キー テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn


class Country(Model):
    """2 文字の国コードを PK に使うモデル。"""
    code = StrColumn(primary_key=True, nullable=False)
    name = StrColumn(nullable=False)

    class Meta:
        table_name = "country"


class Order(Model):
    """IntColumn を PK に使うが auto_increment しないモデル。"""
    order_no = IntColumn(primary_key=True, nullable=False)
    item     = StrColumn(nullable=False)

    class Meta:
        table_name = "order_"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Country)
    await eng.create_table(Order)
    yield eng
    await eng.disconnect()


class TestCustomStringPK:
    async def test_pk_name_detected(self):
        assert Country._meta.pk_name == "code"
        assert Country._meta.is_auto_pk is False

    async def test_create_with_custom_pk(self, engine):
        jp = await Country.create(code="JP", name="Japan")
        assert jp.code == "JP"
        assert jp.name == "Japan"

    async def test_get_by_custom_pk(self, engine):
        await Country.create(code="US", name="United States")
        fetched = await Country.get(Country.code == "US")
        assert fetched.name == "United States"

    async def test_update_via_save(self, engine):
        c = await Country.create(code="DE", name="Germany")
        c.name = "Deutschland"
        await c.save()
        refetched = await Country.get(Country.code == "DE")
        assert refetched.name == "Deutschland"

    async def test_delete_instance(self, engine):
        c = await Country.create(code="FR", name="France")
        await c.delete()
        result = await Country.get_or_none(Country.code == "FR")
        assert result is None

    async def test_filter_and_count(self, engine):
        await Country.create(code="AU", name="Australia")
        await Country.create(code="NZ", name="New Zealand")
        n = await Country.all().count()
        assert n >= 2

    async def test_last_uses_pk_name(self, engine):
        await Country.create(code="AA", name="Alpha")
        await Country.create(code="ZZ", name="Zeta")
        last = await Country.last()
        assert last is not None
        assert last.code == "ZZ"


class TestCustomIntPK:
    async def test_create_with_explicit_int_pk(self, engine):
        o = await Order.create(order_no=1001, item="Widget")
        assert o.order_no == 1001

    async def test_update_explicit_pk_model(self, engine):
        o = await Order.create(order_no=2000, item="Gadget")
        o.item = "Super Gadget"
        await o.save()
        refetched = await Order.get(Order.order_no == 2000)
        assert refetched.item == "Super Gadget"
