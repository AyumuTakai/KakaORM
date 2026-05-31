"""
イベントフック テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn


class AuditedUser(Model):
    name    = StrColumn(nullable=False)
    version = IntColumn(nullable=False, default=0)
    log: list = []  # テスト用の呼び出し記録

    class Meta:
        table_name = "audited_user"

    async def before_insert(self) -> None:
        AuditedUser.log.append("before_insert")

    async def after_insert(self) -> None:
        AuditedUser.log.append("after_insert")

    async def before_update(self) -> None:
        AuditedUser.log.append("before_update")
        self.version = (self.version or 0) + 1

    async def after_update(self) -> None:
        AuditedUser.log.append("after_update")

    async def before_delete(self) -> None:
        AuditedUser.log.append("before_delete")

    async def after_delete(self) -> None:
        AuditedUser.log.append("after_delete")


@pytest.fixture(autouse=True)
def clear_log():
    """各テストの前後でログをリセットする。"""
    AuditedUser.log.clear()
    yield
    AuditedUser.log.clear()


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(AuditedUser)
    yield eng
    await eng.disconnect()


class TestEventHooks:
    async def test_insert_hooks_called_in_order(self, engine):
        await AuditedUser.create(name="Alice")
        assert AuditedUser.log == ["before_insert", "after_insert"]

    async def test_update_hooks_called_in_order(self, engine):
        user = await AuditedUser.create(name="Bob")
        AuditedUser.log.clear()

        user.name = "Bobby"
        await user.save()
        assert AuditedUser.log == ["before_update", "after_update"]

    async def test_delete_hooks_called_in_order(self, engine):
        user = await AuditedUser.create(name="Carol")
        AuditedUser.log.clear()

        await user.delete()
        assert AuditedUser.log == ["before_delete", "after_delete"]

    async def test_before_update_can_mutate_data(self, engine):
        """before_update でフィールドを変更できること。"""
        user = await AuditedUser.create(name="Dave")
        assert user.version == 0

        user.name = "David"
        await user.save()

        refetched = await AuditedUser.get(AuditedUser.id == user.id)
        assert refetched.version == 1

        refetched.name = "David Jr."
        await refetched.save()

        refetched2 = await AuditedUser.get(AuditedUser.id == user.id)
        assert refetched2.version == 2

    async def test_hooks_not_called_on_bulk_queryset_update(self, engine):
        """QuerySet.update() はフックを経由しない（設計通り）。"""
        await AuditedUser.create(name="Eve")
        AuditedUser.log.clear()

        await AuditedUser.all().update(name="Eve2")
        # フックは呼ばれないことを確認
        assert AuditedUser.log == []

    async def test_no_hook_raises_on_base_model(self):
        """基底 Model のフックは何もせず正常終了すること。"""
        class Bare(Model):
            x = IntColumn()
            class Meta:
                table_name = "bare_hook_test"

        bare = Bare(x=1)
        bare._is_new = False
        # フックメソッドは await できること（例外なし）
        await bare.before_insert()
        await bare.after_insert()
        await bare.before_update()
        await bare.after_update()
        await bare.before_delete()
        await bare.after_delete()
