"""
CLI 設定管理
=============
環境変数、.env ファイル、CLI オプションから DB URL とマイグレーションディレクトリを読込む。
優先度: CLI オプション > .env > 環境変数 > デフォルト値
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigManager:
    """CLI 設定を一元管理するクラス。"""

    def __init__(
        self,
        database_url: str | None = None,
        migration_dir: str | None = None,
    ) -> None:
        self.database_url = database_url or self._load_database_url()
        self.migration_dir = migration_dir or self._load_migration_dir()

    @staticmethod
    def _load_database_url() -> str:
        """
        DB URL を以下の優先度で読込む:
        1. 環境変数 DATABASE_URL
        2. .env ファイル
        デフォルトはなし（必須）
        """
        # .env ファイルを読込（必須ではない）
        load_dotenv()

        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError(
                "DATABASE_URL not found. Set it via environment variable, .env file, or --db option."
            )
        return url

    @staticmethod
    def _load_migration_dir() -> str:
        """
        マイグレーションディレクトリを以下の優先度で決定:
        1. 環境変数 KAKAORM_MIGRATIONS_DIR
        2. .env ファイル
        3. デフォルト ./migrations
        """
        load_dotenv()
        return os.environ.get("KAKAORM_MIGRATIONS_DIR", "./migrations")

    @staticmethod
    def load(
        db_url: str | None = None,
        migration_dir: str | None = None,
    ) -> ConfigManager:
        """
        設定を読込む。

        :param db_url: DB URL（CLI オプション）
        :param migration_dir: マイグレーションディレクトリ（CLI オプション）
        :return: ConfigManager インスタンス
        """
        return ConfigManager(database_url=db_url, migration_dir=migration_dir)

    def get_database_url(self) -> str:
        """DB URL を返す。"""
        if not self.database_url:
            raise ValueError("DATABASE_URL not configured")
        return self.database_url

    def get_migration_dir(self) -> Path:
        """マイグレーションディレクトリを Path として返す。"""
        return Path(self.migration_dir)
