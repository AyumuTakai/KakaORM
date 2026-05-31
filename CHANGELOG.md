# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-01

### Added

- `Model` base class with `AsyncORMMeta` metaclass for declarative model definitions
- Column types: `IntColumn`, `StrColumn`, `FloatColumn`, `BoolColumn`, `DateTimeColumn`, `DateColumn`, `TimeColumn`, `DecimalColumn`, `ForeignKey`
- User-defined primary keys (`primary_key=True` on any column)
- `QuerySet` lazy query builder with chainable API: `where()`, `order_by()`, `limit()`, `offset()`, `select()`, `group_by()`, `having()`
- WHERE operators: `==`, `!=`, `>=`, `>`, `<=`, `<`, `IS NULL`, `LIKE`, `ILIKE`, `IN`, `NOT IN`, `BETWEEN`
- Boolean operators: `&` (AND), `|` (OR), `~` (NOT)
- Aggregate functions: `Count`, `Sum`, `Avg`, `Max`, `Min`
- `CASE WHEN` expression support in SELECT and UPDATE
- JOIN support: `join()` (INNER), `left_join()` (LEFT OUTER)
- Subquery support: `WHERE col IN (SELECT ...)` via `Subquery`
- Bulk operations: `bulk_create()`, `QuerySet.update()`, `QuerySet.delete()`, `truncate()`
- `INSERT ... SELECT` via `QuerySet.insert_into()`
- UPDATE column-reference expressions: `Post.all().update(views=Post.views + 1)`
- Event hooks: `before_insert`, `after_insert`, `before_update`, `after_update`, `before_delete`, `after_delete`
- Relationship descriptors: `has_many()`, `has_one()`, `belongs_to()`
- Composite indexes via `Meta.indexes`
- CHECK constraints via `check=` column option
- Explicit transaction support via `engine.transaction()` context manager
- Raw SQL access: `engine.fetch()`, `engine.execute()`, `engine.fetchval()`
- `Migrator` — diff-based schema migration (ADD COLUMN, DROP COLUMN, ADD CONSTRAINT)
- `VersionedMigrator` — migration history tracked in `kakaorm_migrations` table
- `DROP TABLE CASCADE` support
- Pydantic v2 protocol: `model_dump()`, `model_validate()`, `__get_pydantic_core_schema__()`, `__get_pydantic_json_schema__()` — enables direct use as FastAPI `response_model`
- Engine backends: `AsyncpgEngine` (PostgreSQL/asyncpg), `Psycopg3Engine` (PostgreSQL/psycopg3), `AioSQLiteEngine` (SQLite/aiosqlite), `AioMySQLEngine` (MySQL-MariaDB/aiomysql)
- `connect()` factory function with URL-based engine selection
- Security: column-name whitelist validation on `update()` and `insert_into()`
- `py.typed` marker for PEP 561 compliance

[0.1.0]: https://github.com/AyumuTakai/KakaORM/releases/tag/v0.1.0
