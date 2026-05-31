"""
QuerySet — 遅延クエリビルダ
============================
await するまで SQL は実行されない。
メソッドチェーンで条件を積み上げ、最後に execute() / first() を呼ぶ。

設計のポイント:
  - イミュータブルコピーを返す (元の QuerySet は変更しない)
  - SELECT / INSERT / UPDATE / DELETE を統一インターフェースで扱う
  - __await__ を実装し `await Model.filter(...)` でもそのまま動く
  - JOIN / GROUP BY / 集計関数に対応
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, AsyncIterator, Generic, Type, TypeVar

from kakaorm.columns.base import AggFunc, Avg, ColumnCompare, Count, Max, Min, Sum, UpdateExpr, WhereClause

T = TypeVar("T", bound="Model")  # type: ignore[type-arg]


@dataclass
class JoinClause:
    """JOIN 句の情報を保持するデータクラス。"""
    model: Any      # 結合対象のモデルクラス
    on_sql: str     # ON 条件の SQL 文字列（バインドパラメータなし）
    join_type: str  # "INNER" | "LEFT" | "RIGHT"


def _to_where(clause: WhereClause | ColumnCompare) -> WhereClause:
    """ColumnCompare を WhereClause に変換する。"""
    if isinstance(clause, ColumnCompare):
        return WhereClause(clause.sql)
    return clause


class QuerySet(Generic[T]):
    """
    SQL クエリを段階的に構築し、await 時に実行する。

    例:
        # 基本フィルタ
        users = await User.filter(User.age >= 20).order_by(User.name.asc).limit(10)

        # JOIN
        rows = await (
            Post.filter(Post.published == True)
                .join(Author, on=Post.author_id == Author.id)
                .select(Post.title, Author.name)
        )

        # GROUP BY / HAVING
        rows = await (
            Post.all()
                .select(Post.author_id, Count(Post.id).label("cnt"))
                .group_by(Post.author_id)
                .having(Count(Post.id) >= 2)
        )

        # 集計
        total = await Post.all().sum(Post.views)
        stats = await Post.all().aggregate(total=Sum(Post.views), avg=Avg(Post.score))
    """

    def __init__(self, model: Type[T]) -> None:
        self._model = model
        self._where: list[WhereClause] = []
        self._order_by: list[str] = []
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._select_cols: list[str] | None = None  # SQL 式のリスト。None = SELECT *
        self._group_by: list[str] = []
        self._having: list[WhereClause] = []
        self._joins: list[JoinClause] = []

    def _clone(self) -> "QuerySet[T]":
        new = QuerySet(self._model)
        new._where       = list(self._where)
        new._order_by    = list(self._order_by)
        new._limit_val   = self._limit_val
        new._offset_val  = self._offset_val
        new._select_cols = copy.copy(self._select_cols)
        new._group_by    = list(self._group_by)
        new._having      = list(self._having)
        new._joins       = list(self._joins)
        return new

    # ── クエリ条件の積み上げ ──────────────────────────────────

    def filter(self, clause: WhereClause | ColumnCompare) -> "QuerySet[T]":
        """WHERE 条件を追加 (複数は AND で結合)。"""
        qs = self._clone()
        qs._where.append(_to_where(clause))
        return qs

    def exclude(self, clause: WhereClause | ColumnCompare) -> "QuerySet[T]":
        """NOT (clause) を追加。"""
        return self.filter(~_to_where(clause))

    def order_by(self, *cols: str) -> "QuerySet[T]":
        """ORDER BY を指定。ColumnMeta.asc / .desc や AggFunc.asc / .desc を渡す。"""
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

    def select(self, *exprs: Any) -> "QuerySet[T]":
        """
        取得する列・集計式を指定する。
        ColumnMeta / AggFunc を混在して渡せる。
        """
        qs = self._clone()
        cols: list[str] = []
        for expr in exprs:
            if isinstance(expr, AggFunc):
                cols.append(expr._sql_expr())
            elif hasattr(expr, "_qualified"):
                cols.append(expr._qualified())
            else:
                cols.append(str(expr))
        qs._select_cols = cols
        return qs

    def group_by(self, *exprs: Any) -> "QuerySet[T]":
        """GROUP BY 句を追加。ColumnMeta を渡す。"""
        qs = self._clone()
        qs._group_by = [
            expr._qualified() if hasattr(expr, "_qualified") else str(expr)
            for expr in exprs
        ]
        return qs

    def having(self, clause: WhereClause) -> "QuerySet[T]":
        """HAVING 句を追加。AggFunc の比較演算子で生成した WhereClause を渡す。"""
        qs = self._clone()
        qs._having.append(clause)
        return qs

    def join(self, model: Any, *, on: ColumnCompare) -> "QuerySet[T]":
        """INNER JOIN を追加。"""
        qs = self._clone()
        qs._joins.append(JoinClause(model, on.sql, "INNER"))
        return qs

    def left_join(self, model: Any, *, on: ColumnCompare) -> "QuerySet[T]":
        """LEFT JOIN を追加。"""
        qs = self._clone()
        qs._joins.append(JoinClause(model, on.sql, "LEFT"))
        return qs

    def right_join(self, model: Any, *, on: ColumnCompare) -> "QuerySet[T]":
        """RIGHT JOIN を追加。"""
        qs = self._clone()
        qs._joins.append(JoinClause(model, on.sql, "RIGHT"))
        return qs

    # ── SQL 生成 ──────────────────────────────────────────────

    def _build_sql(self) -> tuple[str, list[Any]]:
        """SELECT 文と bind パラメータのタプルを返す。"""
        table = self._model._meta.table_name

        # SELECT 句: JOIN があれば曖昧さ回避のためテーブル名を付ける
        if self._select_cols:
            cols = ", ".join(self._select_cols)
        elif self._joins:
            cols = f"{table}.*"
        else:
            cols = "*"

        sql = f"SELECT {cols} FROM {table}"
        params: list[Any] = []

        # JOIN 句
        for j in self._joins:
            join_table = j.model._meta.table_name
            sql += f" {j.join_type} JOIN {join_table} ON {j.on_sql}"

        # WHERE 句
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)

        # GROUP BY 句
        if self._group_by:
            sql += " GROUP BY " + ", ".join(self._group_by)

        # HAVING 句
        if self._having:
            merged_h = self._having[0]
            for clause in self._having[1:]:
                merged_h = merged_h & clause
            sql += f" HAVING {merged_h.sql}"
            params.extend(merged_h.params)

        # ORDER BY 句
        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)

        # LIMIT / OFFSET
        # SQLite は OFFSET 単独を許可しないため、LIMIT なしの場合は LIMIT -1 を付与する
        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"
        elif self._offset_val is not None:
            sql += " LIMIT -1"
        if self._offset_val is not None:
            sql += f" OFFSET {self._offset_val}"

        return sql, params

    @property
    def _returns_raw(self) -> bool:
        """JOIN / GROUP BY / 集計式がある場合は list[dict] を返す。"""
        if self._joins or self._group_by:
            return True
        if self._select_cols and any("(" in col for col in self._select_cols):
            return True
        return False

    # ── 実行系 ────────────────────────────────────────────────

    async def execute(self) -> list[Any]:
        """
        クエリを実行する。
        - JOIN / GROUP BY / 集計なし → list[Model]
        - JOIN / GROUP BY / 集計あり → list[dict]
        """
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        sql, params = self._build_sql()
        rows = await engine._fetch(sql, params)
        if self._returns_raw:
            return list(rows)
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

    async def aggregate(self, **agg_exprs: AggFunc) -> dict[str, Any]:
        """
        複数の集計関数をまとめて実行し dict で返す。

        例:
            stats = await Post.all().aggregate(
                total=Sum(Post.views),
                avg=Avg(Post.score),
            )
        """
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")
        table = self._model._meta.table_name
        select_parts = [
            f"{agg._having_expr()} AS {alias}"
            for alias, agg in agg_exprs.items()
        ]
        sql = f"SELECT {', '.join(select_parts)} FROM {table}"
        params: list[Any] = []
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)
        rows = await engine._fetch(sql, params)
        return dict(rows[0]) if rows else {alias: None for alias in agg_exprs}

    async def sum(self, col: Any) -> Any:
        """指定カラムの合計を返す。"""
        result = await self.aggregate(_v=Sum(col))
        return result["_v"]

    async def avg(self, col: Any) -> Any:
        """指定カラムの平均を返す。"""
        result = await self.aggregate(_v=Avg(col))
        return result["_v"]

    async def max(self, col: Any) -> Any:
        """指定カラムの最大値を返す。"""
        result = await self.aggregate(_v=Max(col))
        return result["_v"]

    async def min(self, col: Any) -> Any:
        """指定カラムの最小値を返す。"""
        result = await self.aggregate(_v=Min(col))
        return result["_v"]

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
        """
        条件に一致するレコードを一括 UPDATE し更新件数を返す。

        値に UpdateExpr (ColumnMeta の算術演算子の結果) を渡すと
        列参照を含む式として展開される。

        例::

            # 固定値（従来通り）
            await Post.filter(...).update(published=True)

            # 列参照を含む式
            await Product.all().update(price=Product.price * 0.97)
            await Employee.filter(...).update(
                height=Employee.height + 5,
                weight=Employee.weight - 2,
            )
        """
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")
        table = self._model._meta.table_name
        set_parts: list[str] = []
        params: list[Any] = []
        for k, v in values.items():
            if isinstance(v, UpdateExpr):
                set_parts.append(f"{k} = {v.sql}")
                params.extend(v.params)
            else:
                set_parts.append(f"{k} = %s")
                params.append(v)
        sql = f"UPDATE {table} SET {', '.join(set_parts)}"
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)
        return await engine._execute(sql, params)

    async def insert_into(self, dest_model: Any, **mapping: Any) -> int:
        """
        SELECT 結果を別テーブルへ一括 INSERT する (INSERT ... SELECT)。

        mapping のキー   → 挿入先カラム名
        mapping の値:
          - ColumnMeta → SELECT 式として展開（バインドパラメータなし）
          - その他      → リテラル値（バインドパラメータとして展開）

        例::

            await (
                Employee.filter(Employee.hire_fiscal_year <= 1993)
                    .insert_into(Salary,
                        emp_id=Employee.id,   # ColumnMeta
                        amount=20000,          # リテラル
                    )
            )
            # INSERT INTO salary (emp_id, amount)
            # SELECT employee.id, ?
            # FROM employee WHERE hire_fiscal_year <= ?

        戻り値: 挿入した行数
        """
        engine = self._model._engine
        if engine is None:
            raise RuntimeError("No engine connected.")

        dest_table = dest_model._meta.table_name
        src_table = self._model._meta.table_name

        dest_cols: list[str] = []
        select_exprs: list[str] = []
        literal_params: list[Any] = []

        for col_name, value in mapping.items():
            dest_cols.append(col_name)
            if hasattr(value, "_qualified"):  # ColumnMeta
                select_exprs.append(value._qualified())
            else:
                select_exprs.append("%s")
                literal_params.append(value)

        sql = (
            f"INSERT INTO {dest_table} ({', '.join(dest_cols)})"
            f" SELECT {', '.join(select_exprs)} FROM {src_table}"
        )
        # リテラルパラメータが SELECT 句、WHERE 句パラメータがその後に続く
        params: list[Any] = list(literal_params)

        # JOIN 句
        for j in self._joins:
            join_table = j.model._meta.table_name
            sql += f" {j.join_type} JOIN {join_table} ON {j.on_sql}"

        # WHERE 句
        if self._where:
            merged = self._where[0]
            for clause in self._where[1:]:
                merged = merged & clause
            sql += f" WHERE {merged.sql}"
            params.extend(merged.params)

        # GROUP BY / HAVING
        if self._group_by:
            sql += " GROUP BY " + ", ".join(self._group_by)
        if self._having:
            merged_h = self._having[0]
            for clause in self._having[1:]:
                merged_h = merged_h & clause
            sql += f" HAVING {merged_h.sql}"
            params.extend(merged_h.params)

        # ORDER BY / LIMIT / OFFSET
        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)
        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"
        elif self._offset_val is not None:
            sql += " LIMIT -1"
        if self._offset_val is not None:
            sql += f" OFFSET {self._offset_val}"

        return await engine._execute(sql, params)

    # ── Python 組み込みプロトコル ─────────────────────────────

    def __await__(self):
        return self.execute().__await__()

    async def __aiter__(self) -> AsyncIterator[T]:
        results = await self.execute()
        for item in results:
            yield item

    def __repr__(self) -> str:
        sql, params = self._build_sql()
        return f"<QuerySet {sql!r} params={params}>"
