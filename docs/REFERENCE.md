# KakaORM — API Reference

[日本語](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.ja.md) | [← README](https://github.com/AyumuTakai/KakaORM/blob/main/README.md)

---

## Column Types — Common Options

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

---

## Validation

Attach validators to column definitions. `save()` runs them automatically before every INSERT or UPDATE. If any fail, `ValidationError` is raised and nothing is written to the database.

```python
from kakaorm import Model, StrColumn, IntColumn, ValidationError
from kakaorm.validators import min_length, max_length, min_value, max_value, regex, one_of

class User(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(50)])
    age   = IntColumn(nullable=True,  validators=[min_value(0), max_value(150)])
    email = StrColumn(nullable=False, validators=[
        regex(r"^[^@]+@[^@]+\.[^@]+$", message="Enter a valid email address.")
    ])
    role  = StrColumn(nullable=True,  validators=[one_of("admin", "user", "guest")])

    class Meta:
        table_name = "user"
```

### Catching errors

`ValidationError.errors` is a `dict[str, list[str]]` keyed by field name:

```python
user = User(name="A", age=-5, email="bad")
try:
    await user.save()
except ValidationError as e:
    print(e.errors)
    # {
    #   "name":  ["Ensure this value has at least 2 characters."],
    #   "age":   ["Enter a value greater than or equal to 0."],
    #   "email": ["Enter a valid email address."],
    # }
```

All field errors are collected in a single pass — you get the full picture in one exception.

### Manual validation

Call `validate()` directly without hitting the database:

```python
user = User(name="Alice", age=30, email="alice@example.com")
user.validate()  # raises ValidationError immediately if anything is wrong
```

### Built-in validators

| Validator | Checks |
|---|---|
| `min_length(n)` | `len(value) >= n` |
| `max_length(n)` | `len(value) <= n` |
| `min_value(n)` | `value >= n` |
| `max_value(n)` | `value <= n` |
| `regex(pattern, message=None)` | `re.search(pattern, value)` |
| `one_of(*choices)` | `value in choices` |

All built-in validators silently skip `None` values (use `nullable=False` for presence checks).

### Custom validators

Any callable `(value: Any) -> None` works as a validator — raise `ValidationError` on failure:

```python
from kakaorm.validators import ValidationError

def no_spaces(value):
    if value and " " in value:
        raise ValidationError("Username must not contain spaces.")

class User(Model):
    username = StrColumn(nullable=False, validators=[no_spaces])
```

---

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

---

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

---

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

### Window Functions

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

#### Practical patterns

**Top-N per group** — retrieve the top 3 posts by views for each author:

```python
from kakaorm import RowNumber

# Step 1: annotate each post with its rank within its author's posts
ranked = await Post.all().select(
    Post.id,
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views.desc],   # highest views = rank 1
    ).label("rn"),
)

# Step 2: filter to top 3 in Python (or wrap in a CTE — see below)
top3 = [r for r in ranked if r["rn"] <= 3]
```

**Moving average** — 7-day rolling average of daily sales:

```python
from kakaorm import Avg

rows = await Sale.all().select(
    Sale.date,
    Sale.amount,
    Avg(Sale.amount).over(
        order_by=[Sale.date],
    ).label("moving_avg"),
).order_by(Sale.date)
```

**Period-over-period comparison** — compare each month's revenue against the previous month:

```python
from kakaorm import Lag, Sum

rows = await MonthlyRevenue.all().select(
    MonthlyRevenue.month,
    MonthlyRevenue.revenue,
    Lag(MonthlyRevenue.revenue, 1, 0).over(
        order_by=[MonthlyRevenue.month],
    ).label("prev_revenue"),
).order_by(MonthlyRevenue.month)

# revenue - prev_revenue gives the month-over-month delta
```

### CTE (WITH clause)

CTEs let you name a subquery and reference it in the main query, improving readability and enabling multi-step transformations.

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

#### Practical patterns

**Top-N per group with CTE** — combine a window function CTE with a filter:

```python
from kakaorm import RowNumber

# CTE: rank posts within each author
ranked_posts = Post.all().select(
    Post.id,
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views.desc],
    ).label("rn"),
)

# Main query: only rows where rank <= 3
# (filter applied after the CTE is materialised by the DB)
top3 = await (
    Post.all()
        .with_cte("ranked", ranked_posts)
        .join_raw("ranked", on="post.id = ranked.id")
        .select(Post.title, Post.author_id, Post.views)
        .where_raw("ranked.rn <= 3")
)
```

**Reusing a subquery** — reference an expensive subquery in multiple places:

```python
# Compute active user IDs once
active_users = User.where(User.is_active == True).select(User.id)

# Reuse the CTE in multiple joins or filters
results = await (
    Order.all()
         .with_cte("actives", active_users)
         .join_raw("actives", on="order.user_id = actives.id")
         .select(Order.id, Order.total)
         .order_by(Order.total.desc)
         .limit(100)
)
```

**Aggregate then filter** — sum orders per user and keep only high-value customers:

```python
from kakaorm import Sum

# CTE: total spend per user
user_totals = (
    Order.all()
         .select(Order.user_id, Sum(Order.total).label("total_spend"))
         .group_by(Order.user_id)
)

# Main query: join back to get user names
vip_customers = await (
    User.all()
        .with_cte("totals", user_totals)
        .join_raw("totals", on="user.id = totals.user_id")
        .select(User.name, User.email)
        .where_raw("totals.total_spend >= 10000")
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

---

## Upsert — `get_or_create` / `update_or_create`

Both methods take keyword arguments as lookup conditions and an optional `defaults` dict.
They return a `(instance, created: bool)` tuple.

### `get_or_create`

Find a record by the lookup fields. If it exists, return it unchanged. If not, create it.

```python
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "Alice"},
)
# created=True  → new record inserted (email + name)
# created=False → existing record returned (defaults ignored)
```

`defaults` is merged with the lookup kwargs only on creation:

```python
# Second call — record already exists, defaults are not applied
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "Should not change"},
)
assert created is False
assert author.name == "Alice"  # original value preserved
```

### `update_or_create`

Find a record by the lookup fields. If it exists, apply `defaults` and save. If not, create it.

```python
post, created = await Post.update_or_create(
    slug="hello-world",
    defaults={"title": "Hello World", "published": True},
)
# created=True  → new record (slug + defaults merged)
# created=False → existing record updated with defaults, then saved
```

Idempotent upsert pattern — safe to call repeatedly:

```python
for item in incoming_feed:
    await Article.update_or_create(
        external_id=item["id"],
        defaults={
            "title":      item["title"],
            "body":       item["body"],
            "updated_at": datetime.utcnow(),
        },
    )
```

### Multiple lookup fields

Pass multiple keyword arguments to match on more than one column (joined with AND):

```python
post, created = await Post.update_or_create(
    title="Draft",
    author_id=author.id,
    defaults={"published": True},
)
```

---

## Bulk Operations

Use bulk methods when inserting or updating many rows at once. Both methods reduce the number of round-trips to the database by batching statements.

### `bulk_create` — batch INSERT

```python
# Build instances without saving
posts = [Post(title=f"Post {i}", views=0) for i in range(1000)]

# Insert all at once (default batch_size=500 → 2 INSERT statements)
await Post.bulk_create(posts)

# All instances have their id set after the call
print(posts[0].id)  # e.g. 1
```

`batch_size` controls how many rows go into each `INSERT … VALUES (…), (…), …` statement.
Tune it downward if you hit database parameter limits (SQLite caps at 999 bind variables).

```python
await Post.bulk_create(posts, batch_size=200)
```

Performance comparison vs. `create()` in a loop:

| Method | 1 000 rows | SQL statements |
|---|---|---|
| `create()` in a loop | ~1 000 ms | 1 000 |
| `bulk_create()` | ~5 ms | 2 |

### `bulk_update` — batch UPDATE

```python
# Fetch records, modify in Python, then flush all at once
posts = await Post.where(Post.published == False)
for post in posts:
    post.published = True
    post.views = 0

# Update only the changed fields (recommended)
await Post.bulk_update(posts, fields=["published", "views"])
```

`fields` specifies which columns to include in the `SET` clause.
Pass `fields=None` (the default) to update every non-PK column:

```python
await Post.bulk_update(posts)  # updates all columns
```

`batch_size` works the same way as in `bulk_create`:

```python
await Post.bulk_update(posts, fields=["score"], batch_size=200)
```

### Works inside transactions

Both bulk methods respect the current transaction context:

```python
async with engine.transaction():
    await Post.bulk_create(new_posts)
    await Post.bulk_update(existing_posts, fields=["views"])
    # Both are rolled back together on exception
```

---

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

---

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

---

## Transactions

```python
async with engine.transaction():
    order = await Order.create(item="Widget", qty=1)
    await Stock.where(Stock.item == "Widget").update(qty=Stock.qty - 1)
    # Automatically rolled back on exception
```

---

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

---

## CLI Commands

After `pip install kakaorm`, the `kakaorm` command is available.

> **If the command is not found after installation**, your Python's `bin` directory may not be in `PATH`.
> Run `python -m kakaorm` as an alternative, or add the directory to `PATH`:
> ```bash
> # Check where the script was installed
> python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
> # Then add that path to your shell profile (e.g. ~/.zshrc or ~/.bashrc)
> export PATH="$PATH:/path/to/python/bin"
> ```

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

---

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

## Table Naming — Reserved Words

KakaORM automatically quotes identifiers for each database, so SQL reserved words (`order`, `select`, `group`, etc.) can be used as table names without any special handling.

```python
class Order(Model):
    class Meta:
        table_name = "order"  # KakaORM quotes this automatically
```

> **Do not quote manually.** Adding quote characters yourself causes double-quoting:
>
> ```python
> class Meta:
>     table_name = "[order]"   # ❌ becomes [[order]] on SQLite
>     table_name = '"order"'   # ❌ manual quoting is unnecessary
>     table_name = '`order`'   # ❌ manual quoting is unnecessary
> ```
>
> Where possible, prefer names that avoid reserved words (e.g. `orders` instead of `order`).
