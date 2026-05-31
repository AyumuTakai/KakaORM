"""
具体的なカラム型
================
各クラスは sql_type を宣言し、必要に応じて
バリデーションや Python<->DB 型変換を追加できる。
"""

from __future__ import annotations
import datetime
from datetime import datetime as _datetime
from decimal import Decimal
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


class DateTimeColumn(Column[_datetime]):
    sql_type = "TIMESTAMP WITH TIME ZONE"

    def __init__(self, *, auto_now: bool = False, auto_now_add: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def get_insert_value(self, value: Any) -> Any:
        """INSERT 時に auto_now_add なら現在時刻を差し込む。"""
        if self.auto_now_add and value is None:
            return _datetime.utcnow()
        return value

    def get_update_value(self, value: Any) -> Any:
        """UPDATE 時に auto_now なら現在時刻を差し込む。"""
        if self.auto_now:
            return _datetime.utcnow()
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


class DecimalColumn(Column[Decimal]):
    """NUMERIC(max_digits, decimal_places) 型。浮動小数点誤差なし。"""
    sql_type = "NUMERIC"

    def __init__(self, max_digits: int, decimal_places: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def from_db(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    def to_db(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(str(value)))

    def ddl_fragment(self) -> str:
        parts = [f"NUMERIC({self.max_digits},{self.decimal_places})"]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        return " ".join(parts)


class DateColumn(Column[datetime.date]):
    """DATE 型。時刻なし。"""
    sql_type = "DATE"

    def from_db(self, value: Any) -> datetime.date | None:
        if value is None:
            return None
        if isinstance(value, datetime.date) and not isinstance(value, _datetime):
            return value
        if isinstance(value, _datetime):
            return value.date()
        return _datetime.fromisoformat(str(value)).date()

    def to_db(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime.date):
            return value.isoformat()
        return str(value)


class TimeColumn(Column[datetime.time]):
    """TIME 型。日付なし。"""
    sql_type = "TIME"

    def from_db(self, value: Any) -> datetime.time | None:
        if value is None:
            return None
        if isinstance(value, datetime.time):
            return value
        return _datetime.fromisoformat(f"2000-01-01T{value}").time()

    def to_db(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime.time):
            return value.isoformat()
        return str(value)
