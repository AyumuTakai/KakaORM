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
- **Auto migrations** — Detects diff between models and DB schema and generates `ALTER TABLE`
- **Generic descriptors** — Type annotation inference via `Column[T]` for correct IDE completion
- **Event hooks** — Define `before_insert` / `after_update` etc. directly on your Model
- **Relation definitions** — Declare FK navigation (forward and reverse) with `has_many()` / `has_one()` / `belongs_to()`
- **Pydantic v2 integration** — Implements `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__`; use KakaORM models directly as FastAPI `response_model`
- **Eager loading** — Batch-fetch related models with `prefetch()` to eliminate N+1 queries
- **Migration autogenerate** — Auto-generate diff files with `autogenerate()`; manage with `run_files()` + `downgrade()`
- **CTE (WITH clause)** — Structure complex queries with `with_cte(name, queryset)`
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
ForeignKey(Author, on_delete="CASCADE")    # default: CASCADE
ForeignKey(Author, on_delete="SET NULL")   # set referencing column to NULL
ForeignKey(Author, on_delete="RESTRICT")   # prevent deletion
ForeignKey(Author, on_delete="NO ACTION")  # database default behavior
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

# As a dict
author = await Author.get(Author.id == 1)
data = author.to_dict()         # {"id": 1, "name": "Alice", "email": "..."}
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

| Method         | Use case                         | Return type      |
|----------------|----------------------------------|------------------|
| `has_many()`   | 1-to-many reverse (FK on other)  | `list[Model]`    |
| `has_one()`    | 1-to-1 reverse (FK on other)     | `Model \| None`  |
| `belongs_to()` | Many-to-1 forward FK             | `Model \| None`  |

You can pass the class name as a string to `related_model` to avoid circular imports:

```python
posts = has_many("Post", foreign_key="author_id")
```

**`has_one()` example** — Author with a one-to-one Profile:

```python
from kakaorm import Model, StrColumn, IntColumn, ForeignKey, has_one, belongs_to

class Author(Model):
    name    = StrColumn(nullable=False)
    profile = has_one("Profile", foreign_key="author_id")  # FK is on Profile

    class Meta:
        table_name = "author"

class Profile(Model):
    bio       = StrColumn(nullable=True)
    author_id = ForeignKey(Author, nullable=False)
    author    = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "profile"

author  = await Author.get(Author.id == 1)
profile = await author.profile   # → Profile | None (queried by author_id == author.id)
```

### Eager Loading (N+1 elimination)

`prefetch()` batch-fetches related models in a single query and caches the results.

```python
# Without prefetch — N+1 queries
posts = await Post.all()
for post in posts:
    author = await post.author  # fires a SELECT per post

# With prefetch — 2 queries total
posts = await Post.all().prefetch("author")
for post in posts:
    author = await post.author  # served from cache, no extra query

# Prefetch multiple relations at once
posts = await Post.all().prefetch("author", "comments")
```

Performance comparison:

| Case | Records | SQL queries |
|------|---------|-------------|
| Without prefetch | 10 | 11 (1 + 10) |
| Without prefetch | 100 | 101 (1 + 100) |
| With prefetch | 10 | 2 |
| With prefetch | 100 | 2 |

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

# SELECT specific columns (replaces existing SELECT)
rows = await Post.all().select(Post.title, Post.views)

# Append columns to an existing SELECT (does not replace)
base = Post.all().select(Post.id, Post.title)
rows = await base.also_select(Post.views, Post.author_id)
# → SELECT id, title, views, author_id FROM post

# COUNT / EXISTS
n      = await Post.where(Post.published == True).count()
exists = await Post.where(Post.title.like("%Python%")).exists()

# Async iteration (QuerySet supports async for)
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
Post.score.is_null()       # IS NULL  (equivalent to == None)
Post.score.is_not_null()   # IS NOT NULL  (equivalent to != None)
```

### Logical Operators

Combine `WhereClause` values returned by comparison operators using `&` (AND), `|` (OR), and `~` (NOT) to build complex, type-safe conditions.

| Operator | SQL | Usage |
|----------|-----|-------|
| `&` | `AND` | `clause_a & clause_b` |
| `\|` | `OR` | `clause_a \| clause_b` |
| `~` | `NOT` | `~clause` |
| `.where().where()` | `AND` | method chaining |
| `.exclude(clause)` | `NOT (clause)` | syntactic sugar for negation |

```python
# AND: & operator
posts = await Post.where(
    (Post.published == True) & (Post.views >= 100)
)
# WHERE (published = ?) AND (views >= ?)

# OR: | operator
posts = await Post.where(
    (Post.published == True) | (Post.author_id == 1)
)
# WHERE (published = ?) OR (author_id = ?)

# NOT: ~ operator
posts = await Post.where(~(Post.published == False))
# WHERE NOT (published = ?)

# AND chaining: .where().where()
posts = await (
    Post.where(Post.published == True)
        .where(Post.views >= 100)
)
# WHERE (published = ?) AND (views >= ?)
# ※ Each .where() call is always joined with AND

# exclude: syntactic sugar for NOT
posts = await Post.all().exclude(Post.published == False)
# WHERE NOT (published = ?)

# Complex compound conditions
posts = await Post.where(
    (Post.published == True) &
    ((Post.views >= 1000) | (Post.author_id.in_([1, 2, 3]))) &
    ~Post.title.like("%draft%")
)
# WHERE (published = ?)
#   AND ((views >= ?) OR (author_id IN (?,?,?)))
#   AND NOT (title LIKE ?)
```

> **Precedence** — Python's operator precedence applies: `~` binds most tightly, then `&`, then `|`.
> Use parentheses for compound conditions to ensure the intended grouping.

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

# RIGHT JOIN
rows = await (
    Post.all()
        .right_join(Author, on=Post.author_id == Author.id)
        .select(Post.title, Author.name)
)

# Subquery (IN / NOT IN)
from kakaorm import Subquery

active_authors = Author.where(Author.is_active == True).select(Author.id)
posts = await Post.where(Post.author_id.in_(Subquery(active_authors)))
# WHERE author_id IN (SELECT id FROM author WHERE is_active = ?)

# Passing a QuerySet directly works the same way
posts = await Post.where(Post.author_id.in_(active_authors))

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

### Aggregate Functions

#### Quick Aggregate Methods

`QuerySet` provides shortcut methods that return a single aggregated value.

```python
# Count
n = await Post.all().count()                            # COUNT(*)
n = await Post.where(Post.published == True).count()    # with WHERE

# Sum / Average / Max / Min
total = await Post.all().sum(Post.views)
avg   = await Post.all().avg(Post.score)
hi    = await Post.all().max(Post.views)
lo    = await Post.all().min(Post.score)

# Existence check
has_draft = await Post.where(Post.published == False).exists()  # bool
```

#### aggregate() — Multiple Aggregates in One Query

Retrieve multiple aggregated values in a single SQL statement.

```python
from kakaorm import Sum, Avg, Max, Min, Count

stats = await Post.all().aggregate(
    total_views = Sum(Post.views),
    avg_score   = Avg(Post.score),
    max_views   = Max(Post.views),
    post_count  = Count(Post.id),
)
# {
#   "total_views": 12500,
#   "avg_score": 3.8,
#   "max_views": 2000,
#   "post_count": 42
# }

# Combined with WHERE filters
stats = await Post.where(Post.published == True).aggregate(
    published_views = Sum(Post.views),
    published_count = Count(Post.id),
)
```

#### Aggregate Classes in SELECT

Pass aggregate classes to `select()` to mix columns and aggregate values in the result. Use `.label()` to name the result key.

| Class | SQL function | Argument |
|-------|-------------|----------|
| `Count(col)` | `COUNT(col)` | Omit for `COUNT(*)` |
| `Sum(col)` | `SUM(col)` | Required |
| `Avg(col)` | `AVG(col)` | Required |
| `Max(col)` | `MAX(col)` | Required |
| `Min(col)` | `MIN(col)` | Required |

```python
from kakaorm import Count, Sum, Avg

rows = await (
    Post.all()
        .select(
            Post.author_id,
            Count(Post.id).label("post_count"),
            Sum(Post.views).label("total_views"),
            Avg(Post.score).label("avg_score"),
        )
        .group_by(Post.author_id)
)
# [
#   {"author_id": 1, "post_count": 3, "total_views": 3600, "avg_score": 4.0},
#   {"author_id": 2, "post_count": 1, "total_views":  100, "avg_score": 3.5},
# ]
```

#### GROUP BY / HAVING

Use `.group_by()` to group results and `.having()` to filter after aggregation.
Aggregate class comparison operators (`==`, `!=`, `>`, `>=`, `<`, `<=`) generate HAVING conditions.

```python
from kakaorm import Count, Sum

# Authors with 2 or more posts
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .having(Count(Post.id) >= 2)
)

# Authors with total views >= 1000 AND at least 3 posts
rows = await (
    Post.all()
        .select(Post.author_id, Sum(Post.views).label("views"))
        .group_by(Post.author_id)
        .having(Sum(Post.views) >= 1000)
        .having(Count(Post.id) >= 3)     # chained .having() joins with AND
)

# Sort by aggregate result
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .order_by(Count(Post.id).desc)
)
```

#### Window Functions

Classes generating `OVER (PARTITION BY ... ORDER BY ...)` clauses.
Window functions can only be used in `select()` (not in `where()` / `having()`).

```python
from kakaorm import RowNumber, Rank, DenseRank, Lag, Lead, Sum, Avg

# Row number per author, ordered by views
rows = await Post.all().select(
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views],
    ).label("row_num"),
)

# Global ranking (with ties)
rows = await Post.all().select(
    Post.title,
    Post.views,
    Rank().over(order_by=[Post.views]).label("rank"),
    DenseRank().over(order_by=[Post.views]).label("dense_rank"),
)

# Preceding row value (LAG)
rows = await Post.all().select(
    Post.title,
    Post.views,
    Lag(Post.views, 1, 0).over(order_by=[Post.views]).label("prev_views"),
)

# Following row value (LEAD)
rows = await Post.all().select(
    Post.title,
    Post.views,
    Lead(Post.views, 1, 0).over(order_by=[Post.views]).label("next_views"),
)

# Cumulative sum (SUM OVER)
rows = await Post.all().select(
    Post.title,
    Post.views,
    Sum(Post.views).over(
        partition_by=[Post.author_id],
        order_by=[Post.views],
    ).label("cumulative_views"),
)
```

Available window function classes:

| Class | SQL | Description |
|-------|-----|-------------|
| `RowNumber()` | `ROW_NUMBER()` | Unique sequential row number |
| `Rank()` | `RANK()` | Ties share rank; next rank is skipped |
| `DenseRank()` | `DENSE_RANK()` | Ties share rank; next rank is not skipped |
| `Lag(col, n, default)` | `LAG(col, n, default)` | Value n rows before |
| `Lead(col, n, default)` | `LEAD(col, n, default)` | Value n rows after |
| `Sum(col).over(...)` | `SUM(col) OVER (...)` | Running total |
| `Avg(col).over(...)` | `AVG(col) OVER (...)` | Moving average |
| `Max(col).over(...)` | `MAX(col) OVER (...)` | Window maximum |
| `Min(col).over(...)` | `MIN(col) OVER (...)` | Window minimum |

> **Note** Window functions are not supported by SQLite. Use PostgreSQL, MySQL 8.0+, or MariaDB 10.2+.

### CTE (WITH clause)

```python
# Define high-earning departments as a CTE, then JOIN
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

### UPDATE Expressions (column references)

```python
# Fixed value
await Post.all().update(published=True)

# Expression with column reference
await Post.all().update(views=Post.views + 1)
await Product.all().update(price=Product.price * 0.97)
```

### CASE WHEN Expressions

Use `Case` and `When` to express SQL `CASE WHEN ... THEN ... ELSE ... END`.
Usable both in `select()` column lists and `update()` SET values.

```python
from kakaorm import Case, When

# In SELECT: compute a category label based on age
rows = await User.all().select(
    User.id,
    User.name,
    Case(
        When(User.age >= 18, then="adult"),
        When(User.age >= 13, then="teen"),
        default="child",
    ).label("category"),
)
# → [{"id": 1, "name": "Alice", "category": "adult"}, ...]

# In UPDATE: bulk-update tier based on price range
await Product.all().update(
    tier=Case(
        When(Product.price >= 10000, then="premium"),
        When(Product.price >= 3000,  then="standard"),
        default="budget",
    )
)
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

### Manual Migrations

```python
from kakaorm.migration import Migrator

migrator = Migrator(engine)

# Preview the migration plan
plan = await migrator.plan([Author, Post])
print(plan.sql)       # UP SQL
print(plan.down_sql)  # DOWN SQL (reverse order)

# Apply / rollback
await plan.apply()
await plan.apply_down()  # rollback

# Destructive plan including column drops
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

### File-based Migrations (recommended)

```python
from kakaorm.migration import VersionedMigrator

migrator = VersionedMigrator(engine)

# 1. Auto-generate a migration file from model-vs-DB diff
path = await migrator.autogenerate([User, Post], "./migrations", name="add_bio")
# → migrations/0001_add_bio.py is created

# 2. Apply all pending migrations
n = await migrator.run_files("./migrations")

# 3. Roll back the latest migration
await migrator.downgrade(steps=1)

# View migration history
for record in await migrator.history():
    print(record.name, record.applied_at)
```

Generated migration file format:

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

## CLI Commands

After `pip install kakaorm`, the `kakaorm` command is available.

```bash
# Initialize project (creates migrations/ directory and config)
kakaorm init

# Generate a migration file from model-vs-DB diff
kakaorm makemigrations --models myapp.models --db sqlite+aiosqlite:///./dev.db --name add_user_bio

# Apply all pending migrations
kakaorm migrate --db sqlite+aiosqlite:///./dev.db

# Roll back the latest N migrations
kakaorm migrate --db sqlite+aiosqlite:///./dev.db --direction down --steps 1

# Show migration history
kakaorm showmigrations --db sqlite+aiosqlite:///./dev.db
```

| Command | Description |
|---|---|
| `init` | Initialize `migrations/` directory and config file |
| `makemigrations` | Output a migration file from model-vs-DB diff |
| `migrate` | Apply pending migrations (`--direction down` to roll back) |
| `showmigrations` | Display migration history as a table |

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

# Request body schema (input validation only)
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
python examples/fastapi_todo.py
# View Swagger UI at http://localhost:8000/docs
```

For detailed integration patterns, best practices, and testing strategies, see [FastAPI Integration Guide](https://github.com/AyumuTakai/KakaORM/blob/main/docs/FASTAPI.md).
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
> Also note that `create()` / `save()` do not restrict writes to privileged fields (e.g. `is_admin`).
> Exclude such fields from user input at the application layer.

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

[MIT License](https://github.com/AyumuTakai/KakaORM/blob/main/LICENSE)
