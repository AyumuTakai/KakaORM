"""
CLI ヘルパー関数
================
Engine 初期化、モデル抽出、ディレクトリ管理など。
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Type

import kakaorm
from kakaorm.model import Model


async def create_engine_from_url(url: str) -> Any:
    """
    DB URL から Engine を初期化する。

    :param url: 接続 URL（例: postgresql+asyncpg://localhost/mydb）
    :return: 初期化済み Engine インスタンス
    """
    try:
        engine = await kakaorm.connect(url)
        return engine
    except Exception as e:
        raise ValueError(f"Failed to create engine from URL {url}: {e}")


def ensure_migrations_dir(path: Path) -> None:
    """
    マイグレーションディレクトリを作成し、.gitkeep を追加する。

    :param path: ディレクトリパス
    """
    path.mkdir(parents=True, exist_ok=True)
    gitkeep = path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()


def load_models_from_file(file_path: str) -> list[Type[Model]]:
    """
    Python ファイルから Model サブクラスを抽出する。

    :param file_path: .py ファイルのパス
    :return: Model サブクラスのリスト
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Models file not found: {file_path}")

    # モジュールを動的にインポート
    spec = importlib.util.spec_from_file_location("models_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["models_module"] = module
    spec.loader.exec_module(module)

    # Model サブクラスを抽出
    models: list[Type[Model]] = []
    for name, obj in inspect.getmembers(module):
        if (
            inspect.isclass(obj)
            and issubclass(obj, Model)
            and obj is not Model
            and obj.__module__ == "models_module"
        ):
            models.append(obj)

    if not models:
        raise ValueError(f"No Model subclasses found in {file_path}")

    return models


def format_migration_table(records: list[Any]) -> str:
    """
    マイグレーション履歴をテーブル形式で整形する。

    :param records: MigrationRecord のリスト
    :return: テーブル形式の文字列
    """
    if not records:
        return "No migrations applied yet"

    lines = ["\n Applied Migrations:\n"]
    lines.append(f"{'Migration':<25} │ {'Applied At':<30}")
    lines.append("─" * 58)

    for record in records:
        lines.append(
            f"{record.name:<25} │ {record.applied_at:<30}"
        )

    return "\n".join(lines)
