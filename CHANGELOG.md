# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- HTML UI for `examples/flask_todo.py` — single-page frontend with vanilla JS (add/toggle/delete/filter, toast notifications)
- `docs/REFERENCE.md` / `docs/REFERENCE.ja.md` — full API reference (column options, QuerySet, relations, migrations, security, etc.)
- `docs/FLASK.md` / `docs/FLASK.ja.md` — Flask integration guide (engine lifecycle, async views, testing, `.env` usage)
- `docs/FASTAPI.ja.md` — Japanese FastAPI integration guide

### Changed

- README split into lean overview (~300 lines) + separate reference/integration docs
- English `README.md` is now the primary README; Japanese version moved to `README.ja.md`
- "Table Naming — Reserved Words" anti-pattern note added to `docs/REFERENCE.md`

### Fixed

- Quoted `pip install "kakaorm[extras]"` in all example files to fix zsh glob expansion error
- All relative links in README files replaced with absolute GitHub URLs (fixes broken links on PyPI)
- `pip install` instructions in examples now include `kakaorm` itself

### Removed

- `RESERVED_WORD_SUPPORT.md` — relevant content merged into `docs/REFERENCE.md`

---

## [0.3.3] - 2026-06-01

### Fixed

- Replace `typer[all]` with `typer` in dependencies — the `[all]` extra no longer exists in typer 0.12+, causing a warning on install

### Changed

- Add CLI PATH troubleshooting note to README with `python -m kakaorm` as an alternative

---

## [0.3.2] - 2026-06-01

### Changed

- English README (`README.en.md`) is now the primary `README.md`; Japanese version renamed to `README.ja.md`
- All relative links replaced with absolute GitHub URLs so links work correctly on both PyPI and GitHub

---

## [0.3.1] - 2026-06-01

### Fixed

- Correct GitHub repository URL casing in `pyproject.toml` (`ayumu-takai` → `AyumuTakai`)

---

## [0.3.0] - 2026-06-01

### Added

- **SoftDeleteModel** — Logical deletion base class:
  - `delete()` sets `deleted_at` instead of physically removing the record
  - `deleted_at` column is added automatically
  - Default queries exclude soft-deleted records (`deleted_at IS NULL`)
  - `include_deleted()` — include soft-deleted records in queries
  - `only_deleted()` — query only soft-deleted records
  - `restore()` — cancel logical deletion (instance and QuerySet level)
  - `purge()` — physically delete soft-deleted records
  - `count()`, `update()`, `aggregate()` respect the deletion filter automatically
- **ArchiveModel** — Archive deletion base class:
  - `delete()` moves the record to `archive_{table}` within a transaction (INSERT + DELETE)
  - Archive table is created separately via `engine.create_archive_table(Model)`
  - Default queries target the main table only
  - `include_deleted()` — UNION ALL across main and archive tables
  - `only_deleted()` — query the archive table only
  - `restore()` — move record back from archive to main table (instance and QuerySet level)
  - `purge()` — physically delete from the archive table
- **`engine.create_archive_table()`** — Creates `archive_{table}` with the same schema as the main table plus an `archived_at` timestamp column
- **autogenerate archive support** — `autogenerate()` now detects `ArchiveModel` subclasses and includes the archive table in the diff plan automatically

### Changed

- `Migrator.plan()` expands `ArchiveModel` subclasses to also plan their corresponding archive tables

[0.3.0]: https://github.com/AyumuTakai/KakaORM/releases/tag/v0.3.0

## [0.2.0] - 2026-06-01

### Added

- **CTE (WITH clause)** — Complex query support via `with_cte()` method
- **Eager loading (prefetch)** — N+1 problem elimination with `prefetch()` method for all relationship types
- **Migration downgrade** — Rollback capability via `downgrade()` method with automatic reverse SQL generation
- **Migration autogenerate** — Automatic migration file generation via `autogenerate()` from model-DB diffs
- **Migration CLI** — Command-line interface via `kakaorm` command:
  - `kakaorm init` — Initialize migrations directory
  - `kakaorm makemigrations` — Auto-generate migration files
  - `kakaorm migrate` — Apply or rollback migrations
  - `kakaorm showmigrations` — View migration history
- **Window Functions** — SQL window functions support:
  - `RowNumber()`, `Rank()`, `DenseRank()` for ranking
  - `Lag()`, `Lead()` for offset functions
  - `Sum().over()`, `Avg().over()`, `Min().over()`, `Max().over()` for aggregate windows
- **FastAPI Integration Guide** — Comprehensive documentation with 3 example implementations:
  - `fastapi_advanced.py` — Dependency injection and multi-model patterns
  - `fastapi_pagination.py` — Pagination and filtering
  - `fastapi_testing.py` — Testing strategies

### Changed

- Enhanced `QuerySet._parse_exprs()` to recognize and handle window functions
- Extended `AggFunc` with `.over()` method for aggregate window support
- Improved `Pydantic v2` integration documentation

### Fixed

- None reported

[0.2.0]: https://github.com/AyumuTakai/KakaORM/releases/tag/v0.2.0

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
