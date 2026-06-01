# KakaORM

[English](https://github.com/AyumuTakai/KakaORM/blob/main/README.md)

[![CI](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml/badge.svg)](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![Python](https://img.shields.io/pypi/pyversions/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AyumuTakai/KakaORM/blob/main/LICENSE)

Python 向けの非同期ネイティブ ORM です。PostgreSQL (`asyncpg` / `psycopg3`)、SQLite (`aiosqlite`)、MySQL/MariaDB (`aiomysql`) をバックエンドとして使用でき、Django ORM ライクなモデル定義と型安全なクエリ構築を提供します。

## 特徴

- **完全非同期** — `async/await` ベースの API。`asyncio` と自然に統合
- **型安全なクエリ** — `User.age >= 20` のような演算子オーバーロードで文字列なしにクエリを構築
- **複数 DB 対応** — PostgreSQL (asyncpg / psycopg3)・SQLite (aiosqlite)・MySQL/MariaDB (aiomysql) をサポート
- **自動マイグレーション** — モデルと DB スキーマの差分を検出して ALTER TABLE を生成。`Migrator.run(models)` で差分の確認と適用を1行で実行できる
- **Generic デスクリプタ** — `Column[T]` による型アノテーション推論。IDE の補完が正しく動作
- **イベントフック** — `before_insert` / `after_update` などを Model に定義するだけで動作
- **リレーション定義** — `has_many()` / `has_one()` / `belongs_to()` で FK ナビゲーション（前向き・逆参照）を宣言的に記述
- **Pydantic v2 統合** — `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__` を実装。FastAPI の `response_model` に KakaORM モデルを直接指定できる
- **Eager loading** — `prefetch()` で関連モデルを一括取得。N+1 問題を解消
- **マイグレーション autogenerate** — `autogenerate()` で差分ファイルを自動生成。`run_files()` + `downgrade()` でファイルベースの管理が可能
- **CTE（WITH 句）** — `with_cte(name, queryset)` で複雑なクエリを構造化
- **削除戦略** — `SoftDeleteModel`（論理削除）・`ArchiveModel`（アーカイブ削除）の基底クラスを提供。継承するだけで `delete()` の挙動を切り替えられる
- **バリデーション** — カラムにバリデータを付与（`min_length`・`max_length`・`min_value`・`max_value`・`regex`・`one_of`）。`save()` が DB 書き込み前に自動検証し、失敗時は `ValidationError` を送出
- **Upsert** — `get_or_create()` / `update_or_create()` が `(instance, created: bool)` を返す
- **一括 UPDATE** — `bulk_update(instances, fields=[...])` で多数のインスタンスを `executemany` 1 回でフラッシュ

## インストール

```bash
# SQLite (開発・テスト向け)
pip install "kakaorm[aiosqlite]"

# PostgreSQL (asyncpg)
pip install "kakaorm[asyncpg]"

# PostgreSQL (psycopg3)
pip install "kakaorm[psycopg3]"

# MySQL / MariaDB
pip install "kakaorm[aiomysql]"

# 全ドライバ
pip install "kakaorm[all]"
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

カラムオプション（`nullable`、`default`、`unique`、`primary_key`、`index`、`check`、`auto_increment`、`auto_now`、`on_delete` など）の詳細はリファレンスを参照してください。

→ 完全な API リファレンス: [docs/REFERENCE.ja.md](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.ja.md)

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

# PK で1件取得 (見つからなければ None)
author = await Author.find(1)

# 条件で1件取得 (見つからなければ None)
author = await Author.get_or_none(Author.id == 1)

# 先頭 / 末尾
first = await Author.first()
last  = await Author.last()

# dict 形式で取得
author = await Author.get(Author.id == 1)
data = author.to_dict()         # {"id": 1, "name": "Alice", "email": "..."}
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

### バリデーション

```python
from kakaorm.validators import min_length, max_length, min_value, regex

class User(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(50)])
    age   = IntColumn(nullable=True,  validators=[min_value(0)])
    email = StrColumn(nullable=False, validators=[
        regex(r"^[^@]+@[^@]+\.[^@]+$", message="有効なメールアドレスを入力してください。")
    ])

    class Meta:
        table_name = "user"

try:
    await User.create(name="A", age=-1, email="bad")
except ValidationError as e:
    print(e.errors)
    # {"name": ["..."], "age": ["..."], "email": ["..."]}
```

### Upsert

```python
# get_or_create — 検索または作成。(instance, created: bool) を返す
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "Alice"},
)

# update_or_create — 検索して更新、またはなければ作成
post, created = await Post.update_or_create(
    slug="hello-world",
    defaults={"title": "Hello World", "published": True},
)
```

### 一括操作

```python
# 一括 INSERT (N 件を最小回数の SQL でまとめる)
posts = [Post(title=f"記事{i}", views=0) for i in range(1000)]
await Post.bulk_create(posts)

# 一括 UPDATE — 多数のインスタンスを executemany で一度にフラッシュ
for post in posts:
    post.views = 0
await Post.bulk_update(posts, fields=["views"])

# QuerySet レベルの一括 UPDATE / DELETE
await Post.where(Post.published == False).update(published=True)
await Post.where(Post.views == 0).delete()

# TRUNCATE (シーケンスもリセット)
await Post.truncate()
```

## DB 接続

```python
# 必ず await を付けること。省略すると修正方法を示す RuntimeWarning が発行される
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

## マイグレーション

```python
from kakaorm.migration import Migrator

# 差分の確認と適用を1行で実行（差分がなければ何もしない）
await Migrator(engine).run([Author, Post])

# 詳細を制御したい場合は2ステップで記述することもできる
migrator = Migrator(engine)
plan = await migrator.plan([Author, Post])
if not plan.is_empty():
    await plan.apply()
```

## フレームワーク連携

- **FastAPI** — [FastAPI 統合ガイド](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FASTAPI.ja.md) / [English](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FASTAPI.md)
- **Flask** — [Flask 統合ガイド](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.ja.md) / [English](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.md)

## プロジェクト構成

```
kakaorm/
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI (lint + test matrix + MySQL + build)
├── docs/
│   ├── FASTAPI.md           # FastAPI 統合ガイド（英語）
│   ├── FASTAPI.ja.md        # FastAPI 統合ガイド（日本語）
│   ├── FLASK.md             # Flask 統合ガイド（英語）
│   ├── FLASK.ja.md          # Flask 統合ガイド（日本語）
│   ├── REFERENCE.md         # API リファレンス（英語）
│   └── REFERENCE.ja.md      # API リファレンス（日本語）
├── kakaorm/                 # パッケージ本体
│   ├── __init__.py          # 公開 API の再エクスポート
│   ├── py.typed             # PEP 561 型情報マーカー
│   ├── engine.py            # Engine 基底クラス + AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine, connect()
│   ├── model.py             # Model 基底クラス, AsyncORMMeta メタクラス
│   ├── query.py             # QuerySet (遅延クエリビルダ)
│   ├── validators.py        # ValidationError + ビルトインバリデータ (min_length, max_length, …)
│   ├── soft_delete.py       # SoftDeleteModel / SoftDeleteQuerySet (論理削除)
│   ├── archive.py           # ArchiveModel / ArchiveQuerySet (アーカイブ削除)
│   ├── relationship.py      # has_many / has_one / belongs_to デスクリプタ
│   ├── columns/
│   │   ├── base.py          # Column[T] 基底クラス, ColumnMeta, WhereClause
│   │   └── types.py         # IntColumn, StrColumn, FloatColumn, BoolColumn,
│   │                        # DateTimeColumn, DateColumn, TimeColumn, DecimalColumn, ForeignKey
│   └── migration/
│       └── __init__.py      # Migrator, VersionedMigrator, MigrationPlan
├── examples/
│   ├── blog_example.py      # ブログシステムの使用例
│   ├── fastapi_todo.py      # FastAPI TODO リスト API
│   └── flask_todo.py        # Flask TODO リスト API
│
│   大規模なサンプルアプリは別リポジトリで管理しています:
│   → https://github.com/AyumuTakai/kakaorm-samples
├── tests/
│   ├── conftest.py
│   ├── test_crud.py
│   ├── test_joins.py
│   ├── test_aggregates.py
│   ├── test_transaction.py
│   ├── test_bulk_create.py
│   ├── test_bulk_update.py  # bulk_update()
│   ├── test_validation.py   # カラムバリデータ + ValidationError
│   ├── test_upsert.py       # get_or_create / update_or_create
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

[MIT License](https://github.com/AyumuTakai/KakaORM/blob/main/LICENSE)
