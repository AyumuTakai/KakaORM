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
    print(plan.sql)        # 実行予定の UP SQL を確認
    await plan.apply()     # 適用
    await plan.apply_down()  # ロールバック

    # ファイル自動生成
    migrator = VersionedMigrator(engine)
    await migrator.autogenerate([User, Post], "./migrations", name="add_bio")
    await migrator.run_files("./migrations")
    await migrator.downgrade(steps=1)
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
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
    """
    差分 SQL のセット。

    - ``statements``      : UP 方向の SQL（適用）
    - ``down_statements`` : DOWN 方向の SQL（ロールバック）。apply_down() が逆順で実行する。
    - ``diffs``           : 変更内容の詳細情報
    """
    statements: list[str] = field(default_factory=list)
    diffs: list[ColumnDiff] = field(default_factory=list)
    down_statements: list[str] = field(default_factory=list)
    engine: Any = None

    @property
    def sql(self) -> str:
        return ";\n".join(self.statements) + ";" if self.statements else "-- no changes"

    @property
    def down_sql(self) -> str:
        return ";\n".join(reversed(self.down_statements)) + ";" if self.down_statements else "-- no changes"

    async def apply(self) -> None:
        """UP 方向の SQL を順番に実行する。"""
        if not self.statements:
            print("No migration needed.")
            return
        for stmt in self.statements:
            print(f"  Executing: {stmt}")
            await self.engine._execute(stmt, [])
        print(f"Applied {len(self.statements)} statement(s).")

    async def apply_down(self) -> None:
        """DOWN 方向の SQL を逆順に実行してロールバックする。"""
        if not self.down_statements:
            print("No down migration available.")
            return
        for stmt in reversed(self.down_statements):
            print(f"  Rolling back: {stmt}")
            await self.engine._execute(stmt, [])
        print(f"Rolled back {len(self.down_statements)} statement(s).")

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

        削除されたカラムは安全のため WARNING コメントとして出力する。
        DROP も含める場合は :meth:`plan_with_drop` を使用する。

        ArchiveModel サブクラス（``_archive_table_name`` 属性を持つモデル）は
        アーカイブテーブルも自動的に差分計算の対象に含める。
        """
        plan = MigrationPlan(engine=self.engine)

        # ArchiveModel のアーカイブテーブルを expanded_models に追加
        expanded_models: list[Type[Any]] = []
        for model_cls in models:
            expanded_models.append(model_cls)
            if hasattr(model_cls, "_archive_table_name"):
                expanded_models.append(self._make_archive_proxy(model_cls))

        for model_cls in expanded_models:
            meta = model_cls._meta
            table = meta.table_name

            # DB に存在するかチェック
            exists = await self._table_exists(table)

            if not exists:
                # テーブルが存在しない → CREATE TABLE
                sql = self._build_create_table(model_cls)
                plan.statements.append(sql)
                plan.diffs.append(ColumnDiff(table, "*", "add", new_type="(new table)"))
                # DOWN: DROP TABLE
                quoted_table = self.engine.quote_identifier(table)
                plan.down_statements.append(f"DROP TABLE IF EXISTS {quoted_table}")
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
                        quoted_table = self.engine.quote_identifier(table)
                        quoted_col = self.engine.quote_identifier(col_name)
                        stmt = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {ddl} {nullable_default}".strip()
                        plan.statements.append(stmt)
                        plan.diffs.append(ColumnDiff(table, col_name, "add", new_type=ddl))
                        # DOWN: ADD の逆は DROP
                        plan.down_statements.append(f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}")

                # 削除されたカラム (安全のためデフォルトは警告コメントのみ)
                for col_name in db_cols:
                    if col_name not in model_cols:
                        old_type = db_cols[col_name]
                        plan.diffs.append(ColumnDiff(table, col_name, "drop", old_type=old_type))
                        plan.statements.append(
                            f"-- WARNING: column {table}.{col_name} exists in DB but not in model. "
                            f"Run plan_with_drop() to drop."
                        )
                        # DOWN: DROP の逆は ADD（old_type を使って元に戻す）
                        quoted_table = self.engine.quote_identifier(table)
                        quoted_col = self.engine.quote_identifier(col_name)
                        plan.down_statements.append(
                            f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {old_type}"
                        )

        return plan

    async def run(self, models: list[Type[Any]]) -> MigrationPlan:
        """
        モデルリストのスキーマ差分を計算し、差分がある場合のみ適用する。

        ``plan()`` → ``apply()`` の定型パターンを 1 行で書けるショートハンド。

        例::

            migrator = Migrator(engine)
            await migrator.run([Group, Contact])

        :param models: マイグレーション対象のモデルクラスリスト。
        :returns:      実行した :class:`MigrationPlan`。差分なしの場合も返す。
        """
        plan = await self.plan(models)
        if not plan.is_empty():
            await plan.apply()
        return plan

    async def plan_with_drop(self, models: list[Type[Any]]) -> MigrationPlan:
        """allow_drop=True: 不要カラムも DROP する破壊的プランを返す。"""
        base_plan = await self.plan(models)
        # WARNING コメントを実際の DROP 文に変換（down_statements は plan() で生成済み）
        base_plan.statements = [
            s if not s.startswith("-- WARNING:") else
            self._warning_to_drop(s)
            for s in base_plan.statements
        ]
        return base_plan

    async def autogenerate(
        self,
        models: list[Type[Any]],
        output_dir: str,
        *,
        name: str = "",
    ) -> "pathlib.Path | None":
        """
        モデルと DB の差分から migration ファイルを自動生成する。

        差分がない場合は ``None`` を返す。

        生成されるファイル形式::

            # migrations/0001_add_bio.py
            # Auto-generated by KakaORM
            up = [
                "ALTER TABLE user ADD COLUMN bio TEXT",
            ]
            down = [
                "ALTER TABLE user DROP COLUMN bio",
            ]

        :param models:     差分検出対象のモデルクラスリスト。
        :param output_dir: 出力ディレクトリのパス。存在しない場合は自動作成する。
        :param name:       ファイル名のスラグ（例: ``"add_bio"``）。省略時は ``"migration"``。
        :returns:          生成したファイルの ``pathlib.Path``。差分なしなら ``None``。

        使い方::

            migrator = VersionedMigrator(engine)
            path = await migrator.autogenerate([User, Post], "./migrations", name="add_bio")
            # → migrations/0001_add_bio.py が生成される
        """
        plan = await self.plan_with_drop(models)
        if plan.is_empty():
            return None

        out = pathlib.Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        existing = sorted(out.glob("[0-9][0-9][0-9][0-9]_*.py"))
        seq = len(existing) + 1
        slug = name.strip().replace(" ", "_").lower() if name else "migration"
        filepath = out / f"{seq:04d}_{slug}.py"

        # WARNING コメントを除いた UP SQL
        up_stmts = [s for s in plan.statements if not s.startswith("--")]
        # DOWN SQL は apply_down() と同じく逆順で格納（ファイル内で実行順）
        down_stmts = list(reversed(plan.down_statements))

        def _fmt(stmts: list[str]) -> str:
            if not stmts:
                return ""
            return "\n".join(f'    {json.dumps(s, ensure_ascii=False)},' for s in stmts) + "\n"

        content = (
            f"# Auto-generated by KakaORM\n"
            f"# Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
            f"\n"
            f"up = [\n{_fmt(up_stmts)}]\n"
            f"\n"
            f"down = [\n{_fmt(down_stmts)}]\n"
        )

        filepath.write_text(content, encoding="utf-8")
        return filepath

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
        col_defs = [
            f"  {self.engine.quote_identifier(col_name)} {self.engine._adapt_ddl(col.ddl_fragment())}"
            for col_name, col in meta.columns.items()
        ]
        col_defs = self.engine._post_process_col_defs(col_defs)
        quoted_table = self.engine.quote_identifier(meta.table_name)
        return (
            f"CREATE TABLE IF NOT EXISTS {quoted_table} (\n"
            + ",\n".join(col_defs)
            + f"\n){self.engine._table_suffix}"
        )

    def _make_archive_proxy(self, model_cls: Any) -> Any:
        """
        ArchiveModel のアーカイブテーブルをあたかも通常モデルのように扱う
        プロキシオブジェクトを返す。

        アーカイブテーブルは:
          - メインテーブルと同じカラム構成（id は auto_increment なし）
          - archived_at TEXT カラムが追加される
        """
        from kakaorm.columns.base import Column
        from kakaorm.columns.types import DateTimeColumn
        from kakaorm.model import ModelMeta

        main_meta  = model_cls._meta
        archive_table = model_cls._archive_table_name()

        # id カラムの auto_increment を無効にしたコピーを作る
        archive_columns: dict[str, Column] = {}
        for col_name, col in main_meta.columns.items():
            if getattr(col, "auto_increment", False):
                from kakaorm.columns.types import IntColumn
                new_col = IntColumn(primary_key=col.primary_key, nullable=col.nullable)
                new_col._name = col_name
                archive_columns[col_name] = new_col
            else:
                archive_columns[col_name] = col

        # archived_at カラムを追加
        archived_at_col = DateTimeColumn(nullable=False)
        archived_at_col._name = "archived_at"
        archive_columns["archived_at"] = archived_at_col

        archive_meta = ModelMeta(
            table_name=archive_table,
            columns=archive_columns,
            pk_name=main_meta.pk_name,
        )
        archive_meta._engine = getattr(model_cls, "_engine", None)

        class _ArchiveProxy:
            _meta = archive_meta
            _engine = getattr(model_cls, "_engine", None)

        return _ArchiveProxy

    def _warning_to_drop(self, warning_comment: str) -> str:
        import re
        m = re.search(r"column (\w+)\.(\w+) exists", warning_comment)
        if m:
            table, col = m.group(1), m.group(2)
            quoted_table = self.engine.quote_identifier(table)
            quoted_col = self.engine.quote_identifier(col)
            return f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"
        return warning_comment


@dataclass
class MigrationRecord:
    """適用済みマイグレーション 1 件分の情報。"""
    name: str
    applied_at: str
    down_sql: str = ""


class VersionedMigrator(Migrator):
    """
    マイグレーション履歴を DB テーブルで管理する Migrator 拡張。

    ``kakaorm_migrations`` テーブルに適用済みマイグレーション名を記録し、
    未適用のものだけを実行する。ダウングレードにも対応する。

    使い方::

        from kakaorm.migration import VersionedMigrator

        migrator = VersionedMigrator(engine)

        # ファイルベースのワークフロー（推奨）
        await migrator.autogenerate([User, Post], "./migrations", name="init")
        applied = await migrator.run_files("./migrations")   # 未適用を一括適用
        await migrator.downgrade(steps=1)                    # 直近 1 件をロールバック

        # 手動マイグレーション（後方互換）
        migrations = {
            "001_create_users": lambda: engine.create_table(User),
        }
        await migrator.run(migrations)
    """

    HISTORY_TABLE = "kakaorm_migrations"

    async def ensure_history_table(self) -> None:
        """履歴テーブルが存在しなければ作成する。既存テーブルに down_sql カラムを追加する。"""
        quoted_table = self.engine.quote_identifier(self.HISTORY_TABLE)
        quoted_col = self.engine.quote_identifier("down_sql")
        sql = (
            f"CREATE TABLE IF NOT EXISTS {quoted_table} ("
            f"  name TEXT PRIMARY KEY,"
            f"  applied_at TEXT NOT NULL,"
            f"  {quoted_col} TEXT NOT NULL DEFAULT ''"
            f")"
        )
        await self.engine._execute(sql, [])

        # 既存テーブル（down_sql カラムなし）へのマイグレーション
        existing_cols = await self._fetch_columns(self.HISTORY_TABLE)
        if "down_sql" not in existing_cols:
            try:
                await self.engine._execute(
                    f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} TEXT NOT NULL DEFAULT ''",
                    [],
                )
            except Exception:
                pass  # 既に存在する場合（DB によってはエラーを返さない）

    async def applied_names(self) -> set[str]:
        """適用済みマイグレーション名のセット。"""
        quoted_table = self.engine.quote_identifier(self.HISTORY_TABLE)
        rows = await self.engine._fetch(
            f"SELECT name FROM {quoted_table}", []
        )
        return {r["name"] for r in rows}

    async def record(self, name: str, down_sql: str = "") -> None:
        """マイグレーション名と DOWN SQL を履歴テーブルに記録する。"""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        quoted_table = self.engine.quote_identifier(self.HISTORY_TABLE)
        quoted_name = self.engine.quote_identifier("name")
        quoted_applied_at = self.engine.quote_identifier("applied_at")
        quoted_down_sql = self.engine.quote_identifier("down_sql")
        await self.engine._execute(
            f"INSERT INTO {quoted_table} ({quoted_name}, {quoted_applied_at}, {quoted_down_sql}) VALUES (%s, %s, %s)",
            [name, now, down_sql],
        )

    async def history(self) -> list[MigrationRecord]:
        """適用済みマイグレーションを適用順に返す。"""
        quoted_table = self.engine.quote_identifier(self.HISTORY_TABLE)
        quoted_name = self.engine.quote_identifier("name")
        quoted_applied_at = self.engine.quote_identifier("applied_at")
        quoted_down_sql = self.engine.quote_identifier("down_sql")
        rows = await self.engine._fetch(
            f"SELECT {quoted_name}, {quoted_applied_at}, {quoted_down_sql} FROM {quoted_table} ORDER BY {quoted_applied_at} ASC",
            [],
        )
        return [
            MigrationRecord(
                name=r["name"],
                applied_at=r["applied_at"],
                down_sql=r.get("down_sql", ""),
            )
            for r in rows
        ]

    async def downgrade(self, steps: int = 1) -> int:
        """
        直近 ``steps`` 件のマイグレーションをロールバックする。

        :param steps: ロールバックする件数（デフォルト: 1）。
        :returns:     実際にロールバックした件数。

        使い方::

            await migrator.downgrade()       # 直近 1 件をロールバック
            await migrator.downgrade(steps=3)  # 直近 3 件をロールバック
        """
        await self.ensure_history_table()
        hist = await self.history()
        if not hist:
            return 0

        to_undo = hist[-steps:]
        count = 0
        for record in reversed(to_undo):
            down_stmts: list[str] = json.loads(record.down_sql) if record.down_sql else []
            for sql in down_stmts:
                await self.engine._execute(sql, [])
            await self.engine._execute(
                f"DELETE FROM {self.HISTORY_TABLE} WHERE name = %s",
                [record.name],
            )
            count += 1

        return count

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
            await self.record(name)  # down_sql は空（手動マイグレーションはダウングレード未対応）
            count += 1

        return count

    async def run_files(
        self,
        directory: str,
        *,
        verbose: bool = False,
    ) -> int:
        """
        ディレクトリ内の migration ファイルを順番に適用する。

        ``0001_*.py`` 形式のファイルを名前順に読み込み、未適用のものを実行する。
        各ファイルには ``up: list[str]`` と ``down: list[str]`` を定義する。

        :param directory: マイグレーションファイルが格納されたディレクトリのパス。
        :param verbose:   True のとき適用中のファイル名を標準出力へ出力。
        :returns:         実行したファイル数。

        使い方::

            await migrator.run_files("./migrations")
            await migrator.downgrade(steps=1)  # 直近 1 件をロールバック
        """
        await self.ensure_history_table()
        applied = await self.applied_names()

        files = sorted(pathlib.Path(directory).glob("[0-9][0-9][0-9][0-9]_*.py"))
        count = 0

        for path in files:
            name = path.stem
            if name in applied:
                continue
            if verbose:
                print(f"  Applying: {name}")

            # ファイルを動的インポート
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Migration file could not be loaded: {path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            up_stmts: list[str] = getattr(mod, "up", [])
            down_stmts: list[str] = getattr(mod, "down", [])

            for sql in up_stmts:
                await self.engine._execute(sql, [])

            # down_sql は JSON でシリアライズして保存（downgrade() が使用する）
            await self.record(name, down_sql=json.dumps(down_stmts))
            count += 1

        return count
