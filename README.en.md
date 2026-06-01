# KakaORM

[![CI](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml/badge.svg)](https://github.com/AyumuTakai/KakaORM/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![Python](https://img.shields.io/pypi/pyversions/kakaorm.svg)](https://pypi.org/project/kakaorm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An async-native ORM for Python. Supports PostgreSQL (`asyncpg` / `psycopg3`), SQLite (`aiosqlite`), and MySQL/MariaDB (`aiomysql`) as backends, providing Django ORM-like model definitions and type-safe query building.

## Features

- **Fully async** — `async/await`-based API that integrates naturally with `asyncio`
- **Type-safe queries** — Build queries without strings using operator overloading: `User.age >= 20`
- **Multi-database** — Supports PostgreSQL (asyncpg / psycopg3), SQLite (aiosqlite), and MySQL/MariaDB (aiomysql)
- **Auto migrations** — Detects diff between models and DB schema and generates `ALTER TABLE`
- **Generic descriptors** — Type annotation inference via `Column[T]` for correct IDE completion
- **Event hooks** — Define `before_insert` / `after_update` etc. directly on your Model
- **Relation definitions** — Declare FK navigation (forward and reverse) with `has_many()` / `has_one()` / `belongs_to()`
- **Pydantic v2 integration** — Implements `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__`; use KakaORM models directly as FastAPI `response_model`
- **Deletion strategies** — `SoftDeleteModel` (logical deletion) and `ArchiveModel` (archive deletion) base classes; switch `delete()` behavior simply by changing inheritance

## Installation

```bash
# SQLite (development / testing)
pip install kakaorm[aiosqlite]

# PostgreSQL (asyncpg)
pip install kakaorm[asyncpg]

# PostgreSQL (psycopg3)
pip install kakaorm[psycopg3]

# MySQL / MariaDB
pip install kakaorm[aiomysql]

# All drivers
pip install kakaorm[all]
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

### Common Options

```python
StrColumn(
    nullable=True,       # allow NULL (default: True)
    default=None,        # default value
    unique=False,        # UNIQUE constraint
    primary_key=False,   # primary key
    index=False,         # single-column index
    check="value > 0",   # CHECK constraint
)
StrColumn(max_length=255)          # → VARCHAR(255)
IntColumn(auto_increment=True)     # → SERIAL PRIMARY KEY (PG) / AUTOINCREMENT (SQLite)
DateTimeColumn(auto_now_add=True)  # set current time automatically on INSERT
DateTimeColumn(auto_now=True)      # update current time automatically on UPDATE
ForeignKey(Author, on_delete="CASCADE")
DecimalColumn(max_digits=10, decimal_places=2)  # NUMERIC(10, 2)
```

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

# Single record (returns None if not found)
author = await Author.get_or_none(Author.id == 1)

# First / last
first = await Author.first()
last  = await Author.last()
```

### Update

```python
author.name = "Alicia"
await author.save()
```

### Delete

```python
await author.delete()
```

### Bulk Operations

```python
# Bulk INSERT (batched into minimal SQL statements)
posts = [Post(title=f"Post {i}", views=0) for i in range(1000)]
await Post.bulk_create(posts)

# Bulk UPDATE
await Post.where(Post.published == False).update(published=True)

# Bulk DELETE
await Post.where(Post.views == 0).delete()

# TRUNCATE (also resets sequences)
await Post.truncate()
```

## Event Hooks

Insert custom logic before/after `save()` / `delete()` by overriding methods on your Model subclass.

```python
import datetime
from kakaorm import Model, StrColumn, IntColumn, DateTimeColumn

class Article(Model):
    title      = StrColumn(nullable=False)
    version    = IntColumn(nullable=False, default=0)
    updated_at = DateTimeColumn(nullable=True)

    async def before_insert(self) -> None:
        # Called just before INSERT: set timestamp automatically
        self.updated_at = datetime.datetime.utcnow()

    async def before_update(self) -> None:
        # Called just before UPDATE: increment version
        self.version = (self.version or 0) + 1
        self.updated_at = datetime.datetime.utcnow()

    async def after_delete(self) -> None:
        # Called after DELETE completes: e.g. log output
        print(f"Article deleted: {self.title}")
```

Available hooks:

| Hook              | When                         |
| ----------------- | ---------------------------- |
| `before_insert`   | Before `save()` (INSERT)     |
| `after_insert`    | After `save()` (INSERT)      |
| `before_update`   | Before `save()` (UPDATE)     |
| `after_update`    | After `save()` (UPDATE)      |
| `before_delete`   | Before `delete()`            |
| `after_delete`    | After `delete()`             |

> `QuerySet.update()` / `QuerySet.delete()` do **not** invoke hooks.

## Relation Definitions

Use `has_many()` / `has_one()` / `belongs_to()` to declaratively describe FK-based related-object access. No query is issued until you `await`.

```python
from kakaorm import Model, StrColumn, ForeignKey, has_many, belongs_to

class Author(Model):
    name  = StrColumn(nullable=False)
    # Reverse 1-to-many
    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"

class Post(Model):
    title     = StrColumn(nullable=False)
    author_id = ForeignKey(Author, nullable=True)
    # Forward many-to-1 FK
    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"

# Usage
post   = await Post.get(Post.id == 1)
author = await post.author          # → Author | None

author = await Author.get(Author.id == 1)
posts  = await author.posts         # → list[Post]
```

### Relation Types

| Method        | Use case              | Return type       |
|---------------|-----------------------|-------------------|
| `has_many()`  | 1-to-many reverse     | `list[Model]`     |
| `has_one()`   | 1-to-1 reverse        | `Model \| None`   |
| `belongs_to()`| Many-to-1 forward FK  | `Model \| None`   |

You can pass the class name as a string to `related_model` to avoid circular imports:

```python
posts = has_many("Post", foreign_key="author_id")
```

## QuerySet — Query Builder

Methods such as `where()` return a `QuerySet`. SQL is not executed until you `await`.

```python
# Filter (AND)
posts = await Post.where(Post.published == True).where(Post.views >= 100)

# Compound conditions
posts = await Post.where(
    (Post.published == True) & (Post.views >= 100)
)

# OR / NOT
clause = (Post.views < 10) | (Post.published == False)
posts  = await Post.where(~clause)

# Sorting and pagination
posts = await (
    Post.where(Post.published == True)
        .order_by(Post.views.desc)
        .limit(10)
        .offset(20)
)

# SELECT specific columns
rows = await Post.all().select(Post.title, Post.views)

# COUNT / EXISTS
n      = await Post.where(Post.published == True).count()
exists = await Post.where(Post.title.like("%Python%")).exists()

# Async iteration
async for post in Post.all().order_by(Post.views.desc):
    print(post.title)
```

### WHERE Operators

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

### JOIN / GROUP BY / Aggregation

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

# Aggregation
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

### UPDATE Expressions (column references)

```python
# Fixed value
await Post.all().update(published=True)

# Expression with column reference
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

## Deletion Strategies

KakaORM lets you switch deletion behavior simply by changing the base class.

### SoftDeleteModel — Logical deletion

Automatically adds a `deleted_at` column. `delete()` sets `deleted_at` to the current time instead of physically removing the record.

```python
from kakaorm import SoftDeleteModel, StrColumn

class Post(SoftDeleteModel):
    title = StrColumn(nullable=False)

    class Meta:
        table_name = "post"

# Create table (deleted_at column is added automatically)
await engine.create_table(Post)

post = await Post.create(title="Hello")
await post.delete()             # Sets deleted_at (no physical deletion)

# Default: exclude deleted records
posts = await Post.all()        # WHERE deleted_at IS NULL

# Include deleted records
posts = await Post.include_deleted()

# Only deleted records
posts = await Post.only_deleted()

# Restore
await post.restore()

# Physical deletion
await Post.only_deleted().purge()
```

Bulk QuerySet operations work the same way:

```python
await Post.where(Post.title.like("%draft%")).delete()   # Bulk logical delete
await Post.only_deleted().restore()                     # Bulk restore
```

### ArchiveModel — Archive deletion

`delete()` moves the record to an `archive_{table}` table within a transaction (INSERT + DELETE).

```python
from kakaorm import ArchiveModel, StrColumn

class Log(ArchiveModel):
    body = StrColumn(nullable=False)

    class Meta:
        table_name = "log"

# Create both main and archive tables
await engine.create_table(Log)
await engine.create_archive_table(Log)  # Creates archive_log

log = await Log.create(body="event")
await log.delete()              # Moves to archive_log (transaction-safe)

# Default: main table only
logs = await Log.all()

# UNION ALL across both tables
logs = await Log.include_deleted()

# Archive table only
logs = await Log.only_deleted()

# Restore to main table
await log.restore()

# Physical deletion from archive
await Log.only_deleted().purge()
```

### autogenerate integration

`ArchiveModel` subclasses are automatically included in the archive table diff when running `autogenerate()`.

```python
from kakaorm.migration import VersionedMigrator

migrator = VersionedMigrator(engine)
# Both log and archive_log tables are planned
path = await migrator.autogenerate([Log], "./migrations", name="add_log")
```

### Deletion strategy comparison

| Base class | `delete()` behavior | Default SELECT | `include_deleted()` |
|---|---|---|---|
| `Model` | Physical delete | All records | — |
| `SoftDeleteModel` | Set `deleted_at` | `deleted_at IS NULL` | Remove filter |
| `ArchiveModel` | Move to `archive_{table}` | Main table only | UNION ALL |

## Raw SQL

Use raw SQL for queries that are hard to express with the ORM.

```python
# SELECT → list[dict]
rows = await engine.fetch(
    "SELECT p.title, a.name FROM post p JOIN author a ON p.author_id = a.id WHERE p.views > %s",
    [100],
)

# INSERT / UPDATE / DELETE → affected row count
affected = await engine.execute(
    "UPDATE post SET views = 0 WHERE author_id = %s",
    [author_id],
)

# Scalar value
count = await engine.fetchval("SELECT COUNT(*) FROM post WHERE published = %s", [True])
```

## Transactions

```python
async with engine.transaction():
    order = await Order.create(item="Widget", qty=1)
    await Stock.where(Stock.item == "Widget").update(qty=Stock.qty - 1)
    # Automatically rolled back on exception
```

## Migrations

```python
from kakaorm.migration import Migrator

migrator = Migrator(engine)

# Preview the migration plan
plan = await migrator.plan([Author, Post])
print(plan.sql)

# Apply
await plan.apply()

# Destructive plan including column drops
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

## Database Connections

```python
# SQLite (development / testing)
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

## FastAPI Integration

KakaORM implements the Pydantic v2 protocol, so you can use KakaORM models directly as `response_model` without defining a separate `BaseModel` subclass for responses.

```python
from contextlib import asynccontextmanager
import kakaorm
from kakaorm import Model, StrColumn, BoolColumn
from kakaorm.migration import Migrator
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel  # only for request bodies

class Todo(Model):
    title       = StrColumn(nullable=False)
    description = StrColumn(nullable=True)
    completed   = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "todo"

# Request body schema (input validation)
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

# Use KakaORM model directly as response_model
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

Swagger UI (`/docs`) automatically outputs type information for `id` / `title` / `description` / `completed`.

Start:

```bash
pip install fastapi uvicorn aiosqlite
python examples/fastapi_todo.py
# View Swagger UI at http://localhost:8000/docs
```

For detailed integration patterns, best practices, and testing strategies, see [FastAPI Integration Guide](docs/FASTAPI.md).
Additional examples:
- `examples/fastapi_advanced.py` — Dependency injection, multiple models, error handling
- `examples/fastapi_pagination.py` — Pagination & filtering
- `examples/fastapi_testing.py` — pytest + httpx testing strategies

### Pydantic-compatible Methods

```python
# Pydantic-compatible serialization
user.model_dump()
# → {"id": 1, "name": "Alice", "age": 30, "bio": None}

user.model_dump(exclude_none=True, exclude={"bio"})
# → {"id": 1, "name": "Alice", "age": 30}

# Pydantic-compatible conversion
user = User.model_validate({"name": "Alice", "age": 30})   # from dict
user = User.model_validate(other_instance)                  # from another instance
```

## Security

KakaORM always treats query values as bind parameters to prevent SQL injection.

- **Values in WHERE / LIKE / IN clauses** — always sent via bind parameters
- **Column names in `update()`** — keys not present in `_meta.columns` are rejected with `ValueError`
- **Destination column names in `insert_into()`** — similarly whitelist-validated against `_meta.columns`
- **Field names in `create()`** — unknown fields are rejected with `TypeError`

> **Application-level notes**
>
> `order_by()` expands raw strings directly into SQL.
> If ORDER BY accepts user input, implement a whitelist of allowed column names in your application layer:
>
> ```python
> ALLOWED = {"views", "title", "created_at"}
> col = user_input if user_input in ALLOWED else "id"
> results = await Post.all().order_by(f"{col} DESC")
> ```
>
> Also note that `create()` / `save()` do not restrict writes to privileged fields.
> Exclude privileged fields such as `is_admin` from user input at the application layer.

## Project Structure

```
kakaorm/
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI (lint + test matrix + MySQL + build)
├── kakaorm/                 # Package source
│   ├── __init__.py          # Public API re-exports
│   ├── py.typed             # PEP 561 type marker
│   ├── engine.py            # Engine base class + AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine, connect()
│   ├── model.py             # Model base class, AsyncORMMeta metaclass
│   ├── query.py             # QuerySet (lazy query builder)
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
│   └── fastapi_todo.py      # FastAPI TODO list API
├── tests/
│   ├── conftest.py
│   ├── test_crud.py
│   ├── test_joins.py
│   ├── test_aggregates.py
│   ├── test_transaction.py
│   ├── test_bulk_create.py
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

## License

[MIT License](LICENSE)
