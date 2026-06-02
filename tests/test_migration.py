"""
Migrator テスト
"""

import tempfile
import pathlib
import datetime
import pytest
import kakaorm
from kakaorm import Model, StrColumn, ForeignKey, DateTimeColumn
from kakaorm.migration import Migrator, VersionedMigrator
from kakaorm.relationship import has_many, belongs_to
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


# ── nullable=False + auto_now_add の ADD COLUMN ───────────────


class TestAutoNowAddColumn:
    async def test_add_auto_now_add_not_null_to_existing_table(self, engine):
        """既存行があるテーブルへ auto_now_add=True + nullable=False 列の ADD が成功すること。"""
        class Ev(Model):
            title = StrColumn(nullable=False)
            class Meta:
                table_name = "ev_auto_now"

        class EvV2(Model):
            title      = StrColumn(nullable=False)
            created_at = DateTimeColumn(auto_now_add=True, nullable=False)
            updated_at = DateTimeColumn(auto_now=True, nullable=False)
            class Meta:
                table_name = "ev_auto_now"

        await engine.create_table(Ev)
        await Ev.create(title="existing")

        plan = await Migrator(engine).plan([EvV2])
        assert not plan.is_empty()
        await plan.apply()  # 例外なく通ること

    async def test_existing_rows_get_non_null_fallback(self, engine):
        """既存行の auto_now_add 列が NULL にならないこと。"""
        class Ev2(Model):
            title = StrColumn(nullable=False)
            class Meta:
                table_name = "ev_fallback"

        class Ev2V2(Model):
            title      = StrColumn(nullable=False)
            created_at = DateTimeColumn(auto_now_add=True, nullable=False)
            class Meta:
                table_name = "ev_fallback"

        await engine.create_table(Ev2)
        await Ev2.create(title="old row")

        await Migrator(engine).run([Ev2V2])
        rows = await engine.fetch("SELECT created_at FROM [ev_fallback]")
        assert all(r["created_at"] is not None for r in rows), "既存行に NULL が入っています"

    async def test_new_inserts_use_auto_now_add_not_fallback(self, engine):
        """マイグレーション後の新規 INSERT では auto_now_add が適用されること。"""
        class Ev3(Model):
            title = StrColumn(nullable=False)
            class Meta:
                table_name = "ev_new_insert"

        class Ev3V2(Model):
            title      = StrColumn(nullable=False)
            created_at = DateTimeColumn(auto_now_add=True, nullable=False)
            class Meta:
                table_name = "ev_new_insert"

        await engine.create_table(Ev3)
        await Migrator(engine).run([Ev3V2])

        item = await Ev3V2.create(title="new row")
        assert isinstance(item.created_at, datetime.datetime), (
            f"auto_now_add が適用されていません: {item.created_at!r}"
        )

    async def test_add_column_ddl_uses_adapt_ddl(self, engine):
        """ADD COLUMN の DDL が _adapt_ddl() を通じて方言変換されること (SQLite: DATETIME)。"""
        class Ev4(Model):
            title = StrColumn(nullable=False)
            class Meta:
                table_name = "ev_ddl_check"

        class Ev4V2(Model):
            title      = StrColumn(nullable=False)
            created_at = DateTimeColumn(auto_now_add=True, nullable=False)
            class Meta:
                table_name = "ev_ddl_check"

        await engine.create_table(Ev4)
        plan = await Migrator(engine).plan([Ev4V2])
        add_stmts = [s for s in plan.statements if "ADD COLUMN" in s]
        assert add_stmts, "ADD COLUMN 文が生成されていません"
        # SQLite では TIMESTAMP WITH TIME ZONE → DATETIME に変換される
        assert "TIMESTAMP WITH TIME ZONE" not in add_stmts[0], (
            f"_adapt_ddl が適用されていません: {add_stmts[0]}"
        )
        assert "DATETIME" in add_stmts[0], (
            f"SQLite 型変換が不正です: {add_stmts[0]}"
        )


# ── VersionedMigrator.run([Model]) ────────────────────────────


class TestVersionedMigratorRun:
    async def test_versioned_run_applies_missing_table(self, engine):
        """VersionedMigrator でも run([Model]) でテーブルを作成できる。"""
        class VmTable(Model):
            label = StrColumn(nullable=False)
            class Meta:
                table_name = "vm_table"

        plan = await VersionedMigrator(engine).run([VmTable])
        assert not plan.is_empty()
        assert await Migrator(engine)._table_exists("vm_table")

    async def test_versioned_run_idempotent(self, engine):
        """run([Model]) は 2 回呼んでも差分なしを返す。"""
        class VmTable2(Model):
            label = StrColumn(nullable=False)
            class Meta:
                table_name = "vm_table2"

        await VersionedMigrator(engine).run([VmTable2])
        plan2 = await VersionedMigrator(engine).run([VmTable2])
        assert plan2.is_empty()

    async def test_run_manual_applies_callable(self, engine):
        """run_manual() が callable を実行して履歴に記録する。"""
        class ManualTable(Model):
            x = StrColumn()
            class Meta:
                table_name = "manual_table"

        migrator = VersionedMigrator(engine)
        n = await migrator.run_manual({
            "001_create_manual": lambda: engine.create_table(ManualTable),
        })
        assert n == 1
        assert await migrator._table_exists("manual_table")

        # 2 回目はスキップされる
        n2 = await migrator.run_manual({
            "001_create_manual": lambda: engine.create_table(ManualTable),
        })
        assert n2 == 0


# ── DDL クォート確認 ───────────────────────────────────────────


class TestMigratorDdlQuoting:
    async def test_create_table_ddl_uses_quoted_fk(self, engine):
        """Migrator._build_create_table() が REFERENCES をクォート済みで生成する。"""
        class Owner(Model):
            name = StrColumn(nullable=False)
            class Meta:
                table_name = "owner"

        class Item(Model):
            owner_id = ForeignKey(Owner, nullable=True)
            class Meta:
                table_name = "item"

        migrator = Migrator(engine)
        sql = migrator._build_create_table(Item)
        # SQLite の quote_identifier は [name] 形式
        assert "REFERENCES [owner]([id])" in sql, (
            f"FK が未クォートです: {sql}"
        )

    async def test_plan_add_column_ddl_quoted(self, engine):
        """plan() の ADD COLUMN DDL にクォートが含まれる。"""
        class FkTarget(Model):
            name = StrColumn(nullable=False)
            class Meta:
                table_name = "fk_target"

        class FkSource(Model):
            ref_id = ForeignKey(FkTarget, nullable=True)
            class Meta:
                table_name = "fk_source"

        # ref_id なしのテーブルを先に作成
        await engine._execute(
            "CREATE TABLE fk_target (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)", []
        )
        await engine._execute(
            "CREATE TABLE fk_source (id INTEGER PRIMARY KEY AUTOINCREMENT)", []
        )

        plan = await Migrator(engine).plan([FkSource])
        add_stmts = [s for s in plan.statements if "ADD COLUMN" in s]
        assert add_stmts, "ADD COLUMN 文が生成されていません"
        assert "REFERENCES [fk_target]([id])" in add_stmts[0], (
            f"ADD COLUMN の FK が未クォートです: {add_stmts[0]}"
        )


# ── validate_relationships ────────────────────────────────────


class TestValidateRelationships:
    def test_valid_string_reference_passes(self, engine):
        """正しいモデル名の文字列参照は例外なく通ること。"""
        class Dept(Model):
            name  = StrColumn(nullable=False)
            staff = has_many("StaffMember", foreign_key="dept_id")
            class Meta:
                table_name = "dept_valid"

        class StaffMember(Model):
            name    = StrColumn(nullable=False)
            dept_id = ForeignKey(Dept, nullable=True)
            class Meta:
                table_name = "staff_valid"

        Migrator(engine).validate_relationships([Dept, StaffMember])  # 例外なし

    def test_typo_in_model_name_raises_lookup_error(self, engine):
        """存在しないモデル名を参照すると LookupError が送出されること。"""
        class Owner(Model):
            name  = StrColumn(nullable=False)
            items = has_many("ItmTypo", foreign_key="owner_id")  # タイポ
            class Meta:
                table_name = "owner_typo"

        with pytest.raises(LookupError, match="ItmTypo"):
            Migrator(engine).validate_relationships([Owner])

    def test_multiple_errors_reported_at_once(self, engine):
        """複数の未解決参照がある場合にまとめて報告されること。"""
        class Hub(Model):
            name  = StrColumn(nullable=False)
            alpha = has_many("AlphaX", foreign_key="hub_id")
            beta  = has_many("BetaX",  foreign_key="hub_id")
            class Meta:
                table_name = "hub_multi"

        with pytest.raises(LookupError) as exc_info:
            Migrator(engine).validate_relationships([Hub])
        msg = str(exc_info.value)
        assert "AlphaX" in msg
        assert "BetaX" in msg

    def test_class_reference_not_validated(self, engine):
        """クラス直接参照（文字列でない）は検証スキップされること。"""
        class Parent(Model):
            name     = StrColumn(nullable=False)
            class Meta:
                table_name = "parent_class_ref"

        class Child(Model):
            name      = StrColumn(nullable=False)
            parent_id = ForeignKey(Parent, nullable=True)
            parent    = belongs_to(Parent, foreign_key="parent_id")
            class Meta:
                table_name = "child_class_ref"

        Migrator(engine).validate_relationships([Parent, Child])  # 例外なし

    async def test_plan_raises_on_typo(self, engine):
        """plan() が文字列参照エラーを事前に検出して LookupError を送出すること。"""
        class Shop(Model):
            name     = StrColumn(nullable=False)
            products = has_many("PrdctTypo", foreign_key="shop_id")
            class Meta:
                table_name = "shop_plan_typo"

        with pytest.raises(LookupError, match="PrdctTypo"):
            await Migrator(engine).plan([Shop])

    async def test_plan_proceeds_normally_with_valid_references(self, engine):
        """有効な文字列参照では plan() が正常に差分を返すこと。"""
        class Library(Model):
            name  = StrColumn(nullable=False)
            books = has_many("BookItem", foreign_key="library_id")
            class Meta:
                table_name = "library_valid"

        class BookItem(Model):
            title      = StrColumn(nullable=False)
            library_id = ForeignKey(Library, nullable=True)
            class Meta:
                table_name = "book_item_valid"

        plan = await Migrator(engine).plan([Library, BookItem])
        assert not plan.is_empty()
