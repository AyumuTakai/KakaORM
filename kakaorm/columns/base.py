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


# ── 集計関数 ──────────────────────────────────────────────────

class AggFunc:
    """
    SUM / AVG / MAX / MIN / COUNT などの集計関数式。
    select() や having() に渡して使う。
    """

    def __init__(self, func: str, col_expr: str) -> None:
        self._func = func
        self._col_expr = col_expr
        self._alias: str | None = None

    def label(self, alias: str) -> "AggFunc":
        """AS alias を付ける。"""
        new = self.__class__.__new__(self.__class__)
        AggFunc.__init__(new, self._func, self._col_expr)
        new._alias = alias
        return new

    def _sql_expr(self) -> str:
        """SELECT リスト用の SQL 式（エイリアス付き）。"""
        base = f"{self._func}({self._col_expr})"
        return f"{base} AS {self._alias}" if self._alias else base

    def _having_expr(self) -> str:
        """HAVING 句用の SQL 式（エイリアスなし）。"""
        return f"{self._func}({self._col_expr})"

    def _result_key(self) -> str:
        return self._alias or self._func.lower()

    @property
    def asc(self) -> str:
        return f"{self._having_expr()} ASC"

    @property
    def desc(self) -> str:
        return f"{self._having_expr()} DESC"

    # HAVING 条件生成のための比較演算子
    def __eq__(self, other: Any) -> "WhereClause":       # type: ignore[override]
        return WhereClause(f"{self._having_expr()} = %s", [other])

    def __ne__(self, other: Any) -> "WhereClause":       # type: ignore[override]
        return WhereClause(f"{self._having_expr()} != %s", [other])

    def __gt__(self, other: Any) -> "WhereClause":
        return WhereClause(f"{self._having_expr()} > %s", [other])

    def __ge__(self, other: Any) -> "WhereClause":
        return WhereClause(f"{self._having_expr()} >= %s", [other])

    def __lt__(self, other: Any) -> "WhereClause":
        return WhereClause(f"{self._having_expr()} < %s", [other])

    def __le__(self, other: Any) -> "WhereClause":
        return WhereClause(f"{self._having_expr()} <= %s", [other])

    def __repr__(self) -> str:
        return f"<{self._func}({self._col_expr})>"


def _col_expr(col: Any) -> str:
    return col._qualified() if hasattr(col, "_qualified") else str(col)


class Count(AggFunc):
    def __init__(self, col: Any = None) -> None:
        super().__init__("COUNT", _col_expr(col) if col is not None else "*")


class Sum(AggFunc):
    def __init__(self, col: Any) -> None:
        super().__init__("SUM", _col_expr(col))


class Avg(AggFunc):
    def __init__(self, col: Any) -> None:
        super().__init__("AVG", _col_expr(col))


class Max(AggFunc):
    def __init__(self, col: Any) -> None:
        super().__init__("MAX", _col_expr(col))


class Min(AggFunc):
    def __init__(self, col: Any) -> None:
        super().__init__("MIN", _col_expr(col))


# ── JOIN ON 用カラム間比較式 ──────────────────────────────────

@dataclass
class ColumnCompare:
    """
    2つのカラム間の比較式（バインドパラメータなし）。
    ColumnMeta 同士を == / != で比較したときに生成され、
    JOIN の ON 句や WHERE 句で使用する。
    """
    sql: str

    def __and__(self, other: "ColumnCompare") -> "ColumnCompare":
        return ColumnCompare(f"({self.sql}) AND ({other.sql})")

    def __or__(self, other: "ColumnCompare") -> "ColumnCompare":
        return ColumnCompare(f"({self.sql}) OR ({other.sql})")


# ── UPDATE 式 ─────────────────────────────────────────────────

@dataclass
class UpdateExpr:
    """
    列参照を含む UPDATE の SET 式。
    ColumnMeta の算術演算子から生成される。

    例:
        Employee.height - 2   → UpdateExpr("employee.height - %s", [2])
        Product.price * 0.97  → UpdateExpr("product.price * %s", [0.97])
    """
    sql: str
    params: list[Any] = field(default_factory=list)


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

    def _to_db(self, value: Any) -> Any:
        """比較値を to_db() で変換する。"""
        return self._column.to_db(value)

    # ── 比較演算子 ────────────────────────────────────────────
    def __eq__(self, other: Any) -> "WhereClause | ColumnCompare":   # type: ignore[override]
        if isinstance(other, ColumnMeta):
            return ColumnCompare(f"{self._qualified()} = {other._qualified()}")
        if other is None:
            return WhereClause(f"{self._qualified()} IS NULL")
        return WhereClause(f"{self._qualified()} = %s", [self._to_db(other)])

    def __ne__(self, other: Any) -> "WhereClause | ColumnCompare":   # type: ignore[override]
        if isinstance(other, ColumnMeta):
            return ColumnCompare(f"{self._qualified()} != {other._qualified()}")
        if other is None:
            return WhereClause(f"{self._qualified()} IS NOT NULL")
        return WhereClause(f"{self._qualified()} != %s", [self._to_db(other)])

    def __lt__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} < %s", [self._to_db(other)])

    def __le__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} <= %s", [self._to_db(other)])

    def __gt__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} > %s", [self._to_db(other)])

    def __ge__(self, other: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} >= %s", [self._to_db(other)])

    # ── 追加クエリメソッド ────────────────────────────────────
    def like(self, pattern: str) -> WhereClause:
        return WhereClause(f"{self._qualified()} LIKE %s", [pattern])

    def ilike(self, pattern: str) -> WhereClause:
        return WhereClause(f"{self._qualified()} ILIKE %s", [pattern])

    def in_(self, values: "Sequence[Any] | Any") -> WhereClause:
        # サブクエリ対応: _build_sql() を持つオブジェクト (QuerySet / Subquery) を受け付ける
        if hasattr(values, "_build_sql"):
            sub_sql, sub_params = values._build_sql()
            return WhereClause(f"{self._qualified()} IN ({sub_sql})", sub_params)
        placeholders = ", ".join(["%s"] * len(values))
        return WhereClause(f"{self._qualified()} IN ({placeholders})", [self._to_db(v) for v in values])

    def not_in(self, values: "Sequence[Any] | Any") -> WhereClause:
        if hasattr(values, "_build_sql"):
            sub_sql, sub_params = values._build_sql()
            return WhereClause(f"{self._qualified()} NOT IN ({sub_sql})", sub_params)
        placeholders = ", ".join(["%s"] * len(values))
        return WhereClause(f"{self._qualified()} NOT IN ({placeholders})", [self._to_db(v) for v in values])

    def is_null(self) -> WhereClause:
        return WhereClause(f"{self._qualified()} IS NULL")

    def is_not_null(self) -> WhereClause:
        return WhereClause(f"{self._qualified()} IS NOT NULL")

    def between(self, low: Any, high: Any) -> WhereClause:
        return WhereClause(f"{self._qualified()} BETWEEN %s AND %s", [self._to_db(low), self._to_db(high)])

    # ── 算術演算子（UPDATE 式生成用）────────────────────────────
    def __add__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"{self._qualified()} + %s", [other])

    def __sub__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"{self._qualified()} - %s", [other])

    def __mul__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"{self._qualified()} * %s", [other])

    def __truediv__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"{self._qualified()} / %s", [other])

    def __radd__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"%s + {self._qualified()}", [other])

    def __rsub__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"%s - {self._qualified()}", [other])

    def __rmul__(self, other: Any) -> "UpdateExpr":
        return UpdateExpr(f"%s * {self._qualified()}", [other])

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
        check: str | None = None,
    ) -> None:
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.index = index
        self.check = check
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

    # ── 型変換フック ─────────────────────────────────────────
    # サブクラスでオーバーライドして Python ↔ DB 間の型変換を実装する。

    def from_db(self, value: Any) -> Any:
        """DB から読み取った値を Python 型に変換する。デフォルトはそのまま。"""
        return value

    def to_db(self, value: Any) -> Any:
        """Python 値を DB に書き込む前に変換する。デフォルトはそのまま。"""
        return value

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
        if self.check:
            parts.append(f"CHECK ({self.check})")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self._name!r}>"
