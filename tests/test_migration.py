"""
Migrator テスト
"""

from kakaorm.migration import Migrator
from conftest import Author, Post


class TestMigrator:
    async def test_plan_empty_when_tables_exist(self, engine):
        migrator = Migrator(engine)
        plan = await migrator.plan([Author, Post])
        non_warning = [s for s in plan.statements if not s.startswith("--")]
        assert len(non_warning) == 0

    async def test_plan_creates_missing_table(self, engine):
        import kakaorm
        from kakaorm import Model, StrColumn

        class NewTable(Model):
            label = StrColumn(nullable=False)
            class Meta:
                table_name = "new_table"

        migrator = Migrator(engine)
        plan = await migrator.plan([NewTable])
        assert any("CREATE TABLE" in s for s in plan.statements)

    async def test_plan_is_empty(self, engine):
        migrator = Migrator(engine)
        plan = await migrator.plan([Author, Post])
        assert plan.is_empty()

    async def test_plan_not_empty_for_new_table(self, engine):
        import kakaorm
        from kakaorm import Model, StrColumn

        class AnotherTable(Model):
            value = StrColumn()
            class Meta:
                table_name = "another_table"

        migrator = Migrator(engine)
        plan = await migrator.plan([AnotherTable])
        assert not plan.is_empty()
