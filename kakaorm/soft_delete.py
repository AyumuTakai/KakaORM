"""
SoftDeleteModel — 論理削除をサポートするモデル基底クラス
=========================================================

delete() を呼ぶと物理削除ではなく deleted_at に現在時刻をセットする。
SELECT は デフォルトで deleted_at IS NULL のみ対象にする。

使い方::

    class User(SoftDeleteModel):
        name = StrColumn(nullable=False)

    user = await User.create(name="Alice")
    await user.delete()                           # 論理削除

    users = await User.all()                      # 削除済みを除外
    users = await User.include_deleted().all()    # 削除済みも含む
    users = await User.only_deleted().all()       # 削除済みのみ

    await user.restore()                          # 論理削除を取り消す
    await User.where(...).purge()                 # 物理削除
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

from kakaorm.columns.base import WhereClause
from kakaorm.columns.types import DateTimeColumn
from kakaorm.model import Model
from kakaorm.query import QuerySet

T = TypeVar("T", bound="SoftDeleteModel")

_EXCLUDE = "exclude"
_INCLUDE = "include"
_ONLY    = "only"


class SoftDeleteQuerySet(QuerySet[T]):
    """
    論理削除対応 QuerySet。

    デフォルトで ``deleted_at IS NULL`` を WHERE に自動付与する。
    ``include_deleted()`` / ``only_deleted()`` で挙動を変更できる。
    """

    def __init__(self, model: Type[T]) -> None:
        super().__init__(model)
        self._deleted_filter: str = _EXCLUDE

    def _clone(self) -> "SoftDeleteQuerySet[T]":
        new = SoftDeleteQuerySet(self._model)
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

    def include_deleted(self) -> "SoftDeleteQuerySet[T]":
        """削除済みレコードも含めて取得する。"""
        qs = self._clone()
        qs._deleted_filter = _INCLUDE
        return qs

    def only_deleted(self) -> "SoftDeleteQuerySet[T]":
        """削除済みレコードのみを対象にする。"""
        qs = self._clone()
        qs._deleted_filter = _ONLY
        return qs

    def _soft_delete_clauses(self) -> list[WhereClause]:
        """_deleted_filter に応じた追加 WHERE 句を返す。"""
        table = self._model._meta.table_name
        if self._deleted_filter == _EXCLUDE:
            return [WhereClause(f"{table}.deleted_at IS NULL", [])]
        if self._deleted_filter == _ONLY:
            return [WhereClause(f"{table}.deleted_at IS NOT NULL", [])]
        return []

    def _build_sql(self) -> tuple[str, list[Any]]:
        extra = self._soft_delete_clauses()
        saved = self._where
        self._where = extra + list(saved)
        try:
            return super()._build_sql()
        finally:
            self._where = saved

    async def count(self) -> int:
        extra = self._soft_delete_clauses()
        saved = self._where
        self._where = extra + list(saved)
        try:
            return await super().count()
        finally:
            self._where = saved

    async def aggregate(self, **agg_exprs: Any) -> dict[str, Any]:
        extra = self._soft_delete_clauses()
        saved = self._where
        self._where = extra + list(saved)
        try:
            return await super().aggregate(**agg_exprs)
        finally:
            self._where = saved

    async def update(self, **values: Any) -> int:
        extra = self._soft_delete_clauses()
        saved = self._where
        self._where = extra + list(saved)
        try:
            return await super().update(**values)
        finally:
            self._where = saved

    async def delete(self) -> int:
        """論理削除: マッチするレコードの deleted_at に現在時刻をセット。"""
        return await self.update(deleted_at=datetime.now(timezone.utc))

    async def restore(self) -> int:
        """論理削除を取り消す: deleted_at を NULL に戻す。"""
        saved = self._deleted_filter
        self._deleted_filter = _ONLY
        try:
            return await self.update(deleted_at=None)
        finally:
            self._deleted_filter = saved

    async def purge(self) -> int:
        """物理削除: マッチするレコードを DB から完全に削除する。"""
        extra = self._soft_delete_clauses()
        saved = self._where
        self._where = extra + list(saved)
        try:
            return await super().delete()
        finally:
            self._where = saved


class SoftDeleteModel(Model):
    """
    論理削除をサポートするモデル基底クラス。

    サブクラスは自動的に ``deleted_at TIMESTAMP WITH TIME ZONE`` カラムを持つ。
    ``delete()`` は物理削除ではなく ``deleted_at`` をセットする。
    ``restore()`` で論理削除を取り消せる。

    QuerySet エントリポイント（``all()`` / ``where()`` / ``get()`` 等）は
    デフォルトで ``deleted_at IS NULL`` フィルタを自動付与する。
    """

    deleted_at = DateTimeColumn(nullable=True)

    # ── クラスメソッド: SoftDeleteQuerySet を返す ──────────────

    @classmethod
    def all(cls: Type[T]) -> SoftDeleteQuerySet[T]:
        return SoftDeleteQuerySet(cls)

    @classmethod
    def where(cls: Type[T], *clauses: Any) -> SoftDeleteQuerySet[T]:
        qs = SoftDeleteQuerySet(cls)
        for c in clauses:
            qs = qs.where(c)
        return qs

    @classmethod
    def include_deleted(cls: Type[T]) -> SoftDeleteQuerySet[T]:
        """削除済みレコードも含めたクエリを開始する。"""
        return SoftDeleteQuerySet(cls).include_deleted()

    @classmethod
    def only_deleted(cls: Type[T]) -> SoftDeleteQuerySet[T]:
        """削除済みレコードのみを対象にしたクエリを開始する。"""
        return SoftDeleteQuerySet(cls).only_deleted()

    @classmethod
    async def get(cls: Type[T], *clauses: Any) -> T:
        qs = SoftDeleteQuerySet(cls)
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
        return await SoftDeleteQuerySet(cls).first()

    @classmethod
    async def last(cls: Type[T]) -> "T | None":
        return await SoftDeleteQuerySet(cls).last()

    @classmethod
    async def get_or_none(cls: Type[T], *clauses: Any) -> "T | None":
        try:
            return await cls.get(*clauses)
        except cls.NotFound:
            return None

    # ── インスタンスメソッド ──────────────────────────────────

    async def delete(self) -> None:
        """論理削除: deleted_at に現在時刻をセット。"""
        if self._engine is None:
            raise RuntimeError("No engine connected.")
        pk_name = self._meta.pk_name
        pk_val = self._data.get(pk_name)
        if pk_val is None:
            raise ValueError("Cannot delete an unsaved model instance.")
        await self.before_delete()
        now = datetime.now(timezone.utc)
        pk_col = getattr(type(self), pk_name)
        await type(self).include_deleted().where(pk_col == pk_val).update(deleted_at=now)
        self._data["deleted_at"] = now
        await self.after_delete()

    async def restore(self) -> None:
        """論理削除を取り消す: deleted_at を NULL に戻す。"""
        if self._engine is None:
            raise RuntimeError("No engine connected.")
        pk_name = self._meta.pk_name
        pk_val = self._data.get(pk_name)
        if pk_val is None:
            raise ValueError("Cannot restore an unsaved model instance.")
        pk_col = getattr(type(self), pk_name)
        await type(self).only_deleted().where(pk_col == pk_val).update(deleted_at=None)
        self._data["deleted_at"] = None
