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


# ── e.detail 構造化テスト ────────────────────────────────────────

class TestValidationDetail:
    """e.detail が正しい構造を持つことを検証する。"""

    # ── 共通ヘルパー ──────────────────────────────────────────

    def _get_issue(self, detail: list[dict], field: str, rule: str) -> dict:
        """detail から指定フィールド・ルールのエントリを取得する。"""
        for item in detail:
            if item["field"] == field and item["rule"] == rule:
                return item
        raise AssertionError(f"No issue found for field={field!r} rule={rule!r} in {detail}")

    # ── 共通フィールドの検証 ──────────────────────────────────

    def test_detail_has_required_keys(self):
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = exc_info.value.detail[0]
        for key in ("status", "field", "rule", "message", "received"):
            assert key in issue, f"key {key!r} missing from detail entry"

    def test_detail_status_is_always_validation_error(self):
        u = UserV(name="A", age=-1, email="bad")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert all(i["status"] == "validation_error" for i in exc_info.value.detail)

    def test_detail_field_matches_column_name(self):
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        assert exc_info.value.detail[0]["field"] == "name"

    def test_detail_message_matches_errors_dict(self):
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        e = exc_info.value
        issue = e.detail[0]
        assert issue["message"] in e.errors[issue["field"]]

    # ── ルール別の追加キー ────────────────────────────────────

    def test_min_length_issue(self):
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "name", "min_length")
        assert issue["rule"] == "min_length"
        assert issue["received"] == "A"
        assert issue["expected_min"] == 2

    def test_max_length_issue(self):
        u = UserV(name="A" * 21, age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "name", "max_length")
        assert issue["expected_max"] == 20
        assert issue["received"] == "A" * 21

    def test_min_value_issue(self):
        u = UserV(name="Alice", age=-1, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "age", "min_value")
        assert issue["expected_min"] == 0
        assert issue["received"] == -1

    def test_max_value_issue(self):
        u = UserV(name="Alice", age=200, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "age", "max_value")
        assert issue["expected_max"] == 150
        assert issue["received"] == 200

    def test_regex_issue(self):
        u = UserV(name="Alice", age=30, email="not-an-email")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "email", "regex")
        assert "pattern" in issue
        assert issue["received"] == "not-an-email"

    def test_one_of_issue(self):
        u = UserV(name="Alice", age=30, email="alice@example.com", role="superuser")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        issue = self._get_issue(exc_info.value.detail, "role", "one_of")
        assert issue["received"] == "superuser"
        assert set(issue["choices"]) == {"admin", "user", "guest"}

    # ── 複数エラーの一括収集 ─────────────────────────────────

    def test_detail_collects_all_failures(self):
        u = UserV(name="A", age=-1, email="bad")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        fields = {i["field"] for i in exc_info.value.detail}
        assert "name" in fields
        assert "age" in fields
        assert "email" in fields

    def test_detail_length_matches_failure_count(self):
        u = UserV(name="A", age=-1, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        # name: min_length(2) 失敗, age: min_value(0) 失敗 → 2 件
        assert len(exc_info.value.detail) == 2

    # ── カスタムバリデータ ────────────────────────────────────

    def test_custom_validator_gets_rule_custom(self):
        def must_start_with_upper(value):
            if value and not value[0].isupper():
                raise ValidationError("大文字で始まる必要があります。")

        class Titled(Model):
            name = __import__("kakaorm").StrColumn(
                validators=[must_start_with_upper]
            )
            class Meta:
                table_name = "titled"

        t = Titled(name="alice")
        with pytest.raises(ValidationError) as exc_info:
            t.validate()
        issue = self._get_issue(exc_info.value.detail, "name", "custom")
        assert issue["received"] == "alice"
        assert issue["message"] == "大文字で始まる必要があります。"

    # ── 後方互換: errors は従来通り ──────────────────────────

    def test_errors_dict_unchanged(self):
        """e.detail を追加しても e.errors の形式は変わらない。"""
        u = UserV(name="A", age=30, email="alice@example.com")
        with pytest.raises(ValidationError) as exc_info:
            u.validate()
        errors = exc_info.value.errors
        assert isinstance(errors, dict)
        assert "name" in errors
        assert isinstance(errors["name"], list)
        assert isinstance(errors["name"][0], str)
