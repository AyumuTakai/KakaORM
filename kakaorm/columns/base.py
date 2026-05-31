"""
Column 基底クラス
=================
  Pythonの演算子を上書きすることで、文字列マジックなしに
  型安全なクエリ条件を構築できる。

  例:
    User.age >= 20          → WhereClause("age >= %s", [20])
    User.name == "Alice"    → WhereClause("name = %s", ["Alice"])
    User.name.like("A%")    → WhereClause("name LIKE %s", ["A%"])
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Generic, Sequence, TypeVar, overload

T = TypeVar("T")


@dataclass
class WhereClause:
    """SQL WHERE句のフラグメント。複数を AND/OR で結合できる。"""
    sql: str
    params: list[Any] = field(default_factory=list)

    def __and__(self, other: "WhereClause") -> "WhereClause":
        return WhereClause(
            f"({self.sql}) AND ({other.sql})",
            self.params + other.params,
        )

    def __or__(self, other: "WhereClause") -> "WhereClause":
        return WhereClause(
            f"({self.sql}) OR ({other.sql})",
            self.params + other.params,
        )

    def __invert__(self) -> "WhereClause":
        return WhereClause(f"NOT ({self.sql})", self.params)


class ColumnMeta:
    """
    クラス変数として宣言されたカラムの識別子。
    クエリ構築時にテーブル名・カラム名を保持する。

    モデルクラスのメタクラスが __set_name__ で自動的に名前を注入する。
    """

    def __init__(self, column: "Column") -> None:
        self._column = column
        self._name: str = ""
        self._table: str = ""

    def __set_name__(self, owner: Any, name: str) -> None:
        self._name = name
        self._column._name = name

    def _qualified(self) -> str:
        if self._table:
            return f"{self._table}.{self._name}"
        return self._name

    # ── 比較演算子 ────────────────────────────────────────────
    def __eq__(self, other: Any) -> WhereClause:          # type: ignore[override]
        if other is None:
            return WhereClause(f"{self._qualified()} IS NULL")
        return WhereClause(f"{self._qualified()} = %s", [other])

    def __ne__(self, other: Any) -> WhereClause:          # type: ignore[override]
        if other is None:
            return WhereClause(f"{self._qualified()} IS NOT NULL")
        return WhereClause(f"{self._qualified()} != %s", [other])

    def __lt__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} < %s", [other])

    def __le__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} <= %s", [other])

    def __gt__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} > %s", [other])

    def __ge__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} >= %s", [other])

    # ── 追加クエリメソッド ────────────────────────────────────
    def like(self, pattern: str) -> WhereClause:
        return WhereClause(f"{self._qualified()} LIKE %s", [pattern])

    def ilike(self, pattern: str) -> WhereClause:
        return WhereClause(f"{self._qualified()} ILIKE %s", [pattern])

    def in_(self, values: Sequence[Any]) -> WhereClause:
        placeholders = ", ".join(["%s"] * len(values))
        return WhereClause(f"{self._qualified()} IN ({placeholders})", list(values))

    def not_in(self, values: Sequence[Any]) -> WhereClause:
        placeholders = ", ".join(["%s"] * len(values))
        return WhereClause(f"{self._qualified()} NOT IN ({placeholders})", list(values))

    def is_null(self) -> WhereClause:
        return WhereClause(f"{self._qualified()} IS NULL")

    def is_not_null(self) -> WhereClause:
        return WhereClause(f"{self._qualified()} IS NOT NULL")

    def between(self, low: Any, high: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} BETWEEN %s AND %s", [low, high])

    @property
    def asc(self) -> str:
        return f"{self._qualified()} ASC"

    @property
    def desc(self) -> str:
        return f"{self._qualified()} DESC"

    def __repr__(self) -> str:
        return f"<ColumnMeta {self._qualified()!r}>"


class Column(Generic[T]):
    """
    モデルフィールドの基底クラス。
    Generic[T] により型チェッカーがインスタンスアクセス時の戻り値型を推論できる。

    クラスアクセス (Model.field)    → ColumnMeta (クエリ構築用)
    インスタンスアクセス (obj.field) → T          (実際の値)
    """

    # サブクラスが上書きする SQL 型文字列
    sql_type: str = "TEXT"

    def __init__(
        self,
        *,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
        unique: bool = False,
        index: bool = False,
    ) -> None:
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.index = index
        self._name: str = ""

    # ── デスクリプタプロトコル ────────────────────────────────
    # 実行時はメタクラスが ColumnMeta に差し替え / Model.__getattribute__ が
    # _data から値を返すため、これらのメソッドは呼ばれない。
    # 型チェッカー向けのオーバーロードとして宣言する。

    @overload
    def __get__(self, obj: None, objtype: type) -> ColumnMeta: ...
    @overload
    def __get__(self, obj: Any, objtype: type) -> T: ...
    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return ColumnMeta(self)
        return getattr(obj, "_data", {}).get(self._name)

    def __set__(self, obj: Any, value: T) -> None:
        obj._data[self._name] = value

    # ── DDL ──────────────────────────────────────────────────

    def ddl_fragment(self) -> str:
        """CREATE TABLE 用の列定義文字列を返す。"""
        parts = [self.sql_type]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self._name!r}>"
