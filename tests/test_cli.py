"""
マイグレーション CLI テスト
===========================
ConfigManager, ヘルパー関数、CLIコマンド。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kakaorm import Model
from kakaorm.cli.config import ConfigManager
from kakaorm.cli.utils import (
    create_engine_from_url,
    ensure_migrations_dir,
    format_migration_table,
    load_models_from_file,
)
from kakaorm.columns.types import IntColumn, StrColumn


class TestConfigManager:
    """ConfigManager のテスト。"""

    def test_load_database_url_from_environment(self, monkeypatch):
        """環境変数から DB URL を読込む。"""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        config = ConfigManager.load()
        assert config.get_database_url() == "sqlite+aiosqlite:///:memory:"

    def test_load_database_url_from_cli_option(self):
        """CLI オプションが環境変数を上書きする。"""
        config = ConfigManager.load(db_url="postgresql://test")
        assert config.get_database_url() == "postgresql://test"

    def test_load_database_url_missing_raises_error(self, monkeypatch):
        """DB URL がないとエラーを raise する。"""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValueError, match="DATABASE_URL not found"):
            ConfigManager.load()

    def test_load_migration_dir_from_environment(self, monkeypatch):
        """環境変数から migration directory を読込む。"""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("KAKAORM_MIGRATIONS_DIR", "./custom_migrations")
        config = ConfigManager.load()
        assert config.get_migration_dir() == Path("./custom_migrations")

    def test_load_migration_dir_from_cli_option(self, monkeypatch):
        """CLI オプションが環境変数を上書きする。"""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        config = ConfigManager.load(migration_dir="./cli_migrations")
        assert config.get_migration_dir() == Path("./cli_migrations")

    def test_load_migration_dir_default(self, monkeypatch):
        """デフォルト値は ./migrations。"""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.delenv("KAKAORM_MIGRATIONS_DIR", raising=False)
        config = ConfigManager.load()
        assert config.get_migration_dir() == Path("./migrations")


class TestEnsureMigrationsDir:
    """ensure_migrations_dir のテスト。"""

    def test_creates_directory_and_gitkeep(self):
        """ディレクトリと .gitkeep を作成する。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            assert not mig_dir.exists()

            ensure_migrations_dir(mig_dir)

            assert mig_dir.exists()
            assert (mig_dir / ".gitkeep").exists()

    def test_idempotent(self):
        """二度呼んでもエラーが起こらない。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            ensure_migrations_dir(mig_dir)
            ensure_migrations_dir(mig_dir)  # Second call
            assert (mig_dir / ".gitkeep").exists()


class TestLoadModelsFromFile:
    """load_models_from_file のテスト。"""

    def test_load_models_from_file(self):
        """モデル定義ファイルから Model クラスを抽出する。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # テスト用モデルを含むファイルを作成
            models_file = Path(tmpdir) / "test_models.py"
            models_file.write_text(
                """
from kakaorm import Model, IntColumn, StrColumn

class User(Model):
    __table__ = "users"
    id = IntColumn(primary_key=True)
    name = StrColumn(max_length=100)

class Post(Model):
    __table__ = "posts"
    id = IntColumn(primary_key=True)
    title = StrColumn(max_length=255)

# Not a model
class Helper:
    pass
"""
            )

            models = load_models_from_file(str(models_file))

            assert len(models) == 2
            assert any(m.__name__ == "User" for m in models)
            assert any(m.__name__ == "Post" for m in models)
            assert not any(m.__name__ == "Helper" for m in models)

    def test_load_models_file_not_found(self):
        """ファイルが見つからないとエラー。"""
        with pytest.raises(FileNotFoundError):
            load_models_from_file("/nonexistent/models.py")

    def test_load_models_no_models_in_file(self):
        """モデルが含まれていないとエラー。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            models_file = Path(tmpdir) / "empty.py"
            models_file.write_text("# No models here")

            with pytest.raises(ValueError, match="No Model subclasses found"):
                load_models_from_file(str(models_file))


class TestFormatMigrationTable:
    """format_migration_table のテスト。"""

    def test_format_empty_list(self):
        """マイグレーション履歴が空の場合。"""
        result = format_migration_table([])
        assert "No migrations applied yet" in result

    def test_format_migration_records(self):
        """マイグレーション履歴をテーブル形式で整形する。"""
        record1 = MagicMock()
        record1.name = "0001_initial"
        record1.applied_at = "2026-06-01 10:30:00"

        record2 = MagicMock()
        record2.name = "0002_add_email"
        record2.applied_at = "2026-06-01 10:35:00"

        result = format_migration_table([record1, record2])

        assert "0001_initial" in result
        assert "0002_add_email" in result
        assert "Applied Migrations" in result
        assert "2026-06-01 10:30:00" in result


@pytest.mark.asyncio
class TestCreateEngineFromUrl:
    """create_engine_from_url のテスト。"""

    async def test_create_engine_sqlite(self):
        """SQLite Engine を作成する。"""
        engine = await create_engine_from_url("sqlite+aiosqlite:///:memory:")
        assert engine is not None
        await engine.disconnect()

    async def test_create_engine_invalid_url(self):
        """無効な URL はエラー。"""
        with pytest.raises(ValueError, match="Failed to create engine"):
            await create_engine_from_url("invalid://url")


class TestConfigManagerIntegration:
    """ConfigManager の統合テスト。"""

    def test_priority_cli_over_env(self, monkeypatch):
        """CLI オプション > 環境変数の優先度。"""
        monkeypatch.setenv("DATABASE_URL", "env_url")
        config = ConfigManager.load(db_url="cli_url")
        assert config.get_database_url() == "cli_url"

    def test_priority_env_default(self, monkeypatch):
        """環境変数 > デフォルト。"""
        monkeypatch.setenv("DATABASE_URL", "env_url")
        config = ConfigManager.load()
        assert config.get_database_url() == "env_url"


class TestLoadModelsRealFile:
    """実際のモデルファイルから抽出するテスト。"""

    def test_load_from_examples_blog(self):
        """examples/blog_example.py から抽出。"""
        example_file = Path(__file__).parent.parent / "examples" / "blog_example.py"
        if example_file.exists():
            models = load_models_from_file(str(example_file))
            # blog_example.py に User, Post モデルがあるはず
            assert len(models) > 0
