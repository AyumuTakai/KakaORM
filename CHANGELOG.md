# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.5] - 2026-06-02

### Added

- **Query logging** — `engine.query_logging = True/False` toggles SQL output at any time.
  All statements are emitted to the `kakaorm.sql` logger at `DEBUG` level with operation
  type, full SQL, bound parameters, and elapsed time in milliseconds.
- **Column type selection guide** — new section in `docs/REFERENCE.md` / `REFERENCE.ja.md`
  covering which column class to choose (numbers, strings, dates, nullable defaults).
- **Aggregation examples in README** — `aggregate()`, `count()`, `sum()`, `group_by().having()`
  now shown in the CRUD section of `README.md` / `README.ja.md` with a link to REFERENCE.
- **Error message reference** — new section in REFERENCE documenting all descriptive errors
  with fix hints.
- **Upgrade guide** — v0.4.1 → v0.4.2 → v0.4.3 migration notes added to REFERENCE.

### Changed

- **`Migrator.run()` promoted** in REFERENCE migration section — now shown as the recommended
  one-liner; `plan().apply()` remains documented as the verbose alternative.
- **`DateTimeColumn` docs expanded** — firing timing, `nullable=False` + `auto_now_add`
  behavior, and DB storage format now explicitly documented.

### Fixed

- **`Column()` with positional argument** — raises `TypeError` with a list of type-specific
  classes (`IntColumn`, `StrColumn`, …) instead of the cryptic Python default message.
  Applies to all subclasses (`IntColumn`, `StrColumn`, `DateTimeColumn`, …).
- **`Model.__init__` typo suggestion** — unknown field names now show a `Did you mean?`
  hint via `difflib` plus the full list of available fields.
- **`ColumnMeta` / `WhereClause` passed as field value** — `Model.__init__` and
  `QuerySet.update()` now raise `TypeError` with actionable guidance instead of silently
  storing the wrong object.

## [0.4.4] - 2026-06-02

### Added

- **Examples updated** — All `examples/` (blog_example.py, fastapi_*.py, flask_todo.py) now demonstrate:
  - `Migrator.run(models)` 1-liner pattern (replaces `plan()` → `apply()` boilerplate)
  - `Migrator.validate_relationships(models)` call at startup for early error detection
  - `DateTimeColumn(auto_now_add=True)` / `DateTimeColumn(auto_now=True)` for automatic timestamps
  - `has_many()` / `belongs_to()` relationship definitions and traversal patterns
  - `bulk_create()` for batch inserts with hook application
  - blog_example.py: Author.posts reverse relation and Post.author forward relation with `await` navigation

### Fixed

- **fastapi_pagination.py bugs**:
  - `PostResponse.from_orm()` undefined class → replaced with `p.model_dump()`
  - `Post.title.contains()` unimplemented method → replaced with `Post.title.like(f"%{title}%")`
  - Missing `await` on relationship coroutine in author_name filter → wrapped in async loop with proper await

## [0.4.3] - 2026-06-02

### Added

- **`Migrator.validate_relationships(models)`** — Early validation of string-based relationship references (`has_many("Post")`, `belongs_to("Author")`). Detects typos at startup before ORM access and reports all unresolved refs in one batch; called automatically by `plan()`.
- **DateTimeColumn type conversion** — Added `from_db()` (parse ISO format strings from SQLite/TEXT columns) and `to_db()` (serialize to ISO format for consistent DB storage). Enables portable datetime handling across PostgreSQL, SQLite, and MySQL.

### Fixed

- **`auto_now_add` / `auto_now` not applied in bulk operations** — `_bulk_insert()` and `_bulk_update()` now call field hooks (`get_insert_value()`, `get_update_value()`) before collecting parameter lists. All engine backends (PostgreSQL asyncpg, SQLite aiosqlite, MySQL aiomysql) apply hooks consistently.
- **`nullable=False + auto_now_add` on ADD COLUMN fails** — `Migrator.plan()` detects auto-timestamp columns in ALTER TABLE ADD COLUMN and injects `engine._current_timestamp_default()`: PostgreSQL/MySQL use `CURRENT_TIMESTAMP`, SQLite uses literal `'1970-01-01 00:00:00'` (PRAGMA workaround for non-constant defaults).
- **Foreign Key DDL not quoted** — `ForeignKey.ddl_fragment(quote_fn)` now safely quotes target table names. `Migrator.plan()` passes `quote_fn=engine.quote_identifier` to all `ddl_fragment()` calls, producing `REFERENCES [table_name]([id])` on SQLite.
- **SQLite foreign key constraints disabled by default** — `AioSQLiteEngine.connect()` now issues `PRAGMA foreign_keys = ON` to enforce ON DELETE CASCADE and referential integrity.
- **VersionedMigrator.run(dict) conflicts with Migrator.run(models)** — Renamed `VersionedMigrator.run(dict)` → `run_manual(dict)` to avoid override. `Migrator.run([Model])` (0.4.2 API) remains unchanged for schema-only use.
- **`utcnow()` DeprecationWarning (Python 3.12)** — All code replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` for forward compatibility.

## [0.4.2] - 2026-06-02

### Added

- **`Model.find(pk)`** — Shorthand for PK lookup. Returns `None` if not found, equivalent to `get_or_none(Model.id == pk)`. Works with any PK type (integer or string custom PK).
- **`Migrator.run(models)`** — Convenience method that runs `plan()` + `apply()` in a single call. No-ops when the schema is already up to date.

### Changed

- **`connect()` missing-`await` warning** — `kakaorm.connect()` is now a regular function returning a `_ConnectAwaitable`. Forgetting `await` no longer silently discards the coroutine; a `RuntimeWarning` is raised at GC time with the message `"called without 'await' and had no effect. Fix: engine = await kakaorm.connect(url)"`.

## [0.4.1] - 2026-06-02

### Security

- **`bulk_update()` validation bypass** — `validate()` is now called on every instance before any DB write, consistent with `save()` behavior
- **`get_or_create` / `update_or_create` TOCTOU** — SELECT + INSERT/UPDATE is now wrapped in a transaction, preventing duplicate record creation under concurrent requests

## [0.4.0] - 2026-06-01

### Added

- **Validation** — Column-level validators run automatically on `save()` before any DB write:
  - Built-in validators: `min_length(n)`, `max_length(n)`, `min_value(n)`, `max_value(n)`, `regex(pattern)`, `one_of(*choices)`
  - `ValidationError` collects all field errors in a single pass (`error.errors` dict)
  - `Model.validate()` for manual validation without hitting the database
  - Custom validators: any `(value) -> None` callable that raises `ValidationError`
- **`get_or_create(defaults={}, **lookup)`** — return existing record or create; returns `(instance, created: bool)`
- **`update_or_create(defaults={}, **lookup)`** — return existing record updated with `defaults`, or create; returns `(instance, created: bool)`
- **`bulk_update(instances, fields=None, batch_size=500)`** — batch UPDATE for multiple instances; SQLite uses `executemany` for efficiency
- **`Engine._bulk_update()` / `_update_fields()`** — underlying engine methods for partial-field updates
- Expanded `docs/REFERENCE.md` and `docs/REFERENCE.ja.md`:
  - Validation section with custom validator example
  - Upsert section (`get_or_create` / `update_or_create`)
  - Bulk Operations section (`bulk_create` + `bulk_update`)
  - Window Functions practical patterns (top-N per group, moving average, period comparison)
  - CTE practical patterns (top-N with CTE, subquery reuse, aggregate-then-filter)

### Changed

- `Column.__init__` accepts `validators` parameter (list of callables, default `[]`)
- `Model.save()` now calls `validate()` before INSERT / UPDATE

## [0.3.4] - 2026-06-01

### Added

- HTML UI for `examples/flask_todo.py` — single-page frontend with vanilla JS (add/toggle/delete/filter, toast notifications)
- `docs/REFERENCE.md` / `docs/REFERENCE.ja.md` — full API reference (column options, QuerySet, relations, migrations, security, etc.)
- `docs/FLASK.md` / `docs/FLASK.ja.md` — Flask integration guide (engine lifecycle, async views, testing, `.env` usage)
- `docs/FASTAPI.ja.md` — Japanese FastAPI integration guide

### Changed

- README split into lean overview (~300 lines) + separate reference/integration docs
- English `README.md` is now the primary README; Japanese version moved to `README.ja.md`
