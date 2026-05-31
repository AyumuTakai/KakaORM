"""
Engine — DB ドライバ抽象化
===========================
asyncpg / psycopg3 / aiosqlite のどれを使っても同じ API で動く。

設計:
  - Engine は抽象基底クラス
  - 各ドライバの具体クラス (AsyncpgEngine, Psycopg3Engine, AioSQLiteEngine) が実装
  - connect() がURL をパースして適切な Engine を返し、すべての Model に登録
  - コネクションプールを内部管理する

使い方:
    engine = await kakaorm.connect("postgresql+asyncpg://user:pw@localhost/db")
    engine = await kakaorm.connect("sqlite+aiosqlite:///./dev.db")
    engine = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
"""

from __future__ import annotations

import contextvars
import re
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Type
from urllib.parse import urlparse

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

    @abstractmethod
    async def connect(self) -> None:
        """コネクション (プール) を初期化する。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """コネクション (プール) を閉じる。"""

    @abstractmethod
    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        """SELECT 結果を dict のリストで返す。"""

    @abstractmethod
    async def _execute(self, sql: str, params: list[Any]) -> int:
        """INSERT/UPDATE/DELETE を実行し影響行数を返す。"""

    @abstractmethod
    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
        """スカラー値を 1 つ返す (COUNT など)。"""

    @asynccontextmanager
    async def transaction(self):
        """
        トランザクションを開始するコンテキストマネージャ。
        正常終了でコミット、例外発生でロールバックする。

        使い方::

            async with engine.transaction():
                await Order.create(...)
                await Stock.filter(...).update(qty=Stock.qty - 1)
                # 例外があれば自動ロールバック

        サブクラスでオーバーライドして実装する。
        """
        raise NotImplementedError(f"{type(self).__name__} は transaction() を実装していません")
        yield  # asynccontextmanager として認識させるために必要

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
        # 最初の行の最初のカラム値を返す
        return next(iter(rows[0].values()))

    # ── ORM 内部から呼ばれる操作 ─────────────────────────────

    async def _insert(self, instance: Any) -> None:
        """Model インスタンスを INSERT し、生成された id を書き戻す。"""
        meta = instance._meta
        cols = [
            name for name, col in meta.columns.items()
            if not col.primary_key and instance._data.get(name) is not None
        ]
        values = [instance._data[c] for c in cols]
        placeholders = self._placeholders(len(cols))
        sql = (
            f"INSERT INTO {meta.table_name} ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"RETURNING id"
        )
        new_id = await self._fetchval(sql, values)
        instance._data["id"] = new_id

    async def _update(self, instance: Any) -> None:
        """Model インスタンスを UPDATE する。"""
        meta = instance._meta
        col_names = [
            name for name, col in meta.columns.items()
            if not col.primary_key
        ]
        values = [instance._data.get(c) for c in col_names]
        set_clause = ", ".join(
            f"{name} = {self._param(i + 1)}" for i, name in enumerate(col_names)
        )
        pk_placeholder = self._param(len(col_names) + 1)
        sql = (
            f"UPDATE {meta.table_name} "
            f"SET {set_clause} "
            f"WHERE id = {pk_placeholder}"
        )
        await self._execute(sql, values + [instance._data["id"]])

    async def _delete(self, model_cls: Any, pk: Any) -> None:
        """primary key で 1 件 DELETE する。"""
        meta = model_cls._meta
        pk_placeholder = self._param(1)
        sql = f"DELETE FROM {meta.table_name} WHERE id = {pk_placeholder}"
        await self._execute(sql, [pk])

    async def create_table(self, model_cls: Any, *, if_not_exists: bool = True) -> None:
        """モデルクラスから CREATE TABLE 文を生成して実行する。"""
        meta = model_cls._meta
        exists = "IF NOT EXISTS " if if_not_exists else ""
        col_defs = []
        for col_name, col in meta.columns.items():
            col_defs.append(f"  {col_name} {col.ddl_fragment()}")
        sql = (
            f"CREATE TABLE {exists}{meta.table_name} (\n"
            + ",\n".join(col_defs)
            + "\n)"
        )
        await self._execute(sql, [])

    async def drop_table(self, model_cls: Any, *, if_exists: bool = True) -> None:
        """DROP TABLE を実行する。"""
        meta = model_cls._meta
        exists = "IF EXISTS " if if_exists else ""
        sql = f"DROP TABLE {exists}{meta.table_name}"
        await self._execute(sql, [])

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
        return f"${n}"  # asyncpg は $1, $2, ... 形式

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

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        conn = _tx_conn.get()
        if conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]

    async def _execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            result = await conn.execute(sql, *params)
            match = re.search(r"\d+$", result)
            return int(match.group()) if match else 0
        async with self._pool.acquire() as conn:
            result = await conn.execute(sql, *params)
            match = re.search(r"\d+$", result)
            return int(match.group()) if match else 0

    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
        conn = _tx_conn.get()
        if conn:
            return await conn.fetchval(sql, *params)
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *params)

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
        return "?"  # SQLite は ? 形式

    def _placeholders(self, n: int) -> str:
        return ", ".join("?" for _ in range(n))

    async def connect(self) -> None:
        import aiosqlite  # type: ignore
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        # プレースホルダーを ? に変換 (%s → ?)
        sql = self._normalize_sql(sql)
        async with self._conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description] if cursor.description else []
            return [dict(zip(cols, row)) for row in rows]

    async def _execute(self, sql: str, params: list[Any]) -> int:
        sql = self._normalize_sql(sql)
        sql_exec = re.sub(r"\s+RETURNING\s+\w+", "", sql, flags=re.IGNORECASE)
        async with self._conn.execute(sql_exec, params) as cursor:
            # トランザクション中は commit を抑制する
            if not _in_tx.get():
                await self._conn.commit()
            return cursor.rowcount if cursor.rowcount >= 0 else 0

    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
        """INSERT RETURNING id を SQLite の lastrowid で代替。"""
        sql_exec = self._normalize_sql(sql)
        has_returning = "RETURNING" in sql.upper()
        sql_exec = re.sub(r"\s+RETURNING\s+\w+", "", sql_exec, flags=re.IGNORECASE)
        async with self._conn.execute(sql_exec, params) as cursor:
            if not _in_tx.get():
                await self._conn.commit()
            if has_returning:
                return cursor.lastrowid
            row = await cursor.fetchone()
            return row[0] if row else None

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

    async def create_table(self, model_cls: Any, *, if_not_exists: bool = True) -> None:
        """SQLite 用: SERIAL → INTEGER PRIMARY KEY AUTOINCREMENT"""
        meta = model_cls._meta
        exists = "IF NOT EXISTS " if if_not_exists else ""
        col_defs = []
        for col_name, col in meta.columns.items():
            ddl = col.ddl_fragment()
            # asyncpg の SERIAL を SQLite 形式に変換
            ddl = ddl.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
            # PostgreSQL の型を SQLite 互換に変換
            ddl = ddl.replace("DOUBLE PRECISION", "REAL")
            ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "TEXT")
            ddl = ddl.replace("BOOLEAN", "INTEGER")
            col_defs.append(f"  {col_name} {ddl}")
        # REFERENCES 句を除去 (SQLite は FK 制約が複雑)
        col_defs_clean = [re.sub(r"\s+REFERENCES\s+\w+\(\w+\).*", "", d) for d in col_defs]
        sql = (
            f"CREATE TABLE {exists}{meta.table_name} (\n"
            + ",\n".join(col_defs_clean)
            + "\n)"
        )
        await self._execute(sql, [])

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
        return "%s"  # MySQL も %s 形式

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

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
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

    async def _execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount if cur.rowcount >= 0 else 0
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount if cur.rowcount >= 0 else 0

    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
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

    async def create_table(self, model_cls: Any, *, if_not_exists: bool = True) -> None:
        """MySQL 用: SERIAL → INT AUTO_INCREMENT、TIMESTAMP WITH TIME ZONE → DATETIME"""
        meta = model_cls._meta
        exists = "IF NOT EXISTS " if if_not_exists else ""
        col_defs = []
        for col_name, col in meta.columns.items():
            ddl = col.ddl_fragment()
            ddl = ddl.replace("SERIAL PRIMARY KEY", "INT AUTO_INCREMENT PRIMARY KEY")
            ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")
            col_defs.append(f"  {col_name} {ddl}")
        sql = (
            f"CREATE TABLE {exists}{meta.table_name} (\n"
            + ",\n".join(col_defs)
            + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        await self._execute(sql, [])


# ── Psycopg3 Engine ───────────────────────────────────────────

class Psycopg3Engine(Engine):
    """PostgreSQL 用 psycopg3 ドライバ。"""

    def __init__(self, conninfo: str, *, min_size: int = 2, max_size: int = 10) -> None:
        self._conninfo = conninfo
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

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

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
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

    async def _execute(self, sql: str, params: list[Any]) -> int:
        conn = _tx_conn.get()
        if conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount

    async def _fetchval(self, sql: str, params: list[Any]) -> Any:
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

async def connect(url: str, **kwargs: Any) -> Engine:
    """
    接続 URL から適切な Engine を選択して初期化する。

    URL 形式:
        postgresql+asyncpg://user:pw@host/db
        postgresql+psycopg3://user:pw@host/db
        sqlite+aiosqlite:///./path/to/db.sqlite
        sqlite+aiosqlite:///:memory:
        mysql+aiomysql://user:pw@host:3306/db
        mysql+aiomysql://user:pw@host/db
    """
    from kakaorm.model import Model

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if "asyncpg" in scheme:
        # postgresql+asyncpg:// → postgresql://
        dsn = url.replace("postgresql+asyncpg://", "postgresql://")
        engine = AsyncpgEngine(dsn, **kwargs)

    elif "psycopg3" in scheme:
        conninfo = url.replace("postgresql+psycopg3://", "postgresql://")
        engine = Psycopg3Engine(conninfo, **kwargs)

    elif "aiosqlite" in scheme or "sqlite" in scheme:
        # sqlite+aiosqlite:///./path → ./path
        path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        engine = AioSQLiteEngine(path)

    elif "aiomysql" in scheme or scheme.startswith("mysql"):
        # mysql+aiomysql://user:pw@host:3306/db
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

    # すべての Model サブクラスにエンジンを登録
    _register_engine(Model, engine)

    return engine


def _register_engine(base_cls: Any, engine: Engine) -> None:
    """Model とすべてのサブクラスに engine を登録する。"""
    base_cls._engine = engine
    for sub in base_cls.__subclasses__():
        _register_engine(sub, engine)


# ── 公開 API ──────────────────────────────────────────────────
from kakaorm.model import Model  # noqa: E402
from kakaorm.columns.types import (  # noqa: E402
    IntColumn,
    StrColumn,
    FloatColumn,
    BoolColumn,
    DateTimeColumn,
    ForeignKey,
)
from kakaorm.columns.base import (  # noqa: E402
    AggFunc,
    Count,
    Sum,
    Avg,
    Max,
    Min,
)

__all__ = [
    # Engine
    "Engine",
    "AsyncpgEngine",
    "AioSQLiteEngine",
    "AioMySQLEngine",
    "Psycopg3Engine",
    "connect",
    # Model
    "Model",
    # Column types
    "IntColumn",
    "StrColumn",
    "FloatColumn",
    "BoolColumn",
    "DateTimeColumn",
    "ForeignKey",
    # Aggregate functions
    "AggFunc",
    "Count",
    "Sum",
    "Avg",
    "Max",
    "Min",
]
