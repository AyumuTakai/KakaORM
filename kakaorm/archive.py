"""
ArchiveModel — アーカイブ削除をサポートするモデル基底クラス
============================================================

delete() を呼ぶと物理削除ではなく、archive_{table} テーブルへレコードを移動する。
SELECT はデフォルトでメインテーブルのみを対象にする。

アーカイブテーブルは自動的に生成される（engine.create_table() / autogenerate() 対応）:
  - メインテーブルと同じカラム構成
  - archived_at TIMESTAMP カラムが追加される
  - テーブル名: archive_{main_table}

使い方::

    class Log(ArchiveModel):
        body = StrColumn(nullable=False)

    log = await Log.create(body="hello")
    await log.delete()                             # アーカイブへ移動

    logs = await Log.all()                         # メインのみ
    logs = await Log.include_deleted().all()        # UNION ALL で全件
    logs = await Log.only_deleted()                # アーカイブのみ

    await log.restore()                            # アーカイブから復元
    await Log.only_deleted().purge()               # アーカイブから物理削除
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

from kakaorm.columns.base import WhereClause
from kakaorm.model import Model
from kakaorm.query import QuerySet

T = TypeVar("T", bound="ArchiveModel")

_EXCLUDE = "exclude"
_INCLUDE = "include"
_ONLY    = "only"

_ARCHIVE_PREFIX = "archive_"
_ARCHIVED_AT    = "archived_at"


class ArchiveQuerySet(QuerySet[T]):
    """
    アーカイブ削除対応 QuerySet。

    デフォルトはメインテーブルのみ。
    ``include_deleted()`` で UNION ALL、``only_deleted()`` でアーカイブのみ。
    """

    def __init__(self, model: Type[T]) -> None:
        super().__init__(model)
        self._deleted_filter: str = _EXCLUDE

    def _clone(self) -> "ArchiveQuerySet[T]":
        new = ArchiveQuerySet(self._model)
        new._where          = list(self._where)
        new._order_by       = list(self._order_by)
        new._limit_val      = self._limit_val
        new._offset_val     = self._offset_val
        new._select_cols    = copy.copy(self._select_cols)
        new._group_by       = list(self._group_by)
        new._having         = list(self._having)
        new._joins          = list(self._joins)
        new._ctes           = list(self._ctes)
        new._prefetch_names = list(self._prefetch_names)
        new._deleted_filter = self._deleted_filter
        return new

    def include_deleted(self) -> "ArchiveQuerySet[T]":
        """メインテーブルとアーカイブテーブルを UNION ALL で取得する。"""
        qs = self._clone()
        qs._deleted_filter = _INCLUDE
        return qs

    def only_deleted(self) -> "ArchiveQuerySet[T]":
        """アーカイブテーブルのみを対象にする。"""
        qs = self._clone()
        qs._deleted_filter = _ONLY
        return qs

    # ── テーブル名・カラムリストヘルパー ───────────────────────

    def _main_table(self) -> str:
        return self._model._meta.table_name

    def _archive_table(self) -> str:
        return f"{_ARCHIVE_PREFIX}{self._main_table()}"

    def _col_names(self) -> list[str]:
        """モデルのカラム名一覧（archived_at を除く）。"""
        return list(self._model._meta.columns.keys())

    def _explicit_col_sql(self, table: str) -> list[tuple[str, list[Any]]]:
        """table.col_name の SELECT 句リストを返す。"""
        engine = self._model._engine
        if engine:
            qt = engine.quote_identifier(table)
            return [
                (f"{qt}.{engine.quote_identifier(c)}", [])
                for c in self._col_names()
            ]
        return [(f"{table}.{c}", []) for c in self._col_names()]

    def _translate_where_for_archive(self) -> list[WhereClause]:
        """WHERE 句内のメインテーブル参照をアーカイブテーブルに置換する。

        WhereClause は生成時点では非クォート（例: event.id）のため、
        非クォート・クォート両方を置換する。
        """
        main = self._main_table()
        archive = self._archive_table()
        engine = self._model._engine
        result = []
        for clause in self._where:
            sql = clause.sql
            # 非クォート参照を置換（WhereClause の元の SQL）
            sql = sql.replace(main + ".", archive + ".")
            # クォート参照を置換（_quote_identifiers_in_where で変換済みの場合）
            if engine:
                q_main    = engine.quote_identifier(main)
                q_archive = engine.quote_identifier(archive)
                sql = sql.replace(q_main + ".", q_archive + ".")
            result.append(WhereClause(sql, list(clause.params)))
        return result

    def _quote_archive_where(self, sql: str) -> str:
        """アーカイブ WHERE 句内の非クォート参照をクォートする。"""
        engine = self._model._engine
        if not engine:
            return sql
        archive = self._archive_table()
        q_archive = engine.quote_identifier(archive)
        for col_name in self._col_names():
            unquoted = f"{archive}.{col_name}"
            quoted   = f"{q_archive}.{engine.quote_identifier(col_name)}"
            sql = sql.replace(unquoted, quoted)
        return sql

    def _build_archive_sql(
        self,
        *,
        with_pagination: bool = True,
    ) -> tuple[str, list[Any]]:
        """アーカイブテーブル用の SELECT SQL を構築する。

        with_pagination=False のとき LIMIT/OFFSET/ORDER BY を付与しない（UNION 用）。
        """
        archive = self._archive_table()
        engine  = self._model._engine
        q_archive = engine.quote_identifier(archive) if engine else archive

        col_parts = self._explicit_col_sql(archive)
        col_sql = ", ".join(c for c, _ in col_parts)

        sql = f"SELECT {col_sql} FROM {q_archive}"
        params: list[Any] = []

        # WHERE（メインテーブル参照をアーカイブに置換してクォート）
        archive_where = self._translate_where_for_archive()
        if archive_where:
            merged = archive_where[0]
            for c in archive_where[1:]:
                merged = merged & c
            where_sql = self._quote_archive_where(merged.sql)
            sql += f" WHERE {where_sql}"
            params.extend(merged.params)

        if with_pagination:
            if self._order_by:
                sql += " ORDER BY " + ", ".join(self._order_by)
            if self._limit_val is not None:
                sql += f" LIMIT {self._limit_val}"
            elif self._offset_val is not None:
                sql += " LIMIT -1"
            if self._offset_val is not None:
                sql += f" OFFSET {self._offset_val}"

        return sql, params

    def _build_main_explicit_sql(self) -> tuple[str, list[Any]]:
        """メインテーブルを明示的カラムリストで SELECT する SQL を構築する（UNION 用）。"""
        saved_select = self._select_cols
        self._select_cols = self._explicit_col_sql(self._main_table())
        try:
            return super()._build_sql()
        finally:
            self._select_cols = saved_select

    # ── 実行系 ────────────────────────────────────────────────

    def _hydrate_safe(self, row: dict) -> T:
        """archived_at など余分なカラムを除いてインスタンス化する。"""
        model_cols = set(self._model._meta.columns.keys())
        filtered = {k: v for k, v in row.items() if k in model_cols}
        columns = self._model._meta.columns
        converted = {k: columns[k].from_db(v) for k, v in filtered.items()}
        instance = self._model(**converted)
        instance._is_new = False
        return instance

    async def execute(self) -> list[Any]:
        if self._deleted_filter == _EXCLUDE:
            return await super().execute()

        if self._deleted_filter == _ONLY:
            sql, params = self._build_archive_sql()
            rows = await self._engine._fetch(sql, params)
            return [self._hydrate_safe(row) for row in rows]

        # _INCLUDE: UNION ALL
        # LIMIT/ORDER BY は UNION ALL の後に付ける必要があるため、
        # 各サブクエリからは除いて最終 SQL に追加する。
        saved_limit  = self._limit_val
        saved_offset = self._offset_val
        saved_order  = self._order_by
        self._limit_val  = None
        self._offset_val = None
        self._order_by   = []
        try:
            main_sql,    main_params    = self._build_main_explicit_sql()
            archive_sql, archive_params = self._build_archive_sql(with_pagination=False)
        finally:
            self._limit_val  = saved_limit
            self._offset_val = saved_offset
            self._order_by   = saved_order

        union_sql = f"{main_sql} UNION ALL {archive_sql}"
        if saved_order:
            union_sql += " ORDER BY " + ", ".join(saved_order)
        if saved_limit is not None:
            union_sql += f" LIMIT {saved_limit}"
        elif saved_offset is not None:
            union_sql += " LIMIT -1"
        if saved_offset is not None:
            union_sql += f" OFFSET {saved_offset}"

        union_params = main_params + archive_params
        rows = await self._engine._fetch(union_sql, union_params)
        return [self._hydrate_safe(row) for row in rows]

    async def count(self) -> int:
        if self._deleted_filter == _EXCLUDE:
            return await super().count()

        if self._deleted_filter == _ONLY:
            archive_sql, params = self._build_archive_sql()
            engine = self._engine
            sql = f"SELECT COUNT(*) AS cnt FROM ({archive_sql}) AS _sub"
            rows = await engine._fetch(sql, params)
            return rows[0]["cnt"] if rows else 0

        # _INCLUDE: main + archive
        main_count    = await super().count()
        archive_qs    = self._clone()
        archive_qs._deleted_filter = _ONLY
        archive_count = await archive_qs.count()
        return main_count + archive_count

    async def delete(self) -> int:
        """
        アーカイブ削除: マッチするレコードをアーカイブテーブルへ移動する。

        INSERT INTO archive_table SELECT ... FROM main WHERE ...
        の後に DELETE FROM main WHERE ... をトランザクションで実行。
        """
        main    = self._main_table()
        archive = self._archive_table()
        engine  = self._engine
        q_main    = engine.quote_identifier(main)
        q_archive = engine.quote_identifier(archive)
        q_archived_at = engine.quote_identifier(_ARCHIVED_AT)

        columns   = self._col_names()
        col_list  = ", ".join(engine.quote_identifier(c) for c in columns)
        src_cols  = ", ".join(
            f"{q_main}.{engine.quote_identifier(c)}" for c in columns
        )

        where_sql, where_params = self._merge_clauses(self._where, "WHERE")
        now = datetime.now(timezone.utc)

        insert_sql = (
            f"INSERT INTO {q_archive} ({col_list}, {q_archived_at}) "
            f"SELECT {src_cols}, %s FROM {q_main}{where_sql}"
        )
        delete_sql = f"DELETE FROM {q_main}{where_sql}"

        async with engine.transaction():
            count = await engine._execute(insert_sql, [now] + list(where_params))
            await engine._execute(delete_sql, list(where_params))

        return count

    async def restore(self) -> int:
        """
        アーカイブから復元: アーカイブテーブルのレコードをメインテーブルへ戻す。

        INSERT INTO main SELECT (model cols) FROM archive WHERE ...
        の後に DELETE FROM archive WHERE ... をトランザクションで実行。
        """
        main    = self._main_table()
        archive = self._archive_table()
        engine  = self._engine
        q_main    = engine.quote_identifier(main)
        q_archive = engine.quote_identifier(archive)

        columns  = self._col_names()
        col_list = ", ".join(engine.quote_identifier(c) for c in columns)
        src_cols = ", ".join(
            f"{q_archive}.{engine.quote_identifier(c)}" for c in columns
        )

        archive_where = self._translate_where_for_archive()
        where_sql, where_params = self._merge_clauses(archive_where, "WHERE")

        insert_sql = (
            f"INSERT INTO {q_main} ({col_list}) "
            f"SELECT {src_cols} FROM {q_archive}{where_sql}"
        )
        delete_sql = f"DELETE FROM {q_archive}{where_sql}"

        async with engine.transaction():
            count = await engine._execute(insert_sql, list(where_params))
            await engine._execute(delete_sql, list(where_params))

        return count

    async def purge(self) -> int:
        """アーカイブテーブルから物理削除する。"""
        archive = self._archive_table()
        engine  = self._engine
        q_archive = engine.quote_identifier(archive)

        archive_where = self._translate_where_for_archive()
        where_sql, where_params = self._merge_clauses(archive_where, "WHERE")
        sql = f"DELETE FROM {q_archive}{where_sql}"
        return await engine._execute(sql, list(where_params))


class ArchiveModel(Model):
    """
    アーカイブ削除をサポートするモデル基底クラス。

    ``delete()`` はレコードを archive_{table} テーブルへ移動する。
    ``restore()`` はアーカイブからメインテーブルへ戻す。

    アーカイブテーブルは ``engine.create_table()`` の代わりに
    ``engine.create_archive_table(Model)`` で作成するか、
    ``autogenerate()`` で自動管理する。
    """

    @classmethod
    def _archive_table_name(cls) -> str:
        """アーカイブテーブル名（"archive_{table}"）を返す。"""
        return f"{_ARCHIVE_PREFIX}{cls._meta.table_name}"

    # ── クラスメソッド: ArchiveQuerySet を返す ─────────────────

    @classmethod
    def all(cls: Type[T]) -> ArchiveQuerySet[T]:
        return ArchiveQuerySet(cls)

    @classmethod
    def where(cls: Type[T], *clauses: Any) -> ArchiveQuerySet[T]:
        qs = ArchiveQuerySet(cls)
        for c in clauses:
            qs = qs.where(c)
        return qs

    @classmethod
    def include_deleted(cls: Type[T]) -> ArchiveQuerySet[T]:
        """メインテーブルとアーカイブテーブルを UNION ALL で取得するクエリを開始する。"""
        return ArchiveQuerySet(cls).include_deleted()

    @classmethod
    def only_deleted(cls: Type[T]) -> ArchiveQuerySet[T]:
        """アーカイブテーブルのみを対象にしたクエリを開始する。"""
        return ArchiveQuerySet(cls).only_deleted()

    @classmethod
    async def get(cls: Type[T], *clauses: Any) -> T:
        qs = ArchiveQuerySet(cls)
        for c in clauses:
            qs = qs.where(c)
        results = await qs.limit(2).execute()
        if not results:
            raise cls.NotFound(f"{cls.__name__} not found")
        if len(results) > 1:
            raise cls.MultipleResults(f"Multiple {cls.__name__} found")
        return results[0]

    @classmethod
    async def first(cls: Type[T]) -> "T | None":
        return await ArchiveQuerySet(cls).first()

    @classmethod
    async def last(cls: Type[T]) -> "T | None":
        return await ArchiveQuerySet(cls).last()

    @classmethod
    async def get_or_none(cls: Type[T], *clauses: Any) -> "T | None":
        try:
            return await cls.get(*clauses)
        except cls.NotFound:
            return None

    # ── インスタンスメソッド ──────────────────────────────────

    async def delete(self) -> None:
        """アーカイブ削除: レコードをアーカイブテーブルへ移動する。"""
        if self._engine is None:
            raise RuntimeError("No engine connected.")
        pk_name = self._meta.pk_name
        pk_val  = self._data.get(pk_name)
        if pk_val is None:
            raise ValueError("Cannot delete an unsaved model instance.")
        await self.before_delete()
        pk_col = getattr(type(self), pk_name)
        await type(self).where(pk_col == pk_val).delete()
        await self.after_delete()

    async def restore(self) -> None:
        """アーカイブから復元する。"""
        if self._engine is None:
            raise RuntimeError("No engine connected.")
        pk_name = self._meta.pk_name
        pk_val  = self._data.get(pk_name)
        if pk_val is None:
            raise ValueError("Cannot restore an unsaved model instance.")
        archive = self._archive_table_name()
        engine  = self._engine
        pk_col  = getattr(type(self), pk_name)
        # ArchiveQuerySet の only_deleted().where(pk) を使って復元
        await type(self).only_deleted().where(pk_col == pk_val).restore()
