"""
具体的なカラム型
================
各クラスは sql_type を宣言し、必要に応じて
バリデーションや Python<->DB 型変換を追加できる。
"""

from __future__ import annotations
from datetime import datetime
from typing import Any

from kakaorm.columns.base import Column


class IntColumn(Column[int]):
    sql_type = "INTEGER"

    def __init__(self, *, auto_increment: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.auto_increment = auto_increment

    def ddl_fragment(self) -> str:
        if self.auto_increment and self.primary_key:
            # PostgreSQL: SERIAL / SQLite: INTEGER PRIMARY KEY AUTOINCREMENT
            return "SERIAL PRIMARY KEY"
        return super().ddl_fragment()


class StrColumn(Column[str]):
    sql_type = "TEXT"

    def __init__(self, *, max_length: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_length = max_length

    def ddl_fragment(self) -> str:
        if self.max_length:
            self.sql_type = f"VARCHAR({self.max_length})"
        return super().ddl_fragment()


class FloatColumn(Column[float]):
    sql_type = "DOUBLE PRECISION"


class BoolColumn(Column[bool]):
    sql_type = "BOOLEAN"


class DateTimeColumn(Column[datetime]):
    sql_type = "TIMESTAMP WITH TIME ZONE"

    def __init__(self, *, auto_now: bool = False, auto_now_add: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def get_insert_value(self, value: Any) -> Any:
        """INSERT 時に auto_now_add なら現在時刻を差し込む。"""
        if self.auto_now_add and value is None:
            return datetime.utcnow()
        return value

    def get_update_value(self, value: Any) -> Any:
        """UPDATE 時に auto_now なら現在時刻を差し込む。"""
        if self.auto_now:
            return datetime.utcnow()
        return value


class ForeignKey(Column[int]):
    """
    外部キーカラム。
    related_model は文字列 (遅延解決) または Model クラスを受け取る。
    """

    sql_type = "INTEGER"

    def __init__(self, related_model: Any, *, on_delete: str = "CASCADE", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._related_model = related_model
        self.on_delete = on_delete

    def ddl_fragment(self) -> str:
        base = super().ddl_fragment()
        table = self._resolve_table()
        return f"{base} REFERENCES {table}(id) ON DELETE {self.on_delete}"

    def _resolve_table(self) -> str:
        if isinstance(self._related_model, str):
            return self._related_model.lower()
        # Model クラスが渡された場合
        return getattr(self._related_model, "_meta", None) and \
               self._related_model._meta.table_name or \
               self._related_model.__name__.lower()
