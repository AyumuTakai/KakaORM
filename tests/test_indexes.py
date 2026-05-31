"""
複合インデックス テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn


class Product(Model):
    name     = StrColumn(nullable=False)
    category = StrColumn(nullable=False)
    price    = IntColumn(nullable=False)

    class Meta:
        table_name = "product"
        indexes = [
            ("category", "price"),  # 複合インデックス
            ("name",),              # 単一カラムインデックス
        ]


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Product)
    yield eng
    await eng.disconnect()


class TestIndexes:
    async def test_create_table_with_indexes(self, engine):
        """インデックス付きテーブルが正常に作成されること。"""
        p = await Product.create(name="Widget", category="tools", price=500)
        assert p.name == "Widget"

    async def test_index_exists_in_sqlite_master(self, engine):
        """CREATE INDEX が SQLite に反映されていること。"""
        rows = await engine.fetch(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='product'"
        )
        index_names = {r["name"] for r in rows}
        assert "idx_product_category_price" in index_names
        assert "idx_product_name" in index_names

    async def test_indexed_columns_queryable(self, engine):
        """インデックス付きカラムで正常にクエリできること。"""
        await Product.create(name="Bolt",   category="fasteners", price=10)
        await Product.create(name="Wrench", category="tools",     price=300)
        await Product.create(name="Screw",  category="fasteners", price=5)

        results = await Product.filter(Product.category == "fasteners").order_by(Product.price.asc)
        assert len(results) == 2
        assert results[0].price == 5
        assert results[1].price == 10

    async def test_meta_indexes_stored(self):
        """Meta.indexes が ModelMeta に正しく格納されること。"""
        assert ("category", "price") in Product._meta.indexes
        assert ("name",) in Product._meta.indexes
