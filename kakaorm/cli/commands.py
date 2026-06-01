"""
CLI コマンドハンドラー
====================
init, makemigrations, migrate, showmigrations コマンドの実装。
"""

from __future__ import annotations

from pathlib import Path

import typer

from kakaorm.cli.config import ConfigManager
from kakaorm.cli.utils import (
    create_engine_from_url,
    ensure_migrations_dir,
    format_migration_table,
    load_models_from_file,
)
from kakaorm.migration import VersionedMigrator


async def init_command(dir_path: str = "./migrations") -> None:
    """
    マイグレーションディレクトリを初期化する。

    :param dir_path: ディレクトリパス
    """
    try:
        path = Path(dir_path)
        ensure_migrations_dir(path)
        typer.echo(f"✓ Created: {path.resolve()}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


async def makemigrations_command(
    models_file: str,
    output_dir: str | None = None,
    name: str = "",
    db: str | None = None,
) -> None:
    """
    マイグレーションファイルを自動生成する。

    :param models_file: モデル定義ファイルのパス
    :param output_dir: 出力ディレクトリ
    :param name: マイグレーション名のスラグ
    :param db: DB URL
    """
    try:
        config = ConfigManager.load(db_url=db, migration_dir=output_dir)
        engine = await create_engine_from_url(config.get_database_url())

        # モデルクラスを抽出
        models = load_models_from_file(models_file)

        migrator = VersionedMigrator(engine)
        path = await migrator.autogenerate(
            models,
            str(config.get_migration_dir()),
            name=name,
        )

        if path:
            typer.echo(f"✓ Created: {path}")
            plan = await migrator.plan(models)
            typer.echo(f"  Changes: {len(plan.diffs)} change(s)")
        else:
            typer.echo("✓ No changes detected")

        await engine.disconnect()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


async def migrate_command(
    direction: str = "up",
    steps: int = 1,
    db: str | None = None,
    dir: str | None = None,
) -> None:
    """
    マイグレーションを適用またはロールバックする。

    :param direction: "up" または "down"
    :param steps: ロールバック件数（direction="down" 時のみ）
    :param db: DB URL
    :param dir: マイグレーションディレクトリ
    """
    try:
        config = ConfigManager.load(db_url=db, migration_dir=dir)
        engine = await create_engine_from_url(config.get_database_url())

        migrator = VersionedMigrator(engine)

        if direction == "down":
            count = await migrator.downgrade(steps=steps)
            typer.echo(f"✓ Rolled back {count} migration(s)")
        else:
            count = await migrator.run_files(str(config.get_migration_dir()), verbose=True)
            typer.echo(f"✓ Applied {count} migration(s)")

        await engine.disconnect()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)


async def showmigrations_command(
    db: str | None = None,
    dir: str | None = None,
) -> None:
    """
    適用済みマイグレーション履歴を表示する。

    :param db: DB URL
    :param dir: マイグレーションディレクトリ
    """
    try:
        config = ConfigManager.load(db_url=db, migration_dir=dir)
        engine = await create_engine_from_url(config.get_database_url())

        migrator = VersionedMigrator(engine)
        await migrator.ensure_history_table()

        hist = await migrator.history()
        typer.echo(format_migration_table(hist))

        await engine.disconnect()
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)
