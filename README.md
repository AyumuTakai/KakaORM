# KakaORM

Python 向けの非同期ネイティブ ORM です。`asyncpg` / `psycopg3` / `aiosqlite` をバックエンドとして使用でき、Django ORM ライクなモデル定義と型安全なクエリ構築を提供します。

## 特徴

- **完全非同期** — `async/await` ベースの API。`asyncio` と自然に統合
- **型安全なクエリ** — `User.age >= 20` のような演算子オーバーロードで文字列なしにクエリを構築
- **複数 DB 対応** — PostgreSQL (asyncpg / psycopg3) と SQLite (aiosqlite) をサポート
- **自動マイグレーション** — モデルと DB スキーマの差分を検出して ALTER TABLE を生成
- **Generic デスクリプタ** — `Column[T]` による型アノテーション推論。IDE の補完が正しく動作

## インストール

```bash
# SQLite (開発・テスト向け)
pip install aiosqlite

# PostgreSQL (asyncpg)
pip install asyncpg

# PostgreSQL (psycopg3)
pip install psycopg[binary] psycopg-pool
```

## クイックスタート

```python
import asyncio
import kakaorm
from kakaorm import Model, IntColumn, StrColumn, BoolColumn

class Task(Model):
    title = StrColumn(nullable=False)
    done  = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "task"

async def main():
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await engine.create_table(Task)

    task = await Task.create(title="KakaORM を試す")
    print(task.id, task.title, task.done)  # 1 KakaORM を試す False

    task.done = True
    await task.save()

    tasks = await Task.filter(Task.done == True)
    print(tasks)  # [<Task id=1>]

    await engine.disconnect()

asyncio.run(main())
```

## モデル定義

```python
from kakaorm import Model, IntColumn, StrColumn, FloatColumn, BoolColumn, DateTimeColumn, ForeignKey

class Author(Model):
    name  = StrColumn(nullable=False)
    email = StrColumn(unique=True, nullable=False)
    bio   = StrColumn(nullable=True)

    class Meta:
        table_name = "author"

class Post(Model):
    title     = StrColumn(nullable=False)
    body      = StrColumn(nullable=True)
    published = BoolColumn(nullable=False, default=False)
    views     = IntColumn(nullable=False, default=0)
    author_id = ForeignKey(Author, nullable=True)

    class Meta:
        table_name = "post"
```

`id` カラムは主キーとして自動追加されます。

## カラム型

| クラス            | Python 型  | SQL 型                     |
| ----------------- | ---------- | -------------------------- |
| `IntColumn`       | `int`      | `INTEGER`                  |
| `StrColumn`       | `str`      | `TEXT` / `VARCHAR(n)`      |
| `FloatColumn`     | `float`    | `DOUBLE PRECISION`         |
| `BoolColumn`      | `bool`     | `BOOLEAN`                  |
| `DateTimeColumn`  | `datetime` | `TIMESTAMP WITH TIME ZONE` |
| `ForeignKey`      | `int`      | `INTEGER REFERENCES ...`   |

### 共通オプション

```python
StrColumn(
    nullable=True,       # NULL 許可 (デフォルト: True)
    default=None,        # デフォルト値
    unique=False,        # UNIQUE 制約
    primary_key=False,   # 主キー
)
StrColumn(max_length=255)        # → VARCHAR(255)
IntColumn(auto_increment=True)   # → SERIAL PRIMARY KEY (PG) / AUTOINCREMENT (SQLite)
DateTimeColumn(auto_now_add=True)  # INSERT 時に現在時刻を自動設定
DateTimeColumn(auto_now=True)      # UPDATE 時に現在時刻を自動更新
ForeignKey(Author, on_delete="CASCADE")
```

## CRUD

### 作成

```python
author = await Author.create(name="Alice", email="alice@example.com")
print(author.id)  # DB 生成の ID が設定される
```

### 取得

```python
# 全件
authors = await Author.all()

# 1件 (見つからなければ NotFound 例外)
author = await Author.get(Author.email == "alice@example.com")

# 1件 (見つからなければ None)
author = await Author.get_or_none(Author.id == 1)

# 先頭 / 末尾
first = await Author.first()
last  = await Author.last()
```

### 更新

```python
author.name = "Alicia"
await author.save()
```

### 削除

```python
await author.delete()
```

## QuerySet — クエリビルダ

`filter()` などのメソッドは `QuerySet` を返します。`await` するまで SQL は実行されません。

```python
# 絞り込み (AND)
posts = await Post.filter(Post.published == True).filter(Post.views >= 100)

# 複合条件
posts = await Post.filter(
    (Post.published == True) & (Post.views >= 100)
)

# OR / NOT
clause = (Post.views < 10) | (Post.published == False)
posts  = await Post.filter(~clause)

# ソート・ページネーション
posts = await (
    Post.filter(Post.published == True)
        .order_by(Post.views.desc)
        .limit(10)
        .offset(20)
)

# 特定カラムのみ SELECT
rows = await Post.all().select(Post.title, Post.views)

# COUNT
n = await Post.filter(Post.published == True).count()

# EXISTS
exists = await Post.filter(Post.title.like("%Python%")).exists()

# 一括 UPDATE
updated = await Post.filter(Post.published == False).update(published=True)

# 一括 DELETE
deleted = await Post.filter(Post.views == 0).delete()

# 非同期イテレーション
async for post in Post.all().order_by(Post.views.desc):
    print(post.title)
```

### WHERE 演算子一覧

```python
Post.views == 100          # =
Post.views != 100          # !=
Post.views >= 100          # >=
Post.views >  100          # >
Post.views <= 100          # <=
Post.views <  100          # <
Post.score == None         # IS NULL
Post.score != None         # IS NOT NULL
Post.title.like("A%")      # LIKE
Post.title.ilike("a%")     # ILIKE
Post.views.in_([1, 2, 3])  # IN
Post.views.not_in([1, 2])  # NOT IN
Post.score.between(1, 5)   # BETWEEN
```

## マイグレーション

```python
from kakaorm.migration import Migrator

migrator = Migrator(engine)

# 差分プランを確認
plan = await migrator.plan([Author, Post])
print(plan.sql)

# 適用
await plan.apply()

# カラム削除も含めた破壊的なプラン
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

## DB 接続

```python
# SQLite (開発・テスト)
engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
engine = await kakaorm.connect("sqlite+aiosqlite:///./dev.db")

# PostgreSQL (asyncpg)
engine = await kakaorm.connect("postgresql+asyncpg://user:password@localhost/dbname")

# PostgreSQL (psycopg3)
engine = await kakaorm.connect("postgresql+psycopg3://user:password@localhost/dbname")

# コンテキストマネージャとしても使用可能
async with await kakaorm.connect("sqlite+aiosqlite:///:memory:") as engine:
    ...
```

## FastAPI との連携

`examples/fastapi_todo.py` に TODO リスト API のサンプルがあります。

```python
from contextlib import asynccontextmanager
import kakaorm
from kakaorm import Model, StrColumn, BoolColumn
from kakaorm.migration import Migrator
from fastapi import FastAPI

class Todo(Model):
    title     = StrColumn(nullable=False)
    completed = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "todo"

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = await kakaorm.connect("sqlite+aiosqlite:///./todo.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    yield
    await engine.disconnect()

app = FastAPI(lifespan=lifespan)

@app.get("/todos")
async def list_todos():
    return [t.to_dict() for t in await Todo.all()]
```

起動:

```bash
python examples/fastapi_todo.py
# http://localhost:8000/docs で Swagger UI を確認
```

## プロジェクト構成

```
kakaorm/
├── kakaorm/                 # パッケージ本体
│   ├── __init__.py          # Engine (AsyncpgEngine / AioSQLiteEngine / Psycopg3Engine), connect()
│   ├── model.py             # Model 基底クラス, AsyncORMMeta メタクラス
│   ├── query.py             # QuerySet (遅延クエリビルダ)
│   ├── columns/
│   │   ├── base.py          # Column[T] 基底クラス, ColumnMeta, WhereClause
│   │   └── types.py         # IntColumn, StrColumn, FloatColumn, BoolColumn, DateTimeColumn, ForeignKey
│   └── migration/
│       └── __init__.py      # Migrator, MigrationPlan
├── examples/
│   ├── blog_example.py      # ブログシステムの使用例
│   └── fastapi_todo.py      # FastAPI TODO リスト API
├── tests/
│   └── test_asyncorm.py     # 統合テスト (aiosqlite in-memory)
└── ruff.toml                # Ruff 設定
```

## テスト実行

```bash
pip install aiosqlite
python tests/test_asyncorm.py
```

## 動作要件

- Python 3.11 以上
- 接続するデータベースに応じたドライバ (`aiosqlite` / `asyncpg` / `psycopg[binary]`)
