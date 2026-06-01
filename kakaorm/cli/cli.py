"""
KakaORM マイグレーション CLI
=============================
Typer ベースの CLI ツール。マイグレーション管理コマンドを提供する。

使用例:
    kakaorm init ./migrations
    kakaorm makemigrations models.py --name "add_bio"
    kakaorm migrate
    kakaorm migrate --down 1
    kakaorm showmigrations
"""

from __future__ import annotations

import asyncio

import typer

from kakaorm.cli.commands import (
    init_command,
    makemigrations_command,
    migrate_command,
    showmigrations_command,
)

__all__ = ["main"]

app = typer.Typer(
    help="KakaORM マイグレーション管理ツール",
    no_args_is_help=True,
)


@app.command()
def init(
    dir: str = typer.Argument(
        "./migrations",
        help="マイグレーションディレクトリのパス",
    ),
) -> None:
    """マイグレーションディレクトリを初期化する。"""
    asyncio.run(init_command(dir))


@app.command()
def makemigrations(
    models_file: str = typer.Argument(
        ...,
        help="モデル定義ファイルのパス（例: models.py）",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--dir",
        help="マイグレーション出力ディレクトリ",
    ),
    name: str = typer.Option(
        "",
        "--name",
        help="マイグレーション名のスラグ（例: add_bio）",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DB URL（デフォルト: DATABASE_URL 環境変数）",
    ),
) -> None:
    """マイグレーションファイルを自動生成する。"""
    asyncio.run(
        makemigrations_command(
            models_file,
            output_dir=output_dir,
            name=name,
            db=db,
        )
    )


@app.command()
def migrate(
    down: bool = typer.Option(
        False,
        "--down",
        help="ロールバック方向（デフォルト: UP）",
    ),
    steps: int = typer.Option(
        1,
        "--steps",
        help="ロールバック件数",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="DB URL（デフォルト: DATABASE_URL 環境変数）",
    ),
    dir: str | None = typer.Option(
        None,
        "--dir",
        help="マイグレーションディレクトリ",
    ),
) -> None:
    """マイグレーションを適用またはロールバックする。"""
    direction = "down" if down else "up"
    asyncio.run(
        migrate_command(
            direction=direction,
            steps=steps,
            db=db,
            dir=dir,
        )
    )


@app.command()
def showmigrations(
    db: str | None = typer.Option(
        None,
        "--db",
        help="DB URL（デフォルト: DATABASE_URL 環境変数）",
    ),
    dir: str | None = typer.Option(
        None,
        "--dir",
        help="マイグレーションディレクトリ",
    ),
) -> None:
    """適用済みマイグレーション履歴を表示する。"""
    asyncio.run(showmigrations_command(db=db, dir=dir))


def main() -> None:
    """CLI エントリポイント。"""
    app()


if __name__ == "__main__":
    main()
