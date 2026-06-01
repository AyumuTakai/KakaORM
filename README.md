# KakaORM

[English](README.en.md)

[![CI](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml/badge.svg)](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![Python](https://img.shields.io/pypi/pyversions/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Python 向けの非同期ネイティブ ORM です。PostgreSQL (`asyncpg` / `psycopg3`)、SQLite (`aiosqlite`)、MySQL/MariaDB (`aiomysql`) をバックエンドとして使用でき、Django ORM ライクなモデル定義と型安全なクエリ構築を提供します。

## 特徴

- **完全非同期** — `async/await` ベースの API。`asyncio` と自然に統合
- **型安全なクエリ** — `User.age >= 20` のような演算子オーバーロードで文字列なしにクエリを構築
- **複数 DB 対応** — PostgreSQL (asyncpg / psycopg3)・SQLite (aiosqlite)・MySQL/MariaDB (aiomysql) をサポート
- **自動マイグレーション** — モデルと DB スキーマの差分を検出して ALTER TABLE を生成
- **Generic デスクリプタ** — `Column[T]` による型アノテーション推論。IDE の補完が正しく動作
- **イベントフック** — `before_insert` / `after_update` などを Model に定義するだけで動作
- **リレーション定義** — `has_many()` / `has_one()` / `belongs_to()` で FK ナビゲーション（前向き・逆参照）を宣言的に記述
- **Pydantic v2 統合** — `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__` を実装。FastAPI の `response_model` に KakaORM モデルを直接指定できる
- **Eager loading** — `prefetch()` で関連モデルを一括取得。N+1 問題を解消
- **マイグレーション autogenerate** — `autogenerate()` で差分ファイルを自動生成。`run_files()` + `downgrade()` でファイルベースの管理が可能
- **CTE（WITH 句）** — `with_cte(name, queryset)` で複雑なクエリを構造化

## インストール

```bash
# SQLite (開発・テスト向け)
pip install kakaorm[aiosqlite]

# PostgreSQL (asyncpg)
pip install kakaorm[asyncpg]

# PostgreSQL (psycopg3)
pip install kakaorm[psycopg3]

# MySQL / MariaDB
pip install kakaorm[aiomysql]

# 全ドライバ
pip install kakaorm[all]
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

    tasks = await Task.where(Task.done == True)
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

### ユーザー定義主キー

`primary_key=True` を任意のカラムに付けると、そのカラムが主キーになります。自動採番は行われません。

```python
class Country(Model):
    code = StrColumn(primary_key=True, nullable=False)  # "JP" / "US" など
    name = StrColumn(nullable=False)

    class Meta:
        table_name = "country"

# 主キーを明示して INSERT
jp = await Country.create(code="JP", name="Japan")
jp.name = "Japan (updated)"
await jp.save()  # WHERE code = 'JP' で UPDATE
```

### 複合インデックス

`Meta.indexes` にタプルのリストでインデックスを宣言します。`create_table()` 実行時に `CREATE INDEX` が自動発行されます。

```python
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
```

## カラム型

| クラス            | Python 型        | SQL 型                     |
| ----------------- | ---------------- | -------------------------- |
| `IntColumn`       | `int`            | `INTEGER`                  |
| `StrColumn`       | `str`            | `TEXT` / `VARCHAR(n)`      |
| `FloatColumn`     | `float`          | `DOUBLE PRECISION`         |
| `BoolColumn`      | `bool`           | `BOOLEAN`                  |
| `DateTimeColumn`  | `datetime`       | `TIMESTAMP WITH TIME ZONE` |
| `DateColumn`      | `date`           | `DATE`                     |
| `TimeColumn`      | `time`           | `TIME`                     |
| `DecimalColumn`   | `Decimal`        | `NUMERIC(p, s)`            |
| `ForeignKey`      | `int`            | `INTEGER REFERENCES ...`   |

### 共通オプション

```python
StrColumn(
    nullable=True,       # NULL 許可 (デフォルト: True)
    default=None,        # デフォルト値
    unique=False,        # UNIQUE 制約
    primary_key=False,   # 主キー
    index=False,         # 単一カラムインデックス
    check="value > 0",   # CHECK 制約
)
StrColumn(max_length=255)          # → VARCHAR(255)
IntColumn(auto_increment=True)     # → SERIAL PRIMARY KEY (PG) / AUTOINCREMENT (SQLite)
DateTimeColumn(auto_now_add=True)  # INSERT 時に現在時刻を自動設定
DateTimeColumn(auto_now=True)      # UPDATE 時に現在時刻を自動更新
ForeignKey(Author, on_delete="CASCADE")
DecimalColumn(max_digits=10, decimal_places=2)  # NUMERIC(10, 2)
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

### 一括操作

```python
# 一括 INSERT (N 件を最小回数の SQL でまとめる)
posts = [Post(title=f"記事{i}", views=0) for i in range(1000)]
await Post.bulk_create(posts)

# 一括 UPDATE
await Post.where(Post.published == False).update(published=True)

# 一括 DELETE
await Post.where(Post.views == 0).delete()

# TRUNCATE (シーケンスもリセット)
await Post.truncate()
```

## イベントフック

`save()` / `delete()` の前後に任意の処理を差し込めます。Model を継承したクラスでメソッドをオーバーライドするだけです。

```python
import datetime
from kakaorm import Model, StrColumn, IntColumn, DateTimeColumn

class Article(Model):
    title      = StrColumn(nullable=False)
    version    = IntColumn(nullable=False, default=0)
    updated_at = DateTimeColumn(nullable=True)

    async def before_insert(self) -> None:
        # INSERT 直前: タイムスタンプを自動設定
        self.updated_at = datetime.datetime.utcnow()

    async def before_update(self) -> None:
        # UPDATE 直前: バージョンをインクリメント
        self.version = (self.version or 0) + 1
        self.updated_at = datetime.datetime.utcnow()

    async def after_delete(self) -> None:
        # DELETE 完了後: ログ出力など
        print(f"Article deleted: {self.title}")
```

利用可能なフック:

| フック            | タイミング           |
| ----------------- | -------------------- |
| `before_insert`   | `save()` (INSERT 前) |
| `after_insert`    | `save()` (INSERT 後) |
| `before_update`   | `save()` (UPDATE 前) |
| `after_update`    | `save()` (UPDATE 後) |
| `before_delete`   | `delete()` 前        |
| `after_delete`    | `delete()` 後        |

> `QuerySet.update()` / `QuerySet.delete()` はフックを経由しません。

## リレーション定義

`has_many()` / `has_one()` / `belongs_to()` で FK を通じた関連オブジェクトの取得を宣言的に記述できます。`await` するまでクエリは発行されません。

```python
from kakaorm import Model, StrColumn, ForeignKey, has_many, belongs_to

class Author(Model):
    name  = StrColumn(nullable=False)
    # 1対多の逆参照
    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"

class Post(Model):
    title     = StrColumn(nullable=False)
    author_id = ForeignKey(Author, nullable=True)
    # 多対1の前向き FK
    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"

# 使用例
post   = await Post.get(Post.id == 1)
author = await post.author          # → Author | None

author = await Author.get(Author.id == 1)
posts  = await author.posts         # → list[Post]
```

### リレーションの種類

| メソッド | 用途 | 戻り値 |
|----------|------|--------|
| `has_many()` | 1対多の逆参照 | `list[Model]` |
| `has_one()` | 1対1の逆参照 | `Model \| None` |
| `belongs_to()` | 多対1の前向き FK | `Model \| None` |

`related_model` には文字列でクラス名を渡すことも可能です（循環 import 回避）。

```python
posts = has_many("Post", foreign_key="author_id")
```

### Eager loading（N+1 解消）

`prefetch()` を使うと、関連モデルを 1 クエリで一括取得してキャッシュします。

```python
# N+1 あり（デフォルト）
posts = await Post.all()
for post in posts:
    author = await post.author  # 投稿ごとに SELECT が走る

# N+1 解消: prefetch で一括取得
posts = await Post.all().prefetch("author")
for post in posts:
    author = await post.author  # キャッシュから返す（追加クエリなし）

# 複数のリレーションを同時にプリフェッチ
authors = await Author.all().prefetch("posts", "profile")
```

## QuerySet — クエリビルダ

`where()` などのメソッドは `QuerySet` を返します。`await` するまで SQL は実行されません。

```python
# 絞り込み (AND)
posts = await Post.where(Post.published == True).where(Post.views >= 100)

# 複合条件
posts = await Post.where(
    (Post.published == True) & (Post.views >= 100)
)

# OR / NOT
clause = (Post.views < 10) | (Post.published == False)
posts  = await Post.where(~clause)

# ソート・ページネーション
posts = await (
    Post.where(Post.published == True)
        .order_by(Post.views.desc)
        .limit(10)
        .offset(20)
)

# 特定カラムのみ SELECT
rows = await Post.all().select(Post.title, Post.views)

# COUNT / EXISTS
n      = await Post.where(Post.published == True).count()
exists = await Post.where(Post.title.like("%Python%")).exists()

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

### JOIN / GROUP BY / 集計

```python
from kakaorm import Count, Sum, Avg

# INNER JOIN
rows = await (
    Post.where(Post.published == True)
        .join(Author, on=Post.author_id == Author.id)
        .select(Post.title, Author.name)
)

# LEFT JOIN
rows = await (
    Author.all()
        .left_join(Post, on=Post.author_id == Author.id)
        .select(Author.name, Count(Post.id).label("post_count"))
        .group_by(Author.id, Author.name)
)

# 集計
total = await Post.all().sum(Post.views)
stats = await Post.all().aggregate(
    total=Sum(Post.views),
    avg=Avg(Post.views),
)

# GROUP BY / HAVING
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .having(Count(Post.id) >= 2)
)
```

### CTE（WITH 句）

```python
# 高給社員がいる部署を CTE で定義して JOIN する
high_earners = (
    Employee.where(Employee.salary >= 1000)
            .select(Employee.dept_id)
)
rows = await (
    Department.all()
              .with_cte("rich_depts", high_earners)
              .join(Employee, on=Employee.dept_id == Department.id)
              .select(Department.name, Employee.name)
              .where(Employee.salary >= 1000)
)
```

### UPDATE 式 (列参照)

```python
# 固定値
await Post.all().update(published=True)

# 列参照を含む式
await Post.all().update(views=Post.views + 1)
await Product.all().update(price=Product.price * 0.97)
```

### INSERT ... SELECT

```python
await (
    Employee.where(Employee.hire_year <= 1993)
        .insert_into(Archive, emp_id=Employee.id, year=Employee.hire_year)
)
```

## Raw SQL

ORM で表現が難しいクエリには Raw SQL を使用できます。

```python
# SELECT → list[dict]
rows = await engine.fetch(
    "SELECT p.title, a.name FROM post p JOIN author a ON p.author_id = a.id WHERE p.views > %s",
    [100],
)

# INSERT / UPDATE / DELETE → 影響行数
affected = await engine.execute(
    "UPDATE post SET views = 0 WHERE author_id = %s",
    [author_id],
)

# スカラー値
count = await engine.fetchval("SELECT COUNT(*) FROM post WHERE published = %s", [True])
```

## トランザクション

```python
async with engine.transaction():
    order = await Order.create(item="Widget", qty=1)
    await Stock.where(Stock.item == "Widget").update(qty=Stock.qty - 1)
    # 例外発生時は自動ロールバック
```

## マイグレーション

### 手動マイグレーション

```python
from kakaorm.migration import Migrator

migrator = Migrator(engine)

# 差分プランを確認
plan = await migrator.plan([Author, Post])
print(plan.sql)       # UP SQL
print(plan.down_sql)  # DOWN SQL（逆順）

# 適用 / ロールバック
await plan.apply()
await plan.apply_down()  # ロールバック

# カラム削除も含めた破壊的なプラン
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

### ファイルベースのマイグレーション（推奨）

```python
from kakaorm.migration import VersionedMigrator

migrator = VersionedMigrator(engine)

# 1. モデルと DB の差分から migration ファイルを自動生成
path = await migrator.autogenerate([User, Post], "./migrations", name="add_bio")
# → migrations/0001_add_bio.py が生成される

# 2. 未適用のマイグレーションを一括適用
n = await migrator.run_files("./migrations")

# 3. 直近 1 件をロールバック
await migrator.downgrade(steps=1)

# 適用履歴を確認
for record in await migrator.history():
    print(record.name, record.applied_at)
```

生成されるマイグレーションファイルの形式:

```python
# migrations/0001_add_bio.py
# Auto-generated by KakaORM

up = [
    "ALTER TABLE user ADD COLUMN bio TEXT DEFAULT NULL",
]

down = [
    "ALTER TABLE user DROP COLUMN bio",
]
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

# MySQL / MariaDB (aiomysql)
engine = await kakaorm.connect("mysql+aiomysql://user:password@localhost:3306/dbname")

# コンテキストマネージャとしても使用可能
async with await kakaorm.connect("sqlite+aiosqlite:///:memory:") as engine:
    ...
```

## FastAPI との連携

Pydantic v2 プロトコルを実装しているため、KakaORM モデルを `response_model` に直接指定できます。
レスポンス用の `BaseModel` サブクラスを別途定義する必要はありません。

```python
from contextlib import asynccontextmanager
import kakaorm
from kakaorm import Model, StrColumn, BoolColumn
from kakaorm.migration import Migrator
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel  # リクエストボディ用のみ

class Todo(Model):
    title       = StrColumn(nullable=False)
    description = StrColumn(nullable=True)
    completed   = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "todo"

# リクエストボディ用スキーマ（入力バリデーション）
class TodoCreate(BaseModel):
    title: str
    description: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = await kakaorm.connect("sqlite+aiosqlite:///./todo.db")
    plan = await Migrator(engine).plan([Todo])
    if not plan.is_empty():
        await plan.apply()
    yield
    await engine.disconnect()

app = FastAPI(lifespan=lifespan)

# response_model に KakaORM モデルを直接指定
@app.get("/todos", response_model=list[Todo])
async def list_todos():
    return await Todo.all()

@app.post("/todos", response_model=Todo, status_code=201)
async def create_todo(body: TodoCreate):
    return await Todo.create(**body.model_dump())

@app.get("/todos/{todo_id}", response_model=Todo)
async def get_todo(todo_id: int):
    todo = await Todo.get_or_none(Todo.id == todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo
```

Swagger UI (`/docs`) には `id` / `title` / `description` / `completed` の型情報が自動出力されます。

起動:

```bash
pip install fastapi uvicorn aiosqlite
python examples/fastapi_todo.py
# http://localhost:8000/docs で Swagger UI を確認
```

詳細なガイド、実装パターン、テスト戦略は [FastAPI 統合ガイド](docs/FASTAPI.md) を参照してください。
その他の実装例：
- `examples/fastapi_advanced.py` — 依存性注入、複数モデル、エラー処理
- `examples/fastapi_pagination.py` — ページング & フィルタリング
- `examples/fastapi_testing.py` — pytest + httpx テスト戦略

### Pydantic 互換メソッド

```python
# Pydantic 互換のシリアライズ
user.model_dump()
# → {"id": 1, "name": "Alice", "age": 30, "bio": None}

user.model_dump(exclude_none=True, exclude={"bio"})
# → {"id": 1, "name": "Alice", "age": 30}

# Pydantic 互換の変換
user = User.model_validate({"name": "Alice", "age": 30})   # dict から
user = User.model_validate(other_instance)                  # 別インスタンスから
```

## セキュリティ

kakaorm はクエリの値を常にバインドパラメータとして扱い、SQL インジェクションを防止します。

- **WHERE / LIKE / IN 句の値** — すべてバインドパラメータ経由で送出されます
- **`update()` のカラム名** — `_meta.columns` に存在しないキーは `ValueError` で拒否します
- **`insert_into()` の宛先カラム名** — 同様に `_meta.columns` でホワイトリスト検証します
- **`create()` のフィールド名** — 未知のフィールドは `TypeError` で拒否します

> **アプリ側の注意点**
>
> `order_by()` は生文字列をそのまま SQL に展開します。
> ユーザー入力を ORDER BY に使う場合は、許可済みカラム名のみを受け付けるホワイトリストをアプリ側で実装してください。
>
> ```python
> ALLOWED = {"views", "title", "created_at"}
> col = user_input if user_input in ALLOWED else "id"
> results = await Post.all().order_by(f"{col} DESC")
> ```
>
> また、`create()` / `save()` は既知フィールドへの書き込みを制限しません。
> ユーザー入力から特権フィールド（`is_admin` など）を除外する処理はアプリ層で行ってください。

## プロジェクト構成

```
kakaorm/
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI (lint + test matrix + MySQL + build)
├── kakaorm/                 # パッケージ本体
│   ├── __init__.py          # 公開 API の再エクスポート
│   ├── py.typed             # PEP 561 型情報マーカー
│   ├── engine.py            # Engine 基底クラス + AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine, connect()
│   ├── model.py             # Model 基底クラス, AsyncORMMeta メタクラス
│   ├── query.py             # QuerySet (遅延クエリビルダ)
│   ├── relationship.py      # has_many / has_one / belongs_to デスクリプタ
│   ├── columns/
│   │   ├── base.py          # Column[T] 基底クラス, ColumnMeta, WhereClause
│   │   └── types.py         # IntColumn, StrColumn, FloatColumn, BoolColumn,
│   │                        # DateTimeColumn, DateColumn, TimeColumn, DecimalColumn, ForeignKey
│   └── migration/
│       └── __init__.py      # Migrator, VersionedMigrator, MigrationPlan
├── examples/
│   ├── blog_example.py      # ブログシステムの使用例
│   └── fastapi_todo.py      # FastAPI TODO リスト API
├── tests/
│   ├── conftest.py
│   ├── test_crud.py
│   ├── test_joins.py
│   ├── test_aggregates.py
│   ├── test_transaction.py
│   ├── test_bulk_create.py
│   ├── test_raw_sql.py
│   ├── test_migration.py
│   ├── test_indexes.py      # 複合インデックス
│   ├── test_custom_pk.py    # ユーザー定義主キー
│   ├── test_hooks.py        # イベントフック
│   ├── test_relationship.py # リレーション定義
│   └── test_security.py     # セキュリティ回帰テスト
├── CHANGELOG.md             # バージョン履歴
├── LICENSE                  # MIT License
├── pyproject.toml           # パッケージメタデータ・ビルド設定
└── ruff.toml                # Ruff 設定
```

## テスト実行

```bash
pip install -e ".[aiosqlite,dev]"
pytest

# MySQL テスト (別途 MySQL サーバーが必要)
# MySQL 8.0 は caching_sha2_password 認証を使うため cryptography が必要
pip install -e ".[aiomysql,dev]" cryptography
export KAKAORM_MYSQL_URL="mysql+aiomysql://root:password@localhost:3306/test_db"
pytest tests/test_mysql.py
```

## 動作要件

- Python 3.11 以上
- 接続するデータベースに応じたドライバ (`aiosqlite` / `asyncpg` / `psycopg[binary]` / `aiomysql`)
- Pydantic v2 統合を使う場合: `pip install pydantic`（省略可能 — 未インストールでも ORM 本体は動作する）

## ライセンス

[MIT License](LICENSE)
