"""
リレーション定義 テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, ForeignKey, has_many, belongs_to


class Writer(Model):
    name  = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    # 逆参照: このライターの記事一覧
    articles = has_many("Article", foreign_key="writer_id")

    class Meta:
        table_name = "writer"


class Article(Model):
    title     = StrColumn(nullable=False)
    writer_id = ForeignKey(Writer, nullable=True)
    # 前向き FK: この記事のライター
    writer = belongs_to(Writer, foreign_key="writer_id")

    class Meta:
        table_name = "article"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Writer)
    await eng.create_table(Article)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    alice = await Writer.create(name="Alice", email="alice@example.com")
    bob   = await Writer.create(name="Bob",   email="bob@example.com")
    a1 = await Article.create(title="Python Tips",    writer_id=alice.id)
    a2 = await Article.create(title="Async Patterns", writer_id=alice.id)
    a3 = await Article.create(title="Go Basics",      writer_id=bob.id)
    return {"alice": alice, "bob": bob, "a1": a1, "a2": a2, "a3": a3}


class TestForwardRelationship:
    async def test_forward_fk_returns_related_instance(self, seeded):
        article = await Article.get(Article.title == "Python Tips")
        writer = await article.writer
        assert writer is not None
        assert writer.name == "Alice"

    async def test_forward_fk_returns_none_when_null(self, engine):
        article = await Article.create(title="Orphan Article", writer_id=None)
        writer = await article.writer
        assert writer is None

    async def test_forward_fk_proxy_repr(self, seeded):
        article = await Article.get(Article.title == "Python Tips")
        proxy = article.writer
        assert "RelationshipProxy" in repr(proxy)

    async def test_class_access_returns_descriptor(self):
        """クラスアクセスではデスクリプタ自体が返ること。"""
        from kakaorm.relationship import belongs_to as BelongsTo
        assert isinstance(Article.writer, BelongsTo)


class TestReverseRelationship:
    async def test_reverse_returns_list(self, seeded):
        writer = await Writer.get(Writer.name == "Alice")
        articles = await writer.articles
        assert isinstance(articles, list)
        assert len(articles) == 2

    async def test_reverse_correct_items(self, seeded):
        writer = await Writer.get(Writer.name == "Alice")
        articles = await writer.articles
        titles = {a.title for a in articles}
        assert "Python Tips" in titles
        assert "Async Patterns" in titles

    async def test_reverse_empty_when_no_articles(self, seeded):
        writer = await Writer.create(name="Charlie", email="charlie@example.com")
        articles = await writer.articles
        assert articles == []

    async def test_reverse_single_item(self, seeded):
        writer = await Writer.get(Writer.name == "Bob")
        articles = await writer.articles
        assert len(articles) == 1
        assert articles[0].title == "Go Basics"


class TestStringModelReference:
    async def test_string_reference_resolves(self, seeded):
        """related_model を文字列で指定した逆参照が解決できること。"""
        writer = await Writer.get(Writer.name == "Alice")
        articles = await writer.articles  # Writer.articles は "Article" 文字列参照
        assert len(articles) == 2


class TestForeignKeyCascade:
    async def test_on_delete_cascade(self, seeded):
        """親レコード削除時に子レコードが CASCADE で自動削除されること。"""
        alice = await Writer.get(Writer.name == "Alice")
        alice_id = alice.id
        await alice.delete()
        orphans = await Article.where(Article.writer_id == alice_id)
        assert orphans == [], f"CASCADE が機能せず記事が残っています: {orphans}"

    async def test_other_rows_unaffected(self, seeded):
        """CASCADE は削除した親に紐づく子のみを削除し、他の行は残ること。"""
        alice = await Writer.get(Writer.name == "Alice")
        await alice.delete()
        bob_articles = await Article.where(Article.writer_id != None)  # noqa: E711
        assert len(bob_articles) == 1
        assert bob_articles[0].title == "Go Basics"

    async def test_fk_ddl_quoted(self, engine):
        """REFERENCES 句の参照先テーブル名・カラム名がクォートされること。"""
        rows = await engine.fetch(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='article'"
        )
        assert rows, "article テーブルが見つかりません"
        ddl = rows[0]["sql"]
        # SQLite の quote_identifier は [name] 形式
        assert "REFERENCES [writer]([id])" in ddl, (
            f"REFERENCES 句のクォートが不正です: {ddl}"
        )
