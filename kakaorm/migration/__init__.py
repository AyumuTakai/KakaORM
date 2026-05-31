"""
Migration — スキーマ差分検出と SQL 生成
========================================
モデルの現在の定義と DB の実際のスキーマを比較し、
差分 ALTER TABLE 文を自動生成する。

設計:
  1. inspect_db()    : 現在の DB スキーマを取得
  2. inspect_models(): モデルクラスから期待するスキーマを取得
  3. diff()          : 差分を計算
  4. generate_sql()  : 差分から ALTER TABLE SQL を生成
  5. apply()         : SQL を実行

使い方:
    migrator = Migrator(engine)
    plan = await migrator.plan([User, Post, Comment])
    print(plan.sql)      # 実行予定の SQL を確認
    await plan.apply()   # 適用
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Type


@dataclass
class ColumnDiff:
    """1カラムの変更内容。"""
    table: str
    column: str
    action: str  # "add" | "drop" | "alter"
    old_type: str = ""
    new_type: str = ""


@dataclass
class MigrationPlan:
    """差分 SQL のセット。apply() で実行する。"""
    statements: list[str] = field(default_factory=list)
    diffs: list[ColumnDiff] = field(default_factory=list)
    engine: Any = None

    @property
    def sql(self) -> str:
        return ";\n".join(self.statements) + ";" if self.statements else "-- no changes"

    async def apply(self) -> None:
        if not self.statements:
            print("No migration needed.")
            return
        for stmt in self.statements:
            print(f"  Executing: {stmt}")
            await self.engine._execute(stmt, [])
        print(f"Applied {len(self.statements)} statement(s).")

    def is_empty(self) -> bool:
        return len(self.statements) == 0


class Migrator:
    """
    スキーマ差分を計算して MigrationPlan を返す。

    DBからの既存スキーマ取得は DB 種別によって SQL が異なるため、
    Engine の種別を判定して切り替える。
    """

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    async def plan(self, models: list[Type[Any]]) -> MigrationPlan:
        """
        モデルリストと現在の DB スキーマを比較し、差分プランを返す。
        """
        plan = MigrationPlan(engine=self.engine)

        for model_cls in models:
            meta = model_cls._meta
            table = meta.table_name

            # DB に存在するかチェック
            exists = await self._table_exists(table)

            if not exists:
                # テーブルが存在しない → CREATE TABLE
                sql = self._build_create_table(model_cls)
                plan.statements.append(sql)
                plan.diffs.append(ColumnDiff(table, "*", "add", new_type="(new table)"))
            else:
                # テーブルは存在する → カラム差分を確認
                db_cols = await self._fetch_columns(table)
                model_cols = {
                    name: col for name, col in meta.columns.items()
                }

                # 追加されたカラム
                for col_name, col in model_cols.items():
                    if col_name not in db_cols:
                        nullable_default = "DEFAULT NULL" if col.nullable else ""
                        ddl = col.ddl_fragment()
                        stmt = f"ALTER TABLE {table} ADD COLUMN {col_name} {ddl} {nullable_default}".strip()
                        plan.statements.append(stmt)
                        plan.diffs.append(ColumnDiff(table, col_name, "add", new_type=ddl))

                # 削除されたカラム (オプション: 安全のためデフォルト無効)
                for col_name in db_cols:
                    if col_name not in model_cols:
                        # 削除は destructive なので警告のみ (コメントとして出力)
                        plan.statements.append(
                            f"-- WARNING: column {table}.{col_name} exists in DB but not in model. "
                            f"Run with allow_drop=True to drop."
                        )

        return plan

    async def plan_with_drop(self, models: list[Type[Any]]) -> MigrationPlan:
        """allow_drop=True: 不要カラムも DROP する破壊的プランを返す。"""
        base_plan = await self.plan(models)
        # コメント行を実際の DROP 文に変換
        base_plan.statements = [
            s if not s.startswith("-- WARNING:") else
            self._warning_to_drop(s)
            for s in base_plan.statements
        ]
        return base_plan

    # ── 内部ヘルパー ──────────────────────────────────────────

    async def _table_exists(self, table_name: str) -> bool:
        engine_type = type(self.engine).__name__
        if "SQLite" in engine_type:
            rows = await self.engine._fetch(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [table_name],
            )
        elif "MySQL" in engine_type:
            rows = await self.engine._fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=%s",
                [table_name],
            )
        else:
            rows = await self.engine._fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s",
                [table_name],
            )
        return len(rows) > 0

    async def _fetch_columns(self, table_name: str) -> dict[str, str]:
        """既存テーブルのカラム名 → 型 を返す。"""
        engine_type = type(self.engine).__name__
        if "SQLite" in engine_type:
            rows = await self.engine._fetch(
                f"PRAGMA table_info({table_name})", []
            )
            return {row["name"]: row["type"] for row in rows}
        elif "MySQL" in engine_type:
            rows = await self.engine._fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name=%s AND table_schema=DATABASE()",
                [table_name],
            )
            # aiomysql は大文字キーを返す場合があるため小文字に統一
            return {row["column_name"]: row["data_type"] for row in rows}
        else:
            rows = await self.engine._fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name=%s AND table_schema='public'",
                [table_name],
            )
            return {row["column_name"]: row["data_type"] for row in rows}

    def _build_create_table(self, model_cls: Any) -> str:
        meta = model_cls._meta
        col_defs = []
        engine_type = type(self.engine).__name__
        for col_name, col in meta.columns.items():
            ddl = col.ddl_fragment()
            if "SQLite" in engine_type:
                ddl = ddl.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                ddl = ddl.replace("DOUBLE PRECISION", "REAL")
                ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "TEXT")
                ddl = ddl.replace("BOOLEAN", "INTEGER")
            elif "MySQL" in engine_type:
                ddl = ddl.replace("SERIAL PRIMARY KEY", "INT AUTO_INCREMENT PRIMARY KEY")
                ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")
            col_defs.append(f"  {col_name} {ddl}")
        suffix = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if "MySQL" in engine_type else ""
        return (
            f"CREATE TABLE IF NOT EXISTS {meta.table_name} (\n"
            + ",\n".join(col_defs)
            + f"\n){suffix}"
        )

    @staticmethod
    def _warning_to_drop(warning_comment: str) -> str:
        import re
        m = re.search(r"column (\w+)\.(\w+) exists", warning_comment)
        if m:
            table, col = m.group(1), m.group(2)
            return f"ALTER TABLE {table} DROP COLUMN {col}"
        return warning_comment


@dataclass
class MigrationRecord:
    """適用済みマイグレーション 1 件分の情報。"""
    name: str
    applied_at: str


class VersionedMigrator(Migrator):
    """
    マイグレーション履歴を DB テーブルで管理する Migrator 拡張。

    ``kakaorm_migrations`` テーブルに適用済みマイグレーション名を記録し、
    未適用のものだけを実行する。

    使い方::

        from kakaorm.migration import VersionedMigrator

        migrator = VersionedMigrator(engine)

        # 適用したいマイグレーションを順序付き辞書で定義する
        migrations = {
            "001_create_users": lambda: engine.create_table(User),
            "002_add_email_index": lambda: engine.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_email ON user (email)"
            ),
            "003_create_posts": lambda: engine.create_table(Post),
        }

        applied_count = await migrator.run(migrations)
        print(f"{applied_count} migration(s) applied.")

        # 履歴を確認
        history = await migrator.history()
        for record in history:
            print(record.name, record.applied_at)
    """

    HISTORY_TABLE = "kakaorm_migrations"

    async def ensure_history_table(self) -> None:
        """履歴テーブルが存在しなければ作成する。DB 種別に依存しない汎用 DDL を使用。"""
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self.HISTORY_TABLE} ("
            f"  name TEXT PRIMARY KEY,"
            f"  applied_at TEXT NOT NULL"
            f")"
        )
        await self.engine._execute(sql, [])

    async def applied_names(self) -> set[str]:
        """適用済みマイグレーション名のセット。"""
        rows = await self.engine._fetch(
            f"SELECT name FROM {self.HISTORY_TABLE}", []
        )
        return {r["name"] for r in rows}

    async def record(self, name: str) -> None:
        """マイグレーション名を履歴テーブルに記録する。"""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await self.engine._execute(
            f"INSERT INTO {self.HISTORY_TABLE} (name, applied_at) VALUES (%s, %s)",
            [name, now],
        )

    async def history(self) -> list[MigrationRecord]:
        """適用済みマイグレーションを適用順に返す。"""
        rows = await self.engine._fetch(
            f"SELECT name, applied_at FROM {self.HISTORY_TABLE} ORDER BY applied_at ASC",
            [],
        )
        return [MigrationRecord(name=r["name"], applied_at=r["applied_at"]) for r in rows]

    async def run(
        self,
        migrations: dict[str, Callable],
        *,
        verbose: bool = False,
    ) -> int:
        """
        未適用のマイグレーションのみ実行し、履歴に記録する。

        :param migrations: ``{name: async_callable}`` の順序付き辞書。
                           callable は引数なしの非同期関数。
        :param verbose:    True のとき実行中のマイグレーション名を標準出力へ出力。
        :returns:          実行したマイグレーション数。
        """
        await self.ensure_history_table()
        applied = await self.applied_names()

        count = 0
        for name, migrate_fn in migrations.items():
            if name in applied:
                continue
            if verbose:
                print(f"  Applying: {name}")
            await migrate_fn()
            await self.record(name)
            count += 1

        return count
