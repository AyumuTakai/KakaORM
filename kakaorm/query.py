"""
QuerySet — 遅延クエリビルダ
============================
await するまで SQL は実行されない。
メソッドチェーンで条件を積み上げ、最後に execute() / all() / first() を呼ぶ。

設計のポイント:
  - イミュータブルコピーを返す (元の QuerySet は変更しない)
  - SELECT / INSERT / UPDATE / DELETE を統一インターフェースで扱う
  - __await__ を実装し `await User.filter(...)` でもそのまま動く
"""

from __future__ import annotations

import copy
from typing import Any, AsyncIterator, Generic, Sequence, Type, TypeVar

from kakaorm.columns.base import WhereClause

T = TypeVar("T", bound="Model")  # type: ignore[type-arg]


class QuerySet(Generic[T]):
    """
    SQL クエリを段階的に構築し、await 時に実行する。

    例:
        qs = (
            User.filter(User.age >= 20)
                .filter(User.active == True)
                .order_by(User.name.asc)
                .limit(10)
                .offset(20)
        )
        users = await qs

        # SELECT のみ特定カラム
        rows = await User.all().select(User.name, User.email)

        # COUNT
        n = await User.filter(User.age >= 20).count()

        # 非同期イテレーション
        async for user in User.filter(User.active == True):
            print(user.name)
    """

    def __init__(self, model: Type[T]) -> None:
        self._model = model
        self._where: list[WhereClause] = []
        self._order_by: list[str] = []
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._select_cols: list[str] | None = None  # None = SELECT *

    def _clone(self) -> "QuerySet[T]":
        new = QuerySet(self._model)
        new._where = list(self._where)
        new._order_by = list(self._order_by)
        new._limit_val = self._limit_val
        new._offset_val = self._offset_val
        new._select_cols = copy.copy(self._select_cols)
        return new

    # ── クエリ条件の積み上げ ──────────────────────────────────

    def filter(self, clause: WhereClause) -> "QuerySet[T]":
        """WHERE 条件を追加 (複数は AND で結合)。"""
        qs = self._clone()
        qs._where.append(clause)
        return qs

    def exclude(self, clause: WhereClause) -> "QuerySet[T]":
        """NOT (clause) を追加。"""
        return self.filter(~clause)

    def order_by(self, *cols: str) -> "QuerySet[T]":
        """ORDER BY を指定。ColumnMeta.asc / .desc を渡す。"""
        qs = self._clone()
        qs._order_by = list(cols)
        return qs

    def limit(self, n: int) -> "QuerySet[T]":
        qs = self._clone()
        qs._limit_val = n
        return qs

    def offset(self, n: int) -> "QuerySet[T]":
        qs = self._clone()
        qs._offset_val = n
        return qs

    def select(self, *column_metas: Any) -> "QuerySet[T]":
        """取得カラムを絞り込む。ColumnMeta インスタンスを渡す。"""
        qs = self._clone()
        qs._select_cols = [cm._name for cm in column_metas]
        return qs

    # ── SQL 生成 ──────────────────────────────────────────────

    def _build_sql(self) -> tuple[str, list[Any]]:
        """SELECT 文と bind パラメータのタプルを返す。"""
        table = self._model._meta.table_name
        cols = "*" if not self._select_cols else ", ".join(self._select_cols)
        sql = f"SELECT {cols} FROM {table}"
        params: list[Any] = []

        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)

        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)

        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"

        if self._offset_val is not None:
            sql += f" OFFSET {self._offset_val}"

        return sql, params

    # ── 実行系 ────────────────────────────────────────────────

    async def execute(self) -> list[T]:
        """クエリを実行してモデルインスタンスのリストを返す。"""
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        sql, params = self._build_sql()
        rows = await engine._fetch(sql, params)
        return [self._model(**dict(row)) for row in rows]

    async def count(self) -> int:
        """COUNT(*) を実行して件数を返す。"""
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")
        table = self._model._meta.table_name
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        params: list[Any] = []
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)
        rows = await engine._fetch(sql, params)
        return rows[0]["cnt"] if rows else 0

    async def first(self) -> T | None:
        """最初の 1 件を返す。なければ None。"""
        results = await self.limit(1).execute()
        return results[0] if results else None

    async def last(self) -> T | None:
        """pk 降順で最初の 1 件を返す。"""
        results = await self.order_by("id DESC").limit(1).execute()
        return results[0] if results else None

    async def exists(self) -> bool:
        """条件に一致するレコードが 1 件以上あれば True。"""
        return await self.count() > 0

    async def delete(self) -> int:
        """条件に一致するレコードを一括 DELETE し削除件数を返す。"""
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")
        table = self._model._meta.table_name
        sql = f"DELETE FROM {table}"
        params: list[Any] = []
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)
        return await engine._execute(sql, params)

    async def update(self, **values: Any) -> int:
        """条件に一致するレコードを一括 UPDATE し更新件数を返す。"""
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")
        table = self._model._meta.table_name
        set_parts = [f"{k} = %s" for k in values]
        set_params = list(values.values())
        sql = f"UPDATE {table} SET {', '.join(set_parts)}"
        params: list[Any] = set_params
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)
        return await engine._execute(sql, params)

    # ── Python 組み込みプロトコル ─────────────────────────────

    def __await__(self):
        """
        `await User.filter(...)` のように直接 await できる。
        内部で execute() を呼ぶ。
        """
        return self.execute().__await__()

    async def __aiter__(self) -> AsyncIterator[T]:
        """
        `async for user in User.filter(...)` のように非同期イテレーションできる。
        大量データをバッファなしでストリーミングしたい場合に拡張可能。
        """
        results = await self.execute()
        for item in results:
            yield item

    def __repr__(self) -> str:
        sql, params = self._build_sql()
        return f"<QuerySet {sql!r} params={params}>"
