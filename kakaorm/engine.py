"""
Engine — DB ドライバ抽象化
===========================
asyncpg / psycopg3 / aiosqlite / aiomysql のどれを使っても同じ API で動く。

設計:
  - Engine は抽象基底クラス
  - _adapt_ddl() で DB 方言ごとの型変換を一元管理
  - _post_process_col_defs() / _table_suffix で create_table の差分を吸収
  - connect() が URL をパースして適切な Engine を返し、すべての Model に登録
  - コネクションプールを内部管理する

使い方:
    engine = await kakaorm.connect("postgresql+asyncpg://user:pw@localhost/db")
    engine = await kakaorm.connect("sqlite+aiosqlite:///./dev.db")
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
"""

from __future__ import annotations

import contextvars
import logging
import re
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

_sql_logger = logging.getLogger("kakaorm.sql")

# ── トランザクション用 ContextVar ─────────────────────────────
# asyncio タスクごとに独立した値を持つため、並列リクエストが干渉しない。

# SQLite: トランザクション中は auto-commit を抑制するフラグ
_in_tx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "kakaorm_in_tx", default=False
)
# プール型 Engine: トランザクション専用の接続を保持
_tx_conn: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "kakaorm_tx_conn", default=None
)


# ── 抽象 Engine ───────────────────────────────────────────────

class Engine(ABC):
    """
    DB ドライバの共通インターフェース。
    SQL 文字列と bind パラメータを受け取り、実行する。
    """

    #: True にするとすべての SQL を kakaorm.sql ロガーに DEBUG レベルで出力する。
    #: ``engine.query_logging = True`` で有効化、``False`` で無効化できる。
    query_logging: bool = False

    @abstractmethod
    async def connect(self) -> None:
        """コネクション (プール) を初期化する。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """コネクション (プール) を閉じる。"""

    @abstractmethod
    async def _raw_fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        """SELECT 結果を dict のリストで返す（ログなし低レベル実装）。"""

    @abstractmethod
    async def _raw_execute(self, sql: str, params: list[Any]) -> int:
        """INSERT/UPDATE/DELETE を実行し影響行数を返す（ログなし低レベル実装）。"""

    @abstractmethod
    async def _raw_fetchval(self, sql: str, params: list[Any]) -> Any:
        """スカラー値を 1 つ返す（ログなし低レベル実装）。"""

    # ── ログ付きラッパー（全クエリの唯一の通過点）────────────

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if not self.query_logging:
            return await self._raw_fetch(sql, params)
        t = time.perf_counter()
        result = await self._raw_fetch(sql, params)
        ms = (time.perf_counter() - t) * 1000
        _sql_logger.debug("SELECT  %s  params=%r  (%.1fms)", sql, params, ms)
        return result

    async def _execute(self, sql: str, params: list[Any]) -> int:
        if not self.query_logging:
            return await self._raw_execute(sql, params)
        t = time.perf_counter()
        result = await self._raw_execute(sql, params)
        ms = (time.perf_counter() - t) * 1000
        op = sql.split()[0].upper() if sql else "SQL"
        _sql_logger.debug("%s  %s  params=%r  (%.1fms)", op, sql, params, ms)
        return result

    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
        if not self.query_logging:
            return await self._raw_fetchval(sql, params)
        t = time.perf_counter()
        result = await self._raw_fetchval(sql, params)
        ms = (time.perf_counter() - t) * 1000
        _sql_logger.debug("INSERT  %s  params=%r  (%.1fms)", sql, params, ms)
        return result

    @asynccontextmanager
    async def transaction(self):
        """
        トランザクションを開始するコンテキストマネージャ。
        正常終了でコミット、例外発生でロールバックする。

        使い方::

            async with engine.transaction():
                await Order.create(...)
                await Stock.where(...).update(qty=Stock.qty - 1)

        サブクラスでオーバーライドして実装する。
        """
        raise NotImplementedError(f"{type(self).__name__} は transaction() を実装していません")
        yield  # asynccontextmanager として認識させるために必要

    # ── DB 方言別 DDL 変換 ────────────────────────────────────

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """
        テーブル名やカラム名をDB方言に応じてクォートする。

        - PostgreSQL: "name"
        - SQLite: [name]
        - MySQL: `name`
        """

    def _adapt_ddl(self, ddl: str) -> str:
        """カラム DDL を DB 方言に合わせて変換する。デフォルトはそのまま返す。"""
        return ddl

    def _current_timestamp_default(self) -> str:
        """
        auto_now_add / auto_now 列を既存テーブルに ADD COLUMN するときに使う
        DEFAULT 句を返す。既存行の NOT NULL 制約を満たすためのフォールバック値。

        PostgreSQL / MySQL は CURRENT_TIMESTAMP を使える。
        SQLite は ALTER TABLE ADD COLUMN で CURRENT_TIMESTAMP が非定数扱いとなるため
        リテラル文字列で代替する（サブクラスでオーバーライド）。
        """
        return "DEFAULT CURRENT_TIMESTAMP"

    def _post_process_col_defs(self, col_defs: list[str]) -> list[str]:
        """カラム定義リストの後処理。デフォルトはそのまま返す。"""
        return col_defs

    @property
    def _table_suffix(self) -> str:
        """CREATE TABLE 末尾に付加する文字列。デフォルトは空。"""
        return ""

    # ── Raw SQL 公開 API ─────────────────────────────────────

    async def fetch(
        self, sql: str, params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Raw SQL で SELECT を実行し、行を dict のリストで返す。

        プレースホルダーは ``%s`` を使用する（内部で DB 方言に変換）。

        例::

            rows = await engine.fetch(
                "SELECT p.title, a.name FROM post p"
                " JOIN author a ON p.author_id = a.id"
                " WHERE p.views > %s",
                [100],
            )
        """
        return await self._fetch(sql, params or [])

    async def execute(self, sql: str, params: list[Any] | None = None) -> int:
        """
        Raw SQL で INSERT / UPDATE / DELETE を実行し、影響行数を返す。

        例::

            affected = await engine.execute(
                "UPDATE post SET views = 0 WHERE author_id = %s",
                [author_id],
            )
        """
        return await self._execute(sql, params or [])

    async def fetchval(self, sql: str, params: list[Any] | None = None) -> Any:
        """
        Raw SQL でスカラー値を 1 つ返す。COUNT / MAX / MIN などに使う。

        例::

            count = await engine.fetchval(
                "SELECT COUNT(*) FROM post WHERE published = %s",
                [True],
            )
        """
        rows = await self._fetch(sql, params or [])
        if not rows:
            return None
        return next(iter(rows[0].values()))

    # ── ORM 内部から呼ばれる操作 ─────────────────────────────

    async def _insert(self, instance: Any) -> None:
        """Model インスタンスを INSERT し、生成された pk を書き戻す。"""
        meta = instance._meta
        pk_name = meta.pk_name
        is_auto = meta.is_auto_pk

        # auto_now_add など挿入時フックを適用してから列を収集する
        for name, col in meta.columns.items():
            if hasattr(col, "get_insert_value"):
                new_val = col.get_insert_value(instance._data.get(name))
                if new_val is not None:
                    instance._data[name] = new_val

        if is_auto:
            cols = [
                name for name, col in meta.columns.items()
                if not col.primary_key and instance._data.get(name) is not None
            ]
        else:
            cols = [
                name for name, col in meta.columns.items()
                if instance._data.get(name) is not None
            ]

        values = [meta.columns[c].to_db(instance._data[c]) for c in cols]
        placeholders = self._placeholders(len(cols))

        # Quote table name and column names
        table = self.quote_identifier(meta.table_name)
        cols_quoted = [self.quote_identifier(c) for c in cols]

        if is_auto:
            sql = (
                f"INSERT INTO {table} ({', '.join(cols_quoted)}) "
                f"VALUES ({placeholders}) "
                f"RETURNING {self.quote_identifier(pk_name)}"
            )
            new_pk = await self._fetchval(sql, values)
            instance._data[pk_name] = new_pk
        else:
            sql = (
                f"INSERT INTO {table} ({', '.join(cols_quoted)}) "
                f"VALUES ({placeholders})"
            )
            await self._execute(sql, values)

    async def _update(self, instance: Any) -> None:
        """Model インスタンスを UPDATE する。"""
        meta = instance._meta
        pk_name = meta.pk_name

        # auto_now など更新時フックを適用する
        for name, col in meta.columns.items():
            if hasattr(col, "get_update_value"):
                instance._data[name] = col.get_update_value(instance._data.get(name))

        col_names = [
            name for name, col in meta.columns.items()
            if not col.primary_key
        ]
        values = [meta.columns[c].to_db(instance._data.get(c)) for c in col_names]
        set_clause = ", ".join(
            f"{self.quote_identifier(name)} = {self._param(i + 1)}" for i, name in enumerate(col_names)
        )
        pk_placeholder = self._param(len(col_names) + 1)
        table = self.quote_identifier(meta.table_name)
        sql = (
            f"UPDATE {table} "
            f"SET {set_clause} "
            f"WHERE {self.quote_identifier(pk_name)} = {pk_placeholder}"
        )
        await self._execute(sql, values + [instance._data[pk_name]])

    async def _delete(self, model_cls: Any, pk: Any) -> None:
        """primary key で 1 件 DELETE する。"""
        meta = model_cls._meta
        pk_name = meta.pk_name
        pk_placeholder = self._param(1)
        table = self.quote_identifier(meta.table_name)
        sql = f"DELETE FROM {table} WHERE {self.quote_identifier(pk_name)} = {pk_placeholder}"
        await self._execute(sql, [pk])

    async def _bulk_insert(self, model_cls: Any, instances: list) -> None:
        """
        複数インスタンスを一括 INSERT する。
        デフォルト実装は1件ずつ INSERT するループ。
        各サブクラスでオーバーライドして効率化する。
        """
        for instance in instances:
            await self._insert(instance)

    async def _update_fields(self, instance: Any, fields: list[str] | None) -> None:
        """指定フィールドのみ UPDATE する。fields が None なら全非 PK フィールドを更新。"""
        meta = instance._meta
        pk_name = meta.pk_name

        # auto_now など更新時フックを適用する
        for name, col in meta.columns.items():
            if hasattr(col, "get_update_value"):
                instance._data[name] = col.get_update_value(instance._data.get(name))

        col_names = [
            name for name, col in meta.columns.items()
            if not col.primary_key and (
                fields is None
                or name in fields
                or getattr(col, "auto_now", False)
            )
        ]
        if not col_names:
            return
        values = [meta.columns[c].to_db(instance._data.get(c)) for c in col_names]
        set_clause = ", ".join(
            f"{self.quote_identifier(name)} = {self._param(i + 1)}"
            for i, name in enumerate(col_names)
        )
        pk_placeholder = self._param(len(col_names) + 1)
        table = self.quote_identifier(meta.table_name)
        sql = (
            f"UPDATE {table} "
            f"SET {set_clause} "
            f"WHERE {self.quote_identifier(pk_name)} = {pk_placeholder}"
        )
        await self._execute(sql, values + [instance._data[pk_name]])

    async def _bulk_update(self, instances: list, fields: list[str] | None = None) -> None:
        """
        複数インスタンスを一括 UPDATE する。
        デフォルト実装は1件ずつ UPDATE するループ。
        各サブクラスでオーバーライドして効率化する。
        """
        for instance in instances:
            await self._update_fields(instance, fields)

    async def create_table(self, model_cls: Any, *, if_not_exists: bool = True) -> None:
        """モデルクラスから CREATE TABLE 文を生成して実行する。"""
        meta = model_cls._meta
        exists = "IF NOT EXISTS " if if_not_exists else ""
        col_defs = [
            f"  {self.quote_identifier(col_name)} {self._adapt_ddl(col.ddl_fragment(quote_fn=self.quote_identifier))}"
            for col_name, col in meta.columns.items()
        ]
        col_defs = self._post_process_col_defs(col_defs)
        quoted_table = self.quote_identifier(meta.table_name)
        sql = (
            f"CREATE TABLE {exists}{quoted_table} (\n"
            + ",\n".join(col_defs)
            + f"\n){self._table_suffix}"
        )
        await self._execute(sql, [])
        await self._create_indexes(meta, if_not_exists=if_not_exists)

    async def _create_indexes(self, meta: Any, *, if_not_exists: bool = True) -> None:
        """Meta.indexes で宣言された複合インデックスを CREATE INDEX で発行する。"""
        exists = "IF NOT EXISTS " if if_not_exists else ""
        for idx_cols in meta.indexes:
            idx_name = f"idx_{meta.table_name}_{'_'.join(idx_cols)}"
            # カラム名をクォート
            quoted_cols = ", ".join(self.quote_identifier(col) for col in idx_cols)
            quoted_table = self.quote_identifier(meta.table_name)
            sql = f"CREATE INDEX {exists}{idx_name} ON {quoted_table} ({quoted_cols})"
            await self._execute(sql, [])

    async def create_archive_table(self, model_cls: Any, *, if_not_exists: bool = True) -> None:
        """
        ArchiveModel のアーカイブテーブルを作成する。

        メインテーブルと同じカラム構成に archived_at カラムを追加する。
        id カラムの AUTO_INCREMENT は無効化する（元の値を保持するため）。

        例::

            class Log(ArchiveModel):
                body = StrColumn()

            await engine.create_table(Log)
            await engine.create_archive_table(Log)
            # → archive_log テーブルが作成される
        """
        from kakaorm.columns.types import DateTimeColumn, IntColumn

        meta = model_cls._meta
        archive_table = model_cls._archive_table_name()
        exists = "IF NOT EXISTS " if if_not_exists else ""

        col_defs: list[str] = []
        for col_name, col in meta.columns.items():
            if getattr(col, "auto_increment", False):
                archive_col = IntColumn(primary_key=col.primary_key, nullable=col.nullable)
                archive_col._name = col_name
                ddl = self._adapt_ddl(archive_col.ddl_fragment(quote_fn=self.quote_identifier))
            else:
                ddl = self._adapt_ddl(col.ddl_fragment(quote_fn=self.quote_identifier))
            col_defs.append(f"  {self.quote_identifier(col_name)} {ddl}")

        archived_at_col = DateTimeColumn(nullable=False)
        archived_at_col._name = "archived_at"
        archived_at_ddl = self._adapt_ddl(archived_at_col.ddl_fragment(quote_fn=self.quote_identifier))
        col_defs.append(f"  {self.quote_identifier('archived_at')} {archived_at_ddl} NOT NULL")

        col_defs = self._post_process_col_defs(col_defs)
        quoted_table = self.quote_identifier(archive_table)
        sql = (
            f"CREATE TABLE {exists}{quoted_table} (\n"
            + ",\n".join(col_defs)
            + f"\n){self._table_suffix}"
        )
        await self._execute(sql, [])

    async def drop_table(
        self,
        model_cls: Any,
        *,
        if_exists: bool = True,
        cascade: bool = False,
    ) -> None:
        """
        DROP TABLE を実行する。

        :param cascade: True のとき ``CASCADE`` を付加する。PostgreSQL のみ有効。
        """
        meta = model_cls._meta
        exists = "IF EXISTS " if if_exists else ""
        cascade_sql = " CASCADE" if cascade else ""
        quoted_table = self.quote_identifier(meta.table_name)
        sql = f"DROP TABLE {exists}{quoted_table}{cascade_sql}"
        await self._execute(sql, [])

    async def truncate(self, model_cls: Any, *, restart_identity: bool = True) -> None:
        """
        テーブルの全行を削除し、シーケンス (AUTO INCREMENT) をリセットする。

        PostgreSQL では ``TRUNCATE TABLE ... RESTART IDENTITY``、
        MySQL では ``TRUNCATE TABLE`` を発行する。
        SQLite は TRUNCATE 非対応のため ``AioSQLiteEngine`` でオーバーライドする。
        """
        table = self.quote_identifier(model_cls._meta.table_name)
        restart = " RESTART IDENTITY" if restart_identity else ""
        await self._execute(f"TRUNCATE TABLE {table}{restart}", [])

    # ── サブクラスが上書きするプレースホルダー形式 ────────────

    def _placeholders(self, n: int) -> str:
        """INSERT の VALUES (...) 用プレースホルダー列。"""
        return ", ".join(self._param(i + 1) for i in range(n))

    def _param(self, n: int) -> str:
        """位置 n のバインドパラメータ記号。asyncpg=$1, sqlite=?"""
        return "%s"  # デフォルト: psycopg / MySQL 形式

    async def __aenter__(self) -> "Engine":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()


# ── asyncpg Engine ────────────────────────────────────────────

class AsyncpgEngine(Engine):
    """PostgreSQL 用 asyncpg ドライバ。コネクションプールを使用。"""

    def __init__(self, dsn: str, *, min_size: int = 2, max_size: int = 10) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

    def _param(self, n: int) -> str:
        return f"${n}"

    def quote_identifier(self, name: str) -> str:
        """PostgreSQL: ダブルクォートでテーブル名・カラム名を囲む"""
        return f'"{name}"'

    async def connect(self) -> None:
        import asyncpg  # type: ignore
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _raw_fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        conn = _tx_conn.get()
        if conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]

    async def _raw_execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            result = await conn.execute(sql, *params)
            match = re.search(r"\d+$", result)
            return int(match.group()) if match else 0
        async with self._pool.acquire() as conn:
            result = await conn.execute(sql, *params)
            match = re.search(r"\d+$", result)
            return int(match.group()) if match else 0

    async def _raw_fetchval(self, sql: str, params: list[Any]) -> Any:
        conn = _tx_conn.get()
        if conn:
            return await conn.fetchval(sql, *params)
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *params)

    async def _bulk_insert(self, model_cls: Any, instances: list) -> None:
        """asyncpg 最適化: multi-row INSERT ... RETURNING pk で全 PK を一括取得。"""
        if not instances:
            return
        meta = model_cls._meta
        pk_name = meta.pk_name
        is_auto = meta.is_auto_pk

        cols = (
            [name for name, col in meta.columns.items() if not col.primary_key]
            if is_auto
            else list(meta.columns.keys())
        )
        if not cols:
            return

        # auto_now_add など挿入時フックを全インスタンスに適用する
        for inst in instances:
            for name, col in meta.columns.items():
                if hasattr(col, "get_insert_value"):
                    new_val = col.get_insert_value(inst._data.get(name))
                    if new_val is not None:
                        inst._data[name] = new_val

        n_cols = len(cols)
        row_phs = [
            "(" + ", ".join(f"${i * n_cols + j + 1}" for j in range(n_cols)) + ")"
            for i in range(len(instances))
        ]
        all_params = [
            meta.columns[col_name].to_db(inst._data.get(col_name))
            for inst in instances
            for col_name in cols
        ]

        table = self.quote_identifier(meta.table_name)
        cols_quoted = [self.quote_identifier(c) for c in cols]
        if is_auto:
            sql = (
                f"INSERT INTO {table} ({', '.join(cols_quoted)})"
                f" VALUES {', '.join(row_phs)} RETURNING {self.quote_identifier(pk_name)}"
            )
            conn = _tx_conn.get()
            if conn:
                rows = await conn.fetch(sql, *all_params)
            else:
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(sql, *all_params)
            for inst, row in zip(instances, rows):
                inst._data[pk_name] = row[pk_name]
        else:
            sql = (
                f"INSERT INTO {table} ({', '.join(cols_quoted)})"
                f" VALUES {', '.join(row_phs)}"
            )
            conn = _tx_conn.get()
            if conn:
                await conn.execute(sql, *all_params)
            else:
                async with self._pool.acquire() as conn:
                    await conn.execute(sql, *all_params)

    @asynccontextmanager
    async def transaction(self):
        """asyncpg トランザクション。専用接続を ContextVar に保持する。"""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                token = _tx_conn.set(conn)
                try:
                    yield conn
                finally:
                    _tx_conn.reset(token)


# ── aiosqlite Engine ─────────────────────────────────────────

class AioSQLiteEngine(Engine):
    """SQLite 用 aiosqlite ドライバ。テスト/開発向け。"""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: Any = None

    def _param(self, n: int) -> str:
        return "?"

    def _placeholders(self, n: int) -> str:
        return ", ".join("?" for _ in range(n))

    def quote_identifier(self, name: str) -> str:
        """SQLite: 角括弧でテーブル名・カラム名を囲む"""
        return f"[{name}]"

    def _adapt_ddl(self, ddl: str) -> str:
        ddl = ddl.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        ddl = ddl.replace("DOUBLE PRECISION", "REAL")
        ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")
        ddl = ddl.replace("BOOLEAN", "INTEGER")
        ddl = re.sub(r"^DATE\b", "TEXT", ddl)
        ddl = re.sub(r"^TIME\b", "TEXT", ddl)
        return ddl

    def _current_timestamp_default(self) -> str:
        # SQLite は ALTER TABLE ADD COLUMN で CURRENT_TIMESTAMP が非定数扱いとなるため
        # リテラル文字列を使用する。epoch をフォールバック値とする。
        return "DEFAULT '1970-01-01 00:00:00'"

    async def connect(self) -> None:
        import aiosqlite  # type: ignore
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()

    async def _raw_fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        sql = self._normalize_sql(sql)
        async with self._conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description] if cursor.description else []
            return [dict(zip(cols, row)) for row in rows]

    async def _raw_execute(self, sql: str, params: list[Any]) -> int:
        sql = self._normalize_sql(sql)
        sql_exec = re.sub(r"\s+RETURNING\s+\w+", "", sql, flags=re.IGNORECASE)
        async with self._conn.execute(sql_exec, params) as cursor:
            if not _in_tx.get():
                await self._conn.commit()
            return cursor.rowcount if cursor.rowcount >= 0 else 0

    async def _raw_fetchval(self, sql: str, params: list[Any]) -> Any:
        """INSERT RETURNING id を SQLite の lastrowid で代替。"""
        sql_exec = self._normalize_sql(sql)
        has_returning = "RETURNING" in sql.upper()
        sql_exec = re.sub(r"\s+RETURNING\s+\w+", "", sql_exec, flags=re.IGNORECASE)
        async with self._conn.execute(sql_exec, params) as cursor:
            if has_returning:
                val = cursor.lastrowid
            else:
                row = await cursor.fetchone()
                val = row[0] if row else None
        # コンテキストを抜けた後にcommit
        if not _in_tx.get():
            await self._conn.commit()
        return val

    async def _bulk_insert(self, model_cls: Any, instances: list) -> None:
        """SQLite 最適化: 1回の multi-row INSERT にまとめる。"""
        if not instances:
            return
        meta = model_cls._meta
        pk_name = meta.pk_name
        is_auto = meta.is_auto_pk

        cols = (
            [name for name, col in meta.columns.items() if not col.primary_key]
            if is_auto
            else list(meta.columns.keys())
        )
        if not cols:
            return

        # SQLite のバインド変数上限 (999) を超えないよう分割
        max_rows = max(1, 999 // len(cols))

        # auto_now_add など挿入時フックを全インスタンスに適用する
        for inst in instances:
            for name, col in meta.columns.items():
                if hasattr(col, "get_insert_value"):
                    new_val = col.get_insert_value(inst._data.get(name))
                    if new_val is not None:
                        inst._data[name] = new_val

        for i in range(0, len(instances), max_rows):
            batch = instances[i : i + max_rows]
            all_params = [
                meta.columns[col_name].to_db(inst._data.get(col_name))
                for inst in batch
                for col_name in cols
            ]
            table = self.quote_identifier(meta.table_name)
            cols_quoted = [self.quote_identifier(c) for c in cols]
            row_ph = "(" + ", ".join("?" * len(cols)) + ")"
            sql = (
                f"INSERT INTO {table} ({', '.join(cols_quoted)})"
                f" VALUES {', '.join([row_ph] * len(batch))}"
            )
            async with self._conn.execute(sql, all_params) as cursor:
                if not _in_tx.get():
                    await self._conn.commit()
                last_id = cursor.lastrowid

            if is_auto:
                first_id = last_id - len(batch) + 1
                for j, inst in enumerate(batch):
                    inst._data[pk_name] = first_id + j

    async def _bulk_update(self, instances: list, fields: list[str] | None = None) -> None:
        """SQLite 最適化: executemany で一括 UPDATE する。"""
        if not instances:
            return
        meta = instances[0]._meta
        pk_name = meta.pk_name

        # auto_now など更新時フックを全インスタンスに適用する
        for inst in instances:
            for name, col in meta.columns.items():
                if hasattr(col, "get_update_value"):
                    inst._data[name] = col.get_update_value(inst._data.get(name))

        col_names = [
            name for name, col in meta.columns.items()
            if not col.primary_key and (
                fields is None
                or name in fields
                or getattr(col, "auto_now", False)
            )
        ]
        if not col_names:
            return
        set_clause = ", ".join(f"{self.quote_identifier(name)} = ?" for name in col_names)
        sql = (
            f"UPDATE {self.quote_identifier(meta.table_name)} "
            f"SET {set_clause} "
            f"WHERE {self.quote_identifier(pk_name)} = ?"
        )
        params_list = [
            [meta.columns[c].to_db(inst._data.get(c)) for c in col_names] + [inst._data[pk_name]]
            for inst in instances
        ]
        await self._conn.executemany(sql, params_list)
        if not _in_tx.get():
            await self._conn.commit()

    @asynccontextmanager
    async def transaction(self):
        """SQLite トランザクション。auto-commit を抑制し、終了時に commit/rollback。"""
        token = _in_tx.set(True)
        try:
            yield self
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        finally:
            _in_tx.reset(token)

    async def drop_table(
        self,
        model_cls: Any,
        *,
        if_exists: bool = True,
        cascade: bool = False,
    ) -> None:
        """SQLite 用: CASCADE は未サポートのため無視する。"""
        meta = model_cls._meta
        exists = "IF EXISTS " if if_exists else ""
        await self._execute(f"DROP TABLE {exists}{self.quote_identifier(meta.table_name)}", [])

    async def truncate(self, model_cls: Any, *, restart_identity: bool = True) -> None:
        """SQLite 用: DELETE FROM で全行削除し、sqlite_sequence でリセット。"""
        raw_name = model_cls._meta.table_name
        await self._execute(f"DELETE FROM {self.quote_identifier(raw_name)}", [])
        if restart_identity:
            try:
                # sqlite_sequence.name は非クォートの生テーブル名で格納されている
                await self._execute(
                    "DELETE FROM sqlite_sequence WHERE name = %s", [raw_name]
                )
            except Exception:
                pass

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        """%s プレースホルダーを ? に変換する。"""
        return sql.replace("%s", "?")


# ── aiomysql Engine ──────────────────────────────────────────

class AioMySQLEngine(Engine):
    """MySQL / MariaDB 用 aiomysql ドライバ。コネクションプールを使用。"""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        *,
        minsize: int = 2,
        maxsize: int = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._db = db
        self._minsize = minsize
        self._maxsize = maxsize
        self._pool: Any = None

    def _param(self, n: int) -> str:
        """MySQLは%sプレースホルダーを使用"""
        return "%s"

    def quote_identifier(self, name: str) -> str:
        """MySQL: バッククォートでテーブル名・カラム名を囲む"""
        return f"`{name}`"

    def _adapt_ddl(self, ddl: str) -> str:
        ddl = ddl.replace("SERIAL PRIMARY KEY", "INT AUTO_INCREMENT PRIMARY KEY")
        ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")
        return ddl

    @property
    def _table_suffix(self) -> str:
        return " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

    async def connect(self) -> None:
        import aiomysql  # type: ignore
        self._pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            db=self._db,
            minsize=self._minsize,
            maxsize=self._maxsize,
            autocommit=True,
            charset="utf8mb4",
        )

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    async def _raw_fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        import aiomysql  # type: ignore
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                return [{k.lower(): v for k, v in row.items()} for row in rows]
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                return [{k.lower(): v for k, v in row.items()} for row in rows]

    async def _insert(self, instance: Any) -> None:
        """MySQL 版: RETURNING 非対応のため lastrowid を使用。"""
        meta = instance._meta
        pk_name = meta.pk_name
        is_auto = meta.is_auto_pk

        # auto_now_add など挿入時フックを適用してから列を収集する
        for name, col in meta.columns.items():
            if hasattr(col, "get_insert_value"):
                new_val = col.get_insert_value(instance._data.get(name))
                if new_val is not None:
                    instance._data[name] = new_val

        cols = [c for c in meta.columns.keys() if instance._data.get(c) is not None or c == pk_name]
        if is_auto and pk_name in cols:
            cols.remove(pk_name)
        values = [meta.columns[c].to_db(instance._data[c]) for c in cols]
        placeholders = self._placeholders(len(cols))

        # MySQL: RETURNING 非対応のため RETURNING を除外
        table = self.quote_identifier(meta.table_name)
        cols_quoted = [self.quote_identifier(c) for c in cols]

        sql = (
            f"INSERT INTO {table} ({', '.join(cols_quoted)}) "
            f"VALUES ({placeholders})"
        )

        if is_auto:
            # MySQL では同じ接続内で lastrowid を取得する必要がある
            conn = _tx_conn.get()
            if conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, values)
                    new_pk = cur.lastrowid
            else:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(sql, values)
                        new_pk = cur.lastrowid
            instance._data[pk_name] = new_pk
        else:
            await self._execute(sql, values)

    async def _raw_execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount if cur.rowcount >= 0 else 0
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount if cur.rowcount >= 0 else 0

    async def _raw_fetchval(self, sql: str, params: list[Any]) -> Any:
        """INSERT RETURNING id を MySQL の lastrowid で代替。"""
        has_returning = "RETURNING" in sql.upper()
        sql_exec = re.sub(r"\s+RETURNING\s+\w+", "", sql, flags=re.IGNORECASE)
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql_exec, params)
                if has_returning:
                    return cur.lastrowid
                row = await cur.fetchone()
                return row[0] if row else None
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql_exec, params)
                if has_returning:
                    return cur.lastrowid
                row = await cur.fetchone()
                return row[0] if row else None

    @asynccontextmanager
    async def transaction(self):
        """aiomysql トランザクション。autocommit=False の専用接続を使う。"""
        async with self._pool.acquire() as conn:
            await conn.begin()
            token = _tx_conn.set(conn)
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
            finally:
                _tx_conn.reset(token)

    async def truncate(self, model_cls: Any, *, restart_identity: bool = True) -> None:
        """MySQL 用: TRUNCATE TABLE は常に AUTO_INCREMENT をリセットする。"""
        table = self.quote_identifier(model_cls._meta.table_name)
        await self._execute(f"TRUNCATE TABLE {table}", [])


# ── Psycopg3 Engine ───────────────────────────────────────────

class Psycopg3Engine(Engine):
    """PostgreSQL 用 psycopg3 ドライバ。"""

    def __init__(self, conninfo: str, *, min_size: int = 2, max_size: int = 10) -> None:
        self._conninfo = conninfo
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

    def _param(self, n: int) -> str:
        """psycopg3は$nプレースホルダーを使用"""
        return f"${n}"

    def quote_identifier(self, name: str) -> str:
        """PostgreSQL: ダブルクォートでテーブル名・カラム名を囲む"""
        return f'"{name}"'

    async def connect(self) -> None:
        import psycopg_pool  # type: ignore
        self._pool = psycopg_pool.AsyncConnectionPool(
            self._conninfo,
            min_size=self._min_size,
            max_size=self._max_size,
        )
        await self._pool.wait()

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _raw_fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                return [dict(zip(cols, row)) for row in rows]
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                return [dict(zip(cols, row)) for row in rows]

    async def _raw_execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount

    async def _raw_fetchval(self, sql: str, params: list[Any]) -> Any:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
                return row[0] if row else None
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
                return row[0] if row else None

    @asynccontextmanager
    async def transaction(self):
        """psycopg3 トランザクション。専用接続を ContextVar に保持する。"""
        async with self._pool.connection() as conn:
            async with conn.transaction():
                token = _tx_conn.set(conn)
                try:
                    yield conn
                finally:
                    _tx_conn.reset(token)


# ── ファクトリ関数 ────────────────────────────────────────────

async def _connect_impl(url: str, **kwargs: Any) -> Engine:
    """connect() の実装本体。直接呼ばず connect() 経由で使う。"""
    from kakaorm.model import Model

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if "asyncpg" in scheme:
        dsn = url.replace("postgresql+asyncpg://", "postgresql://")
        engine: Engine = AsyncpgEngine(dsn, **kwargs)

    elif "psycopg3" in scheme:
        conninfo = url.replace("postgresql+psycopg3://", "postgresql://")
        engine = Psycopg3Engine(conninfo, **kwargs)

    elif "aiosqlite" in scheme or "sqlite" in scheme:
        path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        engine = AioSQLiteEngine(path)

    elif "aiomysql" in scheme or scheme.startswith("mysql"):
        engine = AioMySQLEngine(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            db=parsed.path.lstrip("/"),
            **kwargs,
        )

    else:
        raise ValueError(f"Unsupported database URL: {url!r}")

    await engine.connect()
    _register_engine(Model, engine)
    return engine


class _ConnectAwaitable:
    """
    connect() が返すカスタム awaitable。

    ``await`` を付け忘れた場合に、Python 標準の
    ``RuntimeWarning: coroutine 'connect' was never awaited``
    より分かりやすいエラーメッセージを表示する。

    正しい使い方::

        engine = await kakaorm.connect(url)

    ``await`` なしで呼んだ場合、オブジェクトがガベージコレクトされる際に
    ``RuntimeWarning`` を発行して修正方法を案内する。
    """

    def __init__(self, url: str, kwargs: dict) -> None:
        self._url = url
        self._kwargs = kwargs
        self._awaited = False

    def __await__(self):
        self._awaited = True
        return _connect_impl(self._url, **self._kwargs).__await__()

    def __del__(self) -> None:
        if not self._awaited:
            import warnings
            warnings.warn(
                f"kakaorm.connect({self._url!r}) was called without `await` and had no effect.\n"
                "Fix: engine = await kakaorm.connect(url)",
                RuntimeWarning,
                stacklevel=2,
            )


def connect(url: str, **kwargs: Any) -> "_ConnectAwaitable":
    """
    接続 URL から適切な Engine を選択して初期化する。

    必ず ``await`` を付けて呼ぶこと::

        engine = await kakaorm.connect(url)

    ``await`` を省略した場合は、接続は行われず
    ``RuntimeWarning`` で修正方法が案内される。

    URL 形式:
        postgresql+asyncpg://user:pw@host/db
        postgresql+psycopg3://user:pw@host/db
        sqlite+aiosqlite:///./path/to/db.sqlite
        sqlite+aiosqlite:///:memory:
        mysql+aiomysql://user:pw@host:3306/db
    """
    return _ConnectAwaitable(url, kwargs)


def _register_engine(base_cls: Any, engine: Engine) -> None:
    """Model とすべてのサブクラスに engine を登録する。"""
    base_cls._engine = engine
    for sub in base_cls.__subclasses__():
        _register_engine(sub, engine)
