"""
VersionedMigrator テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn
from kakaorm.migration import VersionedMigrator


class UserV(Model):
    name = StrColumn(nullable=False)
    class Meta:
        table_name = "user_v"


class PostV(Model):
    title = StrColumn(nullable=False)
    class Meta:
        table_name = "post_v"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    yield eng
    await eng.disconnect()


class TestVersionedMigrator:
    async def test_ensure_history_table_creates_table(self, engine):
        """履歴テーブルが存在しなければ作成されること。"""
        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()
        rows = await engine.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kakaorm_migrations'"
        )
        assert len(rows) == 1

    async def test_ensure_history_table_idempotent(self, engine):
        """2回呼んでもエラーにならないこと。"""
        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()
        await migrator.ensure_history_table()  # 冪等

    async def test_run_applies_all_migrations(self, engine):
        """全マイグレーションが未適用なら全て実行されること。"""
        migrator = VersionedMigrator(engine)
        count = await migrator.run_manual({
            "001_create_user_v": lambda: engine.create_table(UserV),
            "002_create_post_v": lambda: engine.create_table(PostV),
        })
        assert count == 2

    async def test_run_skips_applied_migrations(self, engine):
        """一度適用済みのマイグレーションは再実行されないこと。"""
        migrator = VersionedMigrator(engine)
        migrations = {
            "001_create_user_v": lambda: engine.create_table(UserV),
            "002_create_post_v": lambda: engine.create_table(PostV),
        }
        first  = await migrator.run_manual(migrations)
        second = await migrator.run_manual(migrations)
        assert first  == 2
        assert second == 0

    async def test_run_applies_only_new_migrations(self, engine):
        """追加されたマイグレーションだけが実行されること。"""
        migrator = VersionedMigrator(engine)
        await migrator.run_manual({"001_create_user_v": lambda: engine.create_table(UserV)})
        count = await migrator.run_manual({
            "001_create_user_v": lambda: engine.create_table(UserV),
            "002_create_post_v": lambda: engine.create_table(PostV),
        })
        assert count == 1

    async def test_applied_names_returns_set(self, engine):
        """applied_names() が正しい名前セットを返すこと。"""
        migrator = VersionedMigrator(engine)
        await migrator.run_manual({"001_create_user_v": lambda: engine.create_table(UserV)})
        names = await migrator.applied_names()
        assert "001_create_user_v" in names

    async def test_history_returns_records_in_order(self, engine):
        """history() が MigrationRecord のリストを時系列順で返すこと。"""
        migrator = VersionedMigrator(engine)
        await migrator.run_manual({
            "001_create_user_v": lambda: engine.create_table(UserV),
            "002_create_post_v": lambda: engine.create_table(PostV),
        })
        history = await migrator.history()
        assert len(history) == 2
        assert history[0].name == "001_create_user_v"
        assert history[1].name == "002_create_post_v"
        assert history[0].applied_at is not None

    async def test_run_executes_callable_correctly(self, engine):
        """callable が実際に実行されてテーブルが作られること。"""
        migrator = VersionedMigrator(engine)
        await migrator.run_manual({"001_create_user_v": lambda: engine.create_table(UserV)})
        # テーブルが存在することを確認
        await UserV.create(name="Test")
        user = await UserV.get(UserV.name == "Test")
        assert user.name == "Test"

    async def test_record_stores_iso_timestamp(self, engine):
        """record() が ISO 形式のタイムスタンプを保存すること。"""
        import datetime
        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()
        await migrator.record("test_migration")
        history = await migrator.history()
        assert len(history) == 1
        # ISO 形式でパースできること
        dt = datetime.datetime.fromisoformat(history[0].applied_at)
        assert dt is not None
