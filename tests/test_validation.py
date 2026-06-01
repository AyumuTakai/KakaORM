"""
バリデーション機構のテスト
"""

import pytest
import kakaorm
from kakaorm import (
    Model, IntColumn, StrColumn, FloatColumn,
    ValidationError,
    min_length, max_length, min_value, max_value, regex, one_of,
)


# ── テスト用モデル ──────────────────────────────────────────────

class UserV(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(20)])
    age   = IntColumn(nullable=True,  validators=[min_value(0), max_value(150)])
    email = StrColumn(nullable=False, validators=[regex(r"^[^@]+@[^@]+\.[^@]+$",
                                                        message="有効なメールアドレスを入力してください。")])
    role  = StrColumn(nullable=True,  validators=[one_of("admin", "user", "guest")])

    class Meta:
        table_name = "userv"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(UserV)
    yield eng
    await eng.disconnect()


# ── validate() のユニットテスト（DB 不要）──────────────────────

class TestValidateMethod:
    def test_valid_instance_passes(self):
        u = UserV(name="Alice", age=30, email="alice@example.com", role="admin")
        u.validate()  # should not raise

    def test_min_length_fails(self):
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "name" in exc_info.value.errors

    def test_max_length_fails(self):
        u = UserV(name="A" * 21, age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "name" in exc_info.value.errors

    def test_min_value_fails(self):
        u = UserV(name="Alice", age=-1, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "age" in exc_info.value.errors

    def test_max_value_fails(self):
        u = UserV(name="Alice", age=200, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "age" in exc_info.value.errors

    def test_regex_fails(self):
        u = UserV(name="Alice", age=30, email="not-an-email")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "email" in exc_info.value.errors
        assert "有効なメールアドレスを入力してください。" in exc_info.value.errors["email"]

    def test_one_of_fails(self):
        u = UserV(name="Alice", age=30, email="alice@example.com", role="superuser")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert "role" in exc_info.value.errors

    def test_one_of_passes(self):
        for role in ("admin", "user", "guest"):
            u = UserV(name="Alice", age=30, email="alice@example.com", role=role)
            u.validate()  # should not raise

    def test_none_value_skipped(self):
        """nullable フィールドが None の場合はバリデータをスキップする。"""
        u = UserV(name="Alice", age=None, email="alice@example.com", role=None)
        u.validate()  # should not raise

    def test_multiple_errors_collected(self):
        """複数フィールドのエラーが一括収集される。"""
        u = UserV(name="A", age=-1, email="bad")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        errors = exc_info.value.errors
        assert "name" in errors
        assert "age" in errors
        assert "email" in errors


# ── save() への組み込みテスト ───────────────────────────────────

class TestValidationOnSave:
    async def test_valid_save_succeeds(self, engine):
        u = UserV(name="Alice", age=30, email="alice@example.com")
        await u.save()
        assert u.id is not None

    async def test_invalid_save_raises_before_db(self, engine):
        """バリデーション失敗時は DB に触れる前に例外を送出する。"""
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError):
            await u.save()
        # DB には挿入されていないはず
        count = await UserV.all().count()
        assert count == 0

    async def test_invalid_update_raises(self, engine):
        """UPDATE 時もバリデーションが走る。"""
        u = await UserV.create(name="Alice", age=30, email="alice@example.com")
        u.name = "X"  # too short
        with pytest.raises(ValidationError):
            await u.save()
        # DB の値は変わっていないはず
        fetched = await UserV.get(UserV.id == u.id)
        assert fetched.name == "Alice"

    async def test_create_raises_on_invalid(self, engine):
        """create() 経由でも ValidationError が送出される。"""
        with pytest.raises(ValidationError):
            await UserV.create(name="A", age=30, email="alice@example.com")
