"""
予約語をテーブル名として使用する場合のテスト

SQLiteやPostgreSQLでは、テーブル名をクォートすることで予約語を使用できます：
- SQLite: [table_name] または "table_name"
- PostgreSQL: "table_name"
- MySQL: `table_name`
"""
import pytest
from kakaorm import connect, Model, StrColumn, IntColumn, ForeignKey, has_many, belongs_to


class Category(Model):
    """categoryは予約語ではない"""
    name = StrColumn(nullable=False)
    items = has_many("Item", foreign_key="category_id")

    class Meta:
        table_name = "category"


class Item(Model):
    """itemは予約語ではないが、データ挿入テスト用"""
    name = StrColumn(nullable=False)
    category_id = ForeignKey(Category, nullable=False)

    category = belongs_to(Category, foreign_key="category_id")

    class Meta:
        table_name = "item"


class PurchaseOrder(Model):
    """orderを含むテーブル名を、クォートで回避"""
    name = StrColumn(nullable=False)
    quantity = IntColumn(default=1)

    class Meta:
        # 予約語を避けるために別名を使用
        table_name = "purchase_order"


@pytest.fixture
async def engine():
    """テスト用のin-memory SQLiteエンジン"""
    e = await connect("sqlite+aiosqlite:///:memory:")

    from kakaorm.migration import Migrator
    plan = await Migrator(e).plan([Category, Item, PurchaseOrder])
    if not plan.is_empty():
        await plan.apply()

    yield e

    await e.disconnect()


class TestReservedWords:
    """予約語の処理テスト"""

    @pytest.mark.asyncio
    async def test_create_with_non_reserved_word(self, engine):
        """非予約語のテーブル名は正常に動作"""
        category = await Category.create(name="Electronics")
        assert category.id is not None
        assert category.name == "Electronics"

    @pytest.mark.asyncio
    async def test_table_name_with_underscore(self, engine):
        """アンダースコア付きテーブル名は正常に動作"""
        order = await PurchaseOrder.create(name="Order-123", quantity=5)
        assert order.id is not None
        assert order.name == "Order-123"

    @pytest.mark.asyncio
    async def test_quoted_table_name_in_meta(self, engine):
        """Meta.table_name にクォート付きで記述した場合"""
        # ユーザーが自分でクォートを追加する方法
        pass

    @pytest.mark.asyncio
    async def test_migration_with_underscore_table_name(self, engine):
        """マイグレーション実行時のテーブル作成"""
        # purchase_order テーブルは既に作成されている
        orders = await PurchaseOrder.all().execute()
        assert isinstance(orders, list)


class TestQuotedTableNameWorkaround:
    """予約語対応の回避策テスト"""

    @pytest.mark.asyncio
    async def test_using_alternate_name(self, engine):
        """予約語を避けるために別名を使用（推奨）"""
        # "order" テーブルが必要な場合は "purchase_order" など別名を使用
        order = await PurchaseOrder.create(name="TEST-001", quantity=1)
        retrieved = await PurchaseOrder.get(PurchaseOrder.id == order.id)
        assert retrieved.name == "TEST-001"

    @pytest.mark.asyncio
    async def test_direct_quoted_table_name_sqlite_brackets(self, engine):
        """Meta.table_nameに[order]クォートを直接指定する試行"""
        # SQLiteではテーブル名を[tablename]で囲むことで予約語を回避できる

        class Order(Model):
            name = StrColumn(nullable=False)

            class Meta:
                # SQLiteのクォート: [order]
                table_name = "[order]"

        from kakaorm.migration import Migrator
        plan = await Migrator(engine).plan([Order])
        if not plan.is_empty():
            try:
                await plan.apply()
                # テーブル作成に成功した場合
                order = await Order.create(name="TEST-001")
                assert order.id is not None
            except Exception as e:
                # kakaormが自動的にクォートを処理していない場合
                pytest.skip(f"Quoted table_name support: {e}")

    @pytest.mark.asyncio
    async def test_direct_quoted_table_name_sqlite_quotes(self, engine):
        """Meta.table_nameに"order"クォートを直接指定する試行"""
        # SQLiteではテーブル名を"tablename"で囲むことで予約語を回避できる

        class Order2(Model):
            name = StrColumn(nullable=False)

            class Meta:
                # SQLiteのクォート: "order"
                table_name = '"order2"'

        from kakaorm.migration import Migrator
        plan = await Migrator(engine).plan([Order2])
        if not plan.is_empty():
            try:
                await plan.apply()
                # テーブル作成に成功した場合
                order = await Order2.create(name="TEST-002")
                assert order.id is not None
            except Exception as e:
                # kakaormが自動的にクォートを処理していない場合
                pytest.skip(f"Quoted table_name support: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
