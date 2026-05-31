"""
DROP TABLE CASCADE テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, ForeignKey


class Department(Model):
    name = StrColumn(nullable=False)
    class Meta:
        table_name = "department"


class Staff(Model):
    name     = StrColumn(nullable=False)
    dept_id  = ForeignKey(Department, nullable=True)
    class Meta:
        table_name = "staff"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Department)
    await eng.create_table(Staff)
    yield eng
    await eng.disconnect()


class TestDropTable:
    async def test_drop_table_basic(self, engine):
        """テーブルを正常に削除できること。"""
        await engine.create_table(Department, if_not_exists=True)
        await engine.drop_table(Department)
        # 再作成できれば削除されている
        await engine.create_table(Department)

    async def test_drop_table_if_exists(self, engine):
        """if_exists=True なら存在しないテーブルでもエラーにならないこと。"""
        class Ghost(Model):
            x = StrColumn()
            class Meta:
                table_name = "ghost_table"

        await engine.drop_table(Ghost, if_exists=True)  # 例外が出ないこと

    async def test_drop_table_cascade_sqlite_no_error(self, engine):
        """SQLite では cascade=True を渡しても例外が出ないこと（無視される）。"""
        await engine.create_table(Department, if_not_exists=True)
        # SQLite は CASCADE を無視して DROP するだけ
        await engine.drop_table(Department, cascade=True)
        # 再作成できること
        await engine.create_table(Department)

    async def test_drop_cascade_param_accepted(self, engine):
        """cascade パラメータが Engine に受け付けられること。"""
        import inspect
        sig = inspect.signature(engine.drop_table)
        assert "cascade" in sig.parameters
