"""
MySQL / MariaDB 統合テスト
===========================
環境変数 KAKAORM_MYSQL_URL が設定されていない場合はスキップ。

    export KAKAORM_MYSQL_URL="mysql+aiomysql://root:password@localhost:3306/test_db"
    pytest tests/test_mysql.py -v
"""

import os

import pytest
import pytest_asyncio

import kakaorm
from kakaorm import BoolColumn, IntColumn, Model, StrColumn
from kakaorm.migration import Migrator

MYSQL_URL = os.environ.get("KAKAORM_MYSQL_URL", "")

pytestmark = pytest.mark.skipif(
    not MYSQL_URL,
    reason="KAKAORM_MYSQL_URL 未設定 — MySQL テストをスキップ",
)


class MySQLItem(Model):
    name = StrColumn(nullable=False)
    qty  = IntColumn(nullable=False, default=0)
    done = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "test_item"


@pytest_asyncio.fixture
async def mysql_engine():
    engine = await kakaorm.connect(MYSQL_URL)
    await engine.drop_table(MySQLItem, if_exists=True)
    await engine.create_table(MySQLItem)
    yield engine
    await engine.drop_table(MySQLItem, if_exists=True)
    await engine.disconnect()


class TestMySQLCrud:
    async def test_create_and_fetch(self, mysql_engine):
        item = await MySQLItem.create(name="apple", qty=10)
        assert item.id is not None
        fetched = await MySQLItem.get(MySQLItem.id == item.id)
        assert fetched.name == "apple"
        assert fetched.qty == 10

    async def test_update(self, mysql_engine):
        item = await MySQLItem.create(name="banana", qty=5)
        item.qty = 99
        await item.save()
        updated = await MySQLItem.get(MySQLItem.id == item.id)
        assert updated.qty == 99

    async def test_delete(self, mysql_engine):
        item = await MySQLItem.create(name="cherry", qty=3)
        pk = item.id
        await item.delete()
        result = await MySQLItem.get_or_none(MySQLItem.id == pk)
        assert result is None

    async def test_filter_and_count(self, mysql_engine):
        await MySQLItem.create(name="date", qty=1)
        await MySQLItem.create(name="date", qty=2)
        items = await MySQLItem.filter(MySQLItem.name == "date")
        assert len(items) >= 2
        n = await MySQLItem.filter(MySQLItem.name == "date").count()
        assert n >= 2

    async def test_bulk_update_delete(self, mysql_engine):
        await MySQLItem.create(name="fig", qty=0, done=False)
        await MySQLItem.create(name="fig", qty=0, done=False)
        updated = await MySQLItem.filter(MySQLItem.name == "fig").update(done=True)  # noqa: E712
        assert updated >= 2
        deleted = await MySQLItem.filter(MySQLItem.name == "fig").delete()
        assert deleted >= 2


class TestMySQLMigration:
    async def test_migration_plan_empty(self, mysql_engine):
        migrator = Migrator(mysql_engine)
        plan = await migrator.plan([MySQLItem])
        non_warn = [s for s in plan.statements if not s.startswith("--")]
        assert len(non_warn) == 0
