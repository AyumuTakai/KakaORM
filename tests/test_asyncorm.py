"""
kakaorm テストスイート
========================
aiosqlite を使ったインメモリ DB でエンジン・クエリ・モデル・マイグレーションを統合テストする。
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kakaorm import Model, IntColumn, StrColumn, FloatColumn, BoolColumn, DateTimeColumn, connect
from kakaorm.migration import Migrator

# ── テスト用モデル定義 ────────────────────────────────────────

class Author(Model):
    name = StrColumn(nullable=False)
    email = StrColumn(unique=True)
    bio = StrColumn(nullable=True)

    class Meta:
        table_name = "author"


class Post(Model):
    title = StrColumn(nullable=False)
    body = StrColumn(nullable=True)
    views = IntColumn(nullable=False, default=0)
    published = BoolColumn(nullable=False, default=False)
    score = FloatColumn(nullable=True)

    class Meta:
        table_name = "post"


# ── テストユーティリティ ──────────────────────────────────────

passed = 0
failed = 0

async def run_test(name: str, coro):
    global passed, failed
    try:
        await coro
        print(f"  ✓ {name}")
        passed += 1
    except AssertionError as e:
        print(f"  ✗ {name}: AssertionError: {e}")
        failed += 1
    except Exception as e:
        print(f"  ✗ {name}: {type(e).__name__}: {e}")
        failed += 1

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}\n  actual:   {actual!r}\n  expected: {expected!r}")

# ── テストケース ──────────────────────────────────────────────

async def test_column_meta_operators():
    """WhereClause の演算子オーバーロードが正しく SQL を生成する。"""
    clause = Post.views >= 100
    assert "views" in clause.sql and ">=" in clause.sql
    assert clause.params == [100]

    and_clause = (Post.views >= 10) & (Post.published == True)
    assert "AND" in and_clause.sql

    or_clause = (Post.views >= 10) | (Post.published == True)
    assert "OR" in or_clause.sql

    not_clause = ~(Post.views >= 10)
    assert "NOT" in not_clause.sql

    null_clause = Post.score == None
    assert "IS NULL" in null_clause.sql
    assert null_clause.params == []

    like_clause = Author.name.like("A%")
    assert "LIKE" in like_clause.sql

    in_clause = Post.views.in_([1, 2, 3])
    assert "IN" in in_clause.sql and len(in_clause.params) == 3

    between_clause = Post.score.between(1.0, 5.0)
    assert "BETWEEN" in between_clause.sql


async def test_queryset_sql_generation():
    """QuerySet が正しい SQL 文字列を生成する。"""
    qs = Post.filter(Post.views >= 100).order_by(Post.views.desc).limit(10).offset(5)
    sql, params = qs._build_sql()
    assert "SELECT" in sql
    assert "WHERE" in sql
    assert "ORDER BY" in sql
    assert "LIMIT 10" in sql
    assert "OFFSET 5" in sql
    assert params == [100]

    # 複数 filter は AND 結合
    qs2 = Post.filter(Post.views >= 10).filter(Post.published == True)
    sql2, params2 = qs2._build_sql()
    assert "AND" in sql2

    # select() で特定カラムのみ
    qs3 = Post.all().select(Post.title, Post.views)
    sql3, _ = qs3._build_sql()
    assert "SELECT title, views" in sql3
    assert "*" not in sql3


async def test_model_instantiation():
    """Model のインスタンス化とフィールドアクセス。"""
    post = Post(title="Hello kakaorm", views=42)
    assert post.title == "Hello kakaorm"
    assert post.views == 42
    assert post.published == False  # default

    try:
        Post(unknown_field="oops")
        raise AssertionError("Should have raised TypeError")
    except TypeError:
        pass  # 期待通り


async def test_create_and_fetch(engine):
    """INSERT → SELECT の基本フロー。"""
    author = await Author.create(name="Alice", email="alice@example.com")
    assert author.id is not None
    assert author.name == "Alice"

    fetched = await Author.get(Author.email == "alice@example.com")
    assert fetched.name == "Alice"
    assert fetched.id == author.id


async def test_filter_and_count(engine):
    """フィルタとカウントが正しく動く。"""
    await Author.create(name="Bob", email="bob@example.com")
    await Author.create(name="Charlie", email="charlie@example.com")

    total = await Author.all().count()
    assert total >= 2

    bobs = await Author.filter(Author.name == "Bob")
    assert len(bobs) == 1
    assert bobs[0].name == "Bob"


async def test_update_instance(engine):
    """save() で UPDATE が実行される。"""
    author = await Author.create(name="Dave", email="dave@example.com")
    original_id = author.id

    author.name = "David"
    await author.save()

    refetched = await Author.get(Author.id == original_id)
    assert refetched.name == "David"


async def test_delete_instance(engine):
    """delete() でレコードが削除される。"""
    author = await Author.create(name="Eve", email="eve@example.com")
    pk = author.id

    await author.delete()

    result = await Author.get_or_none(Author.id == pk)
    assert result is None


async def test_queryset_update(engine):
    """QuerySet.update() で一括更新。"""
    await Post.create(title="Draft1", views=0, published=False)
    await Post.create(title="Draft2", views=0, published=False)

    updated = await Post.filter(Post.published == False).update(views=999)
    assert updated >= 2

    posts = await Post.filter(Post.views == 999)
    assert len(posts) >= 2


async def test_queryset_delete(engine):
    """QuerySet.delete() で一括削除。"""
    await Post.create(title="ToDelete", views=0, published=False)
    before = await Post.filter(Post.title == "ToDelete").count()
    assert before >= 1

    deleted = await Post.filter(Post.title == "ToDelete").delete()
    assert deleted >= 1

    after = await Post.filter(Post.title == "ToDelete").count()
    assert after == 0


async def test_first_and_last(engine):
    """first() と last() が正しいレコードを返す。"""
    await Post.create(title="Alpha", views=1)
    await Post.create(title="Beta", views=2)

    first = await Post.all().order_by(Post.views.asc).first()
    assert first is not None
    assert first.views <= 2  # 最小

    last = await Post.last()
    assert last is not None


async def test_exists(engine):
    """exists() が正しいbool値を返す。"""
    await Author.create(name="Exists", email="exists@example.com")

    yes = await Author.filter(Author.name == "Exists").exists()
    no = await Author.filter(Author.name == "NoSuchUser12345").exists()

    assert yes is True
    assert no is False


async def test_not_found(engine):
    """get() が存在しないレコードで NotFound を送出する。"""
    try:
        await Author.get(Author.id == 99999)
        raise AssertionError("Should have raised NotFound")
    except Author.NotFound:
        pass  # 期待通り


async def test_async_for(engine):
    """async for ループで QuerySet をイテレーションできる。"""
    await Post.create(title="IterPost1", views=10)
    await Post.create(title="IterPost2", views=20)

    collected = []
    async for post in Post.filter(Post.title.like("IterPost%")):
        collected.append(post.title)

    assert len(collected) >= 2


async def test_migration_plan(engine):
    """Migrator が差分プランを生成する。"""
    migrator = Migrator(engine)

    # Author テーブルはすでに作成済み → 差分なし (カラム追加なし)
    plan = await migrator.plan([Author, Post])
    # テーブルは CREATE 済みなので statement が空のはず
    non_warning = [s for s in plan.statements if not s.startswith("--")]
    # 既存テーブルへの新カラムがないので 0
    assert len(non_warning) == 0, f"Unexpected statements: {non_warning}"


async def test_to_dict():
    """to_dict() がすべてのフィールドを返す。"""
    post = Post(title="Dict Test", views=5)
    d = post.to_dict()
    assert d["title"] == "Dict Test"
    assert d["views"] == 5
    assert "published" in d


# ── メイン実行 ────────────────────────────────────────────────

async def main():
    print("\n━━━ kakaorm テストスイート ━━━\n")

    # エンジン非依存テスト
    print("[ ユニットテスト — エンジン不要 ]")
    await run_test("Column演算子オーバーロード", test_column_meta_operators())
    await run_test("QuerySet SQL生成", test_queryset_sql_generation())
    await run_test("Modelインスタンス化", test_model_instantiation())
    await run_test("to_dict()", test_to_dict())

    # インメモリ SQLite を使った統合テスト
    print("\n[ 統合テスト — aiosqlite in-memory ]")
    try:
        engine = await connect("sqlite+aiosqlite:///:memory:")
        await engine.create_table(Author)
        await engine.create_table(Post)

        await run_test("CREATE & FETCH", test_create_and_fetch(engine))
        await run_test("FILTER & COUNT", test_filter_and_count(engine))
        await run_test("UPDATE インスタンス", test_update_instance(engine))
        await run_test("DELETE インスタンス", test_delete_instance(engine))
        await run_test("QuerySet 一括UPDATE", test_queryset_update(engine))
        await run_test("QuerySet 一括DELETE", test_queryset_delete(engine))
        await run_test("first() & last()", test_first_and_last(engine))
        await run_test("exists()", test_exists(engine))
        await run_test("NotFound 例外", test_not_found(engine))
        await run_test("async for イテレーション", test_async_for(engine))
        await run_test("Migration プラン生成", test_migration_plan(engine))

        await engine.disconnect()
    except ImportError:
        print("  ⚠ aiosqlite が未インストール — 統合テストをスキップ")
        print("    pip install aiosqlite を実行してください")

    # 結果集計
    total = passed + failed
    print(f"\n━━━ 結果: {passed}/{total} passed ━━━")
    if failed:
        print(f"    {failed} test(s) FAILED")
        sys.exit(1)
    else:
        print("    All tests passed! ✓")


if __name__ == "__main__":
    asyncio.run(main())
