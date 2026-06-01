"""
予約語処理の動作確認テスト

kakaormは予約語をMeta.table_nameでクォートすることで対応可能であることを確認
"""
import pytest
from kakaorm import connect, Model, StrColumn, IntColumn


@pytest.fixture
async def engine():
    e = await connect("sqlite+aiosqlite:///:memory:")
    yield e
    await e.disconnect()


class TestReservedWordQuoting:
    """予約語をテーブル名として使用 - Engine が自動的にクォート"""

    @pytest.mark.asyncio
    async def test_sqlite_bracket_quoting(self, engine):
        """予約語をテーブル名として使用 - SQLiteで自動クォート"""

        class Order(Model):
            name = StrColumn(nullable=False)
            quantity = IntColumn(default=1)

            class Meta:
                table_name = "order"  # クォート文字なし - Engine が自動処理

        from kakaorm.migration import Migrator
        plan = await Migrator(engine).plan([Order])
        if not plan.is_empty():
            await plan.apply()

        # テーブル作成成功 → クォート対応OK
        order = await Order.create(name="Item-001", quantity=5)
        assert order.id is not None
        assert order.name == "Item-001"

        # 取得動作確認
        retrieved = await Order.get(Order.id == order.id)
        assert retrieved.name == "Item-001"

    @pytest.mark.asyncio
    async def test_sqlite_double_quote_quoting(self, engine):
        """予約語selectをテーブル名として使用"""

        class Selection(Model):
            """selectは予約語"""
            name = StrColumn(nullable=False)

            class Meta:
                table_name = "select"  # クォート文字なし - Engine が自動処理

        from kakaorm.migration import Migrator
        plan = await Migrator(engine).plan([Selection])
        if not plan.is_empty():
            await plan.apply()

        # テーブル作成成功 → クォート対応OK
        item = await Selection.create(name="Option-1")
        assert item.id is not None

    @pytest.mark.asyncio
    async def test_multiple_quoted_reserved_words(self, engine):
        """複数の予約語テーブルを同時に使用"""

        class Delete_(Model):
            """deleteは予約語"""
            name = StrColumn(nullable=False)

            class Meta:
                table_name = "delete"  # クォート文字なし - Engine が自動処理

        class Insert_(Model):
            """insertは予約語"""
            name = StrColumn(nullable=False)

            class Meta:
                table_name = "insert"  # クォート文字なし - Engine が自動処理

        from kakaorm.migration import Migrator
        plan = await Migrator(engine).plan([Delete_, Insert_])
        if not plan.is_empty():
            await plan.apply()

        # 両方のテーブルが動作
        d = await Delete_.create(name="del")
        i = await Insert_.create(name="ins")

        assert d.id is not None
        assert i.id is not None

    @pytest.mark.asyncio
    async def test_common_reserved_words(self, engine):
        """一般的なSQLの予約語リスト - Engine が自動的にクォート"""

        reserved_words = [
            # SELECT, INSERT, UPDATE, DELETE, WHERE, FROM, ORDER, GROUP, HAVING, LIMIT, OFFSET, ...
            "select",
            "insert",
            "update",
            "delete",
            "where",
            "from",
            "order",
            "group",
            "having",
            "limit",
        ]

        # 複数の予約語をテストするのは現実的でないため、いくつかに限定
        test_words = ["order", "group", "select"]

        for word in test_words:
            # 動的にモデルクラスを作成
            model_class = type(
                f"Model_{word}",
                (Model,),
                {
                    "name": StrColumn(nullable=False),
                    "_meta": type("Meta", (), {"table_name": word}),
                }
            )

            from kakaorm.migration import Migrator
            plan = await Migrator(engine).plan([model_class])
            if not plan.is_empty():
                await plan.apply()

            # 簡単な動作確認
            instance = await model_class.create(name=f"test-{word}")
            assert instance.id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
