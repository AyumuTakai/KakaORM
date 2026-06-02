# KakaORM

[日本語](https://github.com/AyumuTakai/KakaORM/blob/main/README.ja.md)

[![CI](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml/badge.svg)](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![Python](https://img.shields.io/pypi/pyversions/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AyumuTakai/KakaORM/blob/main/LICENSE)

An async-native ORM for Python. Supports PostgreSQL (`asyncpg` / `psycopg3`), SQLite (`aiosqlite`), and MySQL/MariaDB (`aiomysql`) as backends, providing Django ORM-like model definitions and type-safe query building.

## Features

- **Fully async** — `async/await`-based API that integrates naturally with `asyncio`
- **Type-safe queries** — Build queries without strings using operator overloading: `User.age >= 20`
- **Multi-database** — Supports PostgreSQL (asyncpg / psycopg3), SQLite (aiosqlite), and MySQL/MariaDB (aiomysql)
- **Auto migrations** — Detects diff between models and DB schema and generates `ALTER TABLE`; `Migrator.run(models)` applies pending changes in one call
- **Generic descriptors** — Type annotation inference via `Column[T]` for correct IDE completion
- **Event hooks** — Define `before_insert` / `after_update` etc. directly on your Model
- **Relation definitions** — Declare FK navigation (forward and reverse) with `has_many()` / `has_one()` / `belongs_to()`
- **Pydantic v2 integration** — Implements `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__`; use KakaORM models directly as FastAPI `response_model`
- **Eager loading** — Batch-fetch related models with `prefetch()` to eliminate N+1 queries
- **Migration autogenerate** — Auto-generate diff files with `autogenerate()`; manage with `run_files()` + `downgrade()`
- **CTE (WITH clause)** — Structure complex queries with `with_cte(name, queryset)`
- **Deletion strategies** — `SoftDeleteModel` (logical deletion) and `ArchiveModel` (archive deletion) base classes; switch `delete()` behavior simply by changing inheritance
- **Validation** — Attach validators to columns (`min_length`, `max_length`, `min_value`, `max_value`, `regex`, `one_of`); `save()` auto-validates and raises `ValidationError` before any DB write
- **Upsert** — `get_or_create()` and `update_or_create()` return `(instance, created: bool)`
- **Bulk update** — `bulk_update(instances, fields=[...])` flushes many instances in a single `executemany` call

## Installation

```bash
# SQLite (development / testing)
pip install "kakaorm[aiosqlite]"

# PostgreSQL (asyncpg)
pip install "kakaorm[asyncpg]"

# PostgreSQL (psycopg3)
pip install "kakaorm[psycopg3]"

# MySQL / MariaDB
pip install "kakaorm[aiomysql]"

# All drivers
pip install "kakaorm[all]"
```

## Quickstart

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

    task = await Task.create(title="Try KakaORM")
    print(task.id, task.title, task.done)  # 1 Try KakaORM False

    task.done = True
    await task.save()

    tasks = await Task.where(Task.done == True)
    print(tasks)  # [<Task id=1>]

    await engine.disconnect()

asyncio.run(main())
```

## Model Definition

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

An `id` column is added automatically as the primary key.

### Custom Primary Keys

Set `primary_key=True` on any column to make it the primary key. No auto-increment is applied.

```python
class Country(Model):
    code = StrColumn(primary_key=True, nullable=False)  # e.g. "JP" / "US"
    name = StrColumn(nullable=False)

    class Meta:
        table_name = "country"

# Explicit primary key on INSERT
jp = await Country.create(code="JP", name="Japan")
jp.name = "Japan (updated)"
await jp.save()  # UPDATE WHERE code = 'JP'
```

### Composite Indexes

Declare indexes in `Meta.indexes` as a list of tuples. `CREATE INDEX` is issued automatically when `create_table()` runs.

```python
class Product(Model):
    name     = StrColumn(nullable=False)
    category = StrColumn(nullable=False)
    price    = IntColumn(nullable=False)

    class Meta:
        table_name = "product"
        indexes = [
            ("category", "price"),  # composite index
            ("name",),              # single-column index
        ]
```

## Column Types

| Class             | Python type      | SQL type                   |
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

For column options (`nullable`, `default`, `unique`, `primary_key`, `index`, `check`, `auto_increment`, `auto_now`, `on_delete`, etc.) see the full reference below.

> **Not sure which type to use?** See the [Column Type Selection Guide](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.md#choosing-the-right-column-type) — covers numbers (`FloatColumn` vs `DecimalColumn`), strings, dates, and nullable defaults.

→ Full API reference: [docs/REFERENCE.md](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.md)

## CRUD

### Create

```python
author = await Author.create(name="Alice", email="alice@example.com")
print(author.id)  # DB-generated ID is set
```

### Read

```python
# All records
authors = await Author.all()

# Single record (raises NotFound if not found)
author = await Author.get(Author.email == "alice@example.com")

# Single record by primary key (returns None if not found)
author = await Author.find(1)

# Single record by condition (returns None if not found)
author = await Author.get_or_none(Author.id == 1)

# First / last
first = await Author.first()
last  = await Author.last()

# As a dict
author = await Author.get(Author.id == 1)
data = author.to_dict()         # {"id": 1, "name": "Alice", "email": "..."}
```

### Aggregation

```python
from kakaorm import Count, Sum, Avg, Max, Min

# Single-value shortcuts
n     = await Post.all().count()
n     = await Post.where(Post.published == True).count()
total = await Post.all().sum(Post.views)
avg   = await Post.all().avg(Post.score)
hi    = await Post.all().max(Post.views)
lo    = await Post.all().min(Post.score)
found = await Post.where(Post.published == False).exists()  # bool

# Multiple aggregates in one query
stats = await Post.where(Post.published == True).aggregate(
    total_views   = Sum(Post.views),
    avg_score     = Avg(Post.score),
    published_cnt = Count(Post.id),
)
# {"total_views": 12500, "avg_score": 3.8, "published_cnt": 42}

# Group by author, filter with HAVING
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"), Sum(Post.views).label("views"))
        .group_by(Post.author_id)
        .having(Count(Post.id) >= 2)
        .order_by(Sum(Post.views).desc)
)
```

→ Window functions, CTEs, and more: [docs/REFERENCE.md — Aggregate Functions](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.md#aggregate-functions)

### Update

```python
author.name = "Alicia"
await author.save()
```

### Delete

```python
await author.delete()
```

### Validation

```python
from kakaorm.validators import min_length, max_length, min_value, regex

class User(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(50)])
    age   = IntColumn(nullable=True,  validators=[min_value(0)])
    email = StrColumn(nullable=False, validators=[
        regex(r"^[^@]+@[^@]+\.[^@]+$", message="Enter a valid email address.")
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
# get_or_create — find or create; returns (instance, created: bool)
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "Alice"},
)

# update_or_create — find and update, or create
post, created = await Post.update_or_create(
    slug="hello-world",
    defaults={"title": "Hello World", "published": True},
)
```

### Bulk Operations

```python
# Bulk INSERT (batched into minimal SQL statements)
posts = [Post(title=f"Post {i}", views=0) for i in range(1000)]
await Post.bulk_create(posts)

# Bulk UPDATE — flush many instances at once (uses executemany)
for post in posts:
    post.views = 0
await Post.bulk_update(posts, fields=["views"])

# QuerySet-level bulk UPDATE / DELETE
await Post.where(Post.published == False).update(published=True)
await Post.where(Post.views == 0).delete()

# TRUNCATE (also resets sequences)
await Post.truncate()
```

## Database Connections

```bash
# SQLite (development / testing)
pip install fastapi uvicorn kakaorm aiosqlite

# PostgreSQL (asyncpg)
pip install fastapi uvicorn kakaorm asyncpg

# PostgreSQL (psycopg3)
pip install fastapi uvicorn kakaorm "psycopg[binary]" psycopg-pool

# MySQL / MariaDB
pip install fastapi uvicorn kakaorm aiomysql
```

| DB | URL format |
|---|---|
| SQLite (file) | `sqlite+aiosqlite:///./app.db` |
| SQLite (in-memory) | `sqlite+aiosqlite:///:memory:` |
| PostgreSQL (asyncpg) | `postgresql+asyncpg://user:password@localhost/dbname` |
| PostgreSQL (psycopg3) | `postgresql+psycopg3://user:password@localhost/dbname` |
| MySQL / MariaDB | `mysql+aiomysql://user:password@localhost:3306/dbname` |

```python
# Always use await — omitting it raises a RuntimeWarning with a fix hint
engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
engine = await kakaorm.connect("sqlite+aiosqlite:///./dev.db")

# PostgreSQL (asyncpg)
engine = await kakaorm.connect("postgresql+asyncpg://user:password@localhost/dbname")

# PostgreSQL (psycopg3)
engine = await kakaorm.connect("postgresql+psycopg3://user:password@localhost/dbname")

# MySQL / MariaDB (aiomysql)
engine = await kakaorm.connect("mysql+aiomysql://user:password@localhost:3306/dbname")

# Also usable as a context manager
async with await kakaorm.connect("sqlite+aiosqlite:///:memory:") as engine:
    ...
```

## Migrations

```python
from kakaorm.migration import Migrator

# Apply any pending schema changes in one call (no-op if schema is up to date)
await Migrator(engine).run([Author, Post])

# Or use the two-step API for more control
migrator = Migrator(engine)
plan = await migrator.plan([Author, Post])
if not plan.is_empty():
    await plan.apply()
```

## Framework Integration

- **FastAPI** — See [FastAPI Integration Guide](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FASTAPI.md) / [日本語](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FASTAPI.ja.md)
- **Flask** — See [Flask Integration Guide](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.md) / [日本語](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FLASK.ja.md)

## Project Structure

```
kakaorm/
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI (lint + test matrix + MySQL + build)
├── docs/
│   ├── FASTAPI.md           # FastAPI integration guide (English)
│   ├── FASTAPI.ja.md        # FastAPI integration guide (Japanese)
│   ├── FLASK.md             # Flask integration guide (English)
│   ├── FLASK.ja.md          # Flask integration guide (Japanese)
│   ├── REFERENCE.md         # Full API reference (English)
│   └── REFERENCE.ja.md      # Full API reference (Japanese)
├── kakaorm/                 # Package source
│   ├── __init__.py          # Public API re-exports
│   ├── py.typed             # PEP 561 type marker
│   ├── engine.py            # Engine base class + AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine, connect()
│   ├── model.py             # Model base class, AsyncORMMeta metaclass
│   ├── query.py             # QuerySet (lazy query builder)
│   ├── validators.py        # ValidationError + built-in validators (min_length, max_length, …)
│   ├── soft_delete.py       # SoftDeleteModel / SoftDeleteQuerySet (logical deletion)
│   ├── archive.py           # ArchiveModel / ArchiveQuerySet (archive deletion)
│   ├── relationship.py      # has_many / has_one / belongs_to descriptors
│   ├── columns/
│   │   ├── base.py          # Column[T] base class, ColumnMeta, WhereClause
│   │   └── types.py         # IntColumn, StrColumn, FloatColumn, BoolColumn,
│   │                        # DateTimeColumn, DateColumn, TimeColumn, DecimalColumn, ForeignKey
│   └── migration/
│       └── __init__.py      # Migrator, VersionedMigrator, MigrationPlan
├── examples/
│   ├── blog_example.py      # Blog system usage example
│   ├── fastapi_todo.py      # FastAPI TODO list API
│   └── flask_todo.py        # Flask TODO list API
│
│   Larger sample apps live in a separate repository:
│   → https://github.com/AyumuTakai/kakaorm-samples
├── tests/
│   ├── conftest.py
│   ├── test_crud.py
│   ├── test_joins.py
│   ├── test_aggregates.py
│   ├── test_transaction.py
│   ├── test_bulk_create.py
│   ├── test_bulk_update.py  # bulk_update()
│   ├── test_validation.py   # Column validators + ValidationError
│   ├── test_upsert.py       # get_or_create / update_or_create
│   ├── test_raw_sql.py
│   ├── test_migration.py
│   ├── test_indexes.py      # Composite indexes
│   ├── test_custom_pk.py    # Custom primary keys
│   ├── test_hooks.py        # Event hooks
│   ├── test_relationship.py # Relation definitions
│   └── test_security.py     # Security regression tests
├── CHANGELOG.md             # Version history
├── LICENSE                  # MIT License
├── pyproject.toml           # Package metadata and build configuration
└── ruff.toml                # Ruff configuration
```

## Running Tests

```bash
pip install -e ".[aiosqlite,dev]"
pytest

# MySQL tests (requires a running MySQL server)
# MySQL 8.0 uses caching_sha2_password auth, which requires the cryptography package
pip install -e ".[aiomysql,dev]" cryptography
export KAKAORM_MYSQL_URL="mysql+aiomysql://root:password@localhost:3306/test_db"
pytest tests/test_mysql.py
```

## Requirements

- Python 3.11+
- The appropriate driver for your database (`aiosqlite` / `asyncpg` / `psycopg[binary]` / `aiomysql`)
- For Pydantic v2 integration: `pip install pydantic` (optional — the ORM core works without it)

## For AI Agents

A condensed cheat-sheet for LLMs and AI coding assistants is available at [`llms.txt`](https://github.com/AyumuTakai/KakaORM/blob/main/llms.txt).
It covers the full API, anti-patterns to avoid, and copy-ready code snippets — optimised for use in an LLM context window.

## License

[MIT License](https://github.com/AyumuTakai/KakaORM/blob/main/LICENSE)
