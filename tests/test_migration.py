"""
Migrator テスト
"""

import tempfile
import pathlib
import kakaorm
from kakaorm import Model, StrColumn
from kakaorm.migration import Migrator, VersionedMigrator
from conftest import Author, Post


class TestMigrator:
    async def test_run_applies_missing_tables(self, engine):
        class RunTable(Model):
            label = StrColumn(nullable=False)
            class Meta:
                table_name = "run_table"

        plan = await Migrator(engine).run([RunTable])
        assert not plan.is_empty()
        # Running again returns an empty plan (idempotent)
        plan2 = await Migrator(engine).run([RunTable])
        assert plan2.is_empty()

    async def test_run_returns_empty_plan_when_no_diff(self, engine):
        plan = await Migrator(engine).run([Author, Post])
        assert plan.is_empty()

    async def test_plan_empty_when_tables_exist(self, engine):
        migrator = Migrator(engine)
        plan = await migrator.plan([Author, Post])
        non_warning = [s for s in plan.statements if not s.startswith("--")]
        assert len(non_warning) == 0

    async def test_plan_creates_missing_table(self, engine):
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
        class AnotherTable(Model):
            value = StrColumn()
            class Meta:
                table_name = "another_table"

        migrator = Migrator(engine)
        plan = await migrator.plan([AnotherTable])
        assert not plan.is_empty()


# ── down_statements の生成 ────────────────────────────────────


class TestDownStatements:
    async def test_new_table_down_is_drop_table(self, engine):
        """新規テーブル作成の DOWN は DROP TABLE。"""
        class TmpTable(Model):
            val = StrColumn()
            class Meta:
                table_name = "tmp_down_test"

        migrator = Migrator(engine)
        plan = await migrator.plan([TmpTable])
        assert any("DROP TABLE" in s and "tmp_down_test" in s for s in plan.down_statements)

    async def test_add_column_down_is_drop_column(self, engine):
        """ADD COLUMN の DOWN は DROP COLUMN。"""
        class ColModel(Model):
            name = StrColumn(nullable=False)
            extra = StrColumn(nullable=True)
            class Meta:
                table_name = "col_down_test"

        eng = engine
        # name カラムだけのテーブルを先に作成
        await eng._execute(
            "CREATE TABLE col_down_test (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)",
            [],
        )

        migrator = Migrator(eng)
        plan = await migrator.plan([ColModel])
        # extra カラム追加の DOWN は DROP COLUMN extra（クォート文字を含む）
        assert any("DROP COLUMN [extra]" in s or "DROP COLUMN extra" in s for s in plan.down_statements)

    async def test_apply_down_new_table(self, engine):
        """apply_down() で作成したテーブルを削除できる。"""
        class Tmp2(Model):
            val = StrColumn()
            class Meta:
                table_name = "tmp_apply_down"

        migrator = Migrator(engine)
        plan = await migrator.plan([Tmp2])
        await plan.apply()
        assert await migrator._table_exists("tmp_apply_down")

        await plan.apply_down()
        assert not await migrator._table_exists("tmp_apply_down")


# ── VersionedMigrator downgrade ───────────────────────────────


class TestVersionedMigratorDowngrade:
    async def test_downgrade_removes_history(self, engine):
        """downgrade() で履歴が削除される。"""
        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()
        await migrator.record("test_mig", down_sql="[]")

        hist_before = await migrator.history()
        assert len(hist_before) == 1

        n = await migrator.downgrade(steps=1)
        assert n == 1

        hist_after = await migrator.history()
        assert len(hist_after) == 0

    async def test_downgrade_executes_down_sql(self, engine):
        """downgrade() で DOWN SQL が実行される。"""
        class DgTable(Model):
            val = StrColumn()
            class Meta:
                table_name = "dg_table"

        migrator = VersionedMigrator(engine)
        plan = await migrator.plan([DgTable])
        await plan.apply()
        assert await migrator._table_exists("dg_table")

        import json
        await migrator.ensure_history_table()
        down_stmts = list(reversed(plan.down_statements))
        await migrator.record("dg_mig", down_sql=json.dumps(down_stmts))

        await migrator.downgrade(steps=1)
        assert not await migrator._table_exists("dg_table")

    async def test_downgrade_empty_history_returns_zero(self, engine):
        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()
        n = await migrator.downgrade()
        assert n == 0


# ── autogenerate + run_files ──────────────────────────────────


class TestAutogenerate:
    async def test_autogenerate_creates_file(self, engine):
        """autogenerate() でファイルが生成される。"""
        class AgModel(Model):
            title = StrColumn(nullable=False)
            class Meta:
                table_name = "ag_model"

        with tempfile.TemporaryDirectory() as tmpdir:
            migrator = Migrator(engine)
            path = await migrator.autogenerate([AgModel], tmpdir, name="create_ag_model")
            assert path is not None
            assert path.exists()
            content = path.read_text()
            assert "up = [" in content
            assert "down = [" in content
            assert "ag_model" in content

    async def test_autogenerate_returns_none_when_no_diff(self, engine):
        """差分がない場合は None を返す。"""
        migrator = Migrator(engine)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = await migrator.autogenerate([Author, Post], tmpdir)
            assert path is None

    async def test_autogenerate_sequential_numbering(self, engine):
        """2回目は 0002_ で始まる。"""
        class Seq1(Model):
            x = StrColumn()
            class Meta:
                table_name = "seq1"

        class Seq2(Model):
            y = StrColumn()
            class Meta:
                table_name = "seq2"

        with tempfile.TemporaryDirectory() as tmpdir:
            migrator = Migrator(engine)
            p1 = await migrator.autogenerate([Seq1], tmpdir, name="first")
            p2 = await migrator.autogenerate([Seq2], tmpdir, name="second")
            assert p1.name.startswith("0001_")
            assert p2.name.startswith("0002_")

    async def test_run_files_applies_up_sql(self, engine):
        """run_files() が up SQL を実行してテーブルを作成する。"""
        class RfModel(Model):
            name = StrColumn(nullable=False)
            class Meta:
                table_name = "rf_model"

        with tempfile.TemporaryDirectory() as tmpdir:
            migrator = VersionedMigrator(engine)
            await migrator.autogenerate([RfModel], tmpdir, name="create_rf")
            n = await migrator.run_files(tmpdir)
            assert n == 1
            assert await migrator._table_exists("rf_model")

    async def test_run_files_skips_applied(self, engine):
        """run_files() は適用済みをスキップする。"""
        class RfModel2(Model):
            name = StrColumn(nullable=False)
            class Meta:
                table_name = "rf_model2"

        with tempfile.TemporaryDirectory() as tmpdir:
            migrator = VersionedMigrator(engine)
            await migrator.autogenerate([RfModel2], tmpdir, name="init")
            await migrator.run_files(tmpdir)
            n2 = await migrator.run_files(tmpdir)  # 2回目はスキップ
            assert n2 == 0

    async def test_run_files_then_downgrade(self, engine):
        """run_files() → downgrade() でテーブルが削除される。"""
        class RfModel3(Model):
            name = StrColumn(nullable=False)
            class Meta:
                table_name = "rf_model3"

        with tempfile.TemporaryDirectory() as tmpdir:
            migrator = VersionedMigrator(engine)
            await migrator.autogenerate([RfModel3], tmpdir, name="create_rf3")
            await migrator.run_files(tmpdir)
            assert await migrator._table_exists("rf_model3")

            await migrator.downgrade(steps=1)
            assert not await migrator._table_exists("rf_model3")
