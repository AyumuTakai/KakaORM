"""
kakaorm.i18n — translate_detail のテスト
"""

import pytest
from kakaorm import (
    Model, IntColumn, StrColumn,
    ValidationError,
    min_length, max_length, min_value, max_value, regex, one_of,
    translate_detail, SUPPORTED_LOCALES,
)


# ── テスト用モデル ─────────────────────────────────────────────

class Item(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(10)])
    score = IntColumn(nullable=True,  validators=[min_value(0), max_value(100)])
    code  = StrColumn(nullable=True,  validators=[regex(r"^[A-Z]{3}$")])
    tier  = StrColumn(nullable=True,  validators=[one_of("gold", "silver", "bronze")])

    class Meta:
        table_name = "item"


def _get_issue(detail: list[dict], field: str, rule: str) -> dict:
    for item in detail:
        if item["field"] == field and item["rule"] == rule:
            return item
    raise AssertionError(f"No issue for field={field!r} rule={rule!r} in {detail}")


def _make_detail(*validators_and_values) -> list[dict]:
    """指定フィールドの失敗 detail を直接生成するヘルパー。"""
    obj = Item(name="A", score=-1, code="bad", tier="platinum")
    with pytest.raises(ValidationError) as exc_info:
        obj.validate()
    return exc_info.value.detail


# ── SUPPORTED_LOCALES ──────────────────────────────────────────

class TestSupportedLocales:
    def test_contains_ja_and_en(self):
        assert "ja" in SUPPORTED_LOCALES
        assert "en" in SUPPORTED_LOCALES

    def test_is_frozenset(self):
        assert isinstance(SUPPORTED_LOCALES, frozenset)


# ── translate_detail 基本動作 ──────────────────────────────────

class TestTranslateDetailBasic:
    def _detail(self):
        obj = Item(name="A", score=-1, code="bad", tier="platinum")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        return exc_info.value.detail

    def test_returns_new_list(self):
        """元の detail を変更しないこと。"""
        detail = self._detail()
        original_messages = [i["message"] for i in detail]
        translate_detail(detail, locale="en")
        # 元が変わっていない
        assert [i["message"] for i in detail] == original_messages

    def test_length_unchanged(self):
        detail = self._detail()
        assert len(translate_detail(detail, "en")) == len(detail)
        assert len(translate_detail(detail, "ja")) == len(detail)

    def test_non_message_keys_preserved(self):
        """field / rule / received / ルール固有キーが保持されること。"""
        detail = self._detail()
        en = translate_detail(detail, "en")
        for orig, translated in zip(detail, en):
            for key in ("field", "rule", "received", "status"):
                assert translated[key] == orig[key], f"key {key!r} changed"

    def test_unknown_locale_raises(self):
        detail = self._detail()
        with pytest.raises(ValueError, match="Unsupported locale"):
            translate_detail(detail, locale="fr")

    def test_message_key_is_string(self):
        detail = self._detail()
        for issue in translate_detail(detail, "en"):
            assert isinstance(issue["message"], str)


# ── 日本語メッセージ ───────────────────────────────────────────

class TestJapanese:
    def test_min_length_ja(self):
        obj = Item(name="A", score=50, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "name", "min_length")
        assert "2" in issue["message"]
        assert "文字以上" in issue["message"]

    def test_max_length_ja(self):
        obj = Item(name="A" * 11, score=50, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "name", "max_length")
        assert "10" in issue["message"]
        assert "文字以下" in issue["message"]

    def test_min_value_ja(self):
        obj = Item(name="OK", score=-1, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "score", "min_value")
        assert "0" in issue["message"]
        assert "以上" in issue["message"]

    def test_max_value_ja(self):
        obj = Item(name="OK", score=200, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "score", "max_value")
        assert "100" in issue["message"]
        assert "以下" in issue["message"]

    def test_regex_ja(self):
        obj = Item(name="OK", score=50, code="bad", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "code", "regex")
        assert "パターン" in issue["message"] or "一致しません" in issue["message"]

    def test_one_of_ja(self):
        obj = Item(name="OK", score=50, code="ABC", tier="platinum")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        ja = translate_detail(exc_info.value.detail, "ja")
        issue = _get_issue(ja, "tier", "one_of")
        assert "いずれか" in issue["message"]


# ── 英語メッセージ ─────────────────────────────────────────────

class TestEnglish:
    def test_min_length_en(self):
        obj = Item(name="A", score=50, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "name", "min_length")
        assert "2" in issue["message"]
        assert "character" in issue["message"].lower()

    def test_max_length_en(self):
        obj = Item(name="A" * 11, score=50, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "name", "max_length")
        assert "10" in issue["message"]
        assert "character" in issue["message"].lower()

    def test_min_value_en(self):
        obj = Item(name="OK", score=-1, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "score", "min_value")
        assert "0" in issue["message"]
        assert "-1" in issue["message"]

    def test_max_value_en(self):
        obj = Item(name="OK", score=200, code="ABC", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "score", "max_value")
        assert "100" in issue["message"]
        assert "200" in issue["message"]

    def test_regex_en(self):
        obj = Item(name="OK", score=50, code="bad", tier="gold")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "code", "regex")
        assert "format" in issue["message"].lower() or "invalid" in issue["message"].lower()

    def test_one_of_en(self):
        obj = Item(name="OK", score=50, code="ABC", tier="platinum")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()
        en = translate_detail(exc_info.value.detail, "en")
        issue = _get_issue(en, "tier", "one_of")
        assert "platinum" in issue["message"]
        assert "one of" in issue["message"].lower()


# ── カスタムバリデータ ─────────────────────────────────────────

class TestCustomValidatorLocale:
    def test_custom_rule_passes_through_original_message(self):
        """カスタムバリデータは翻訳カタログにないため元のメッセージをそのまま使う。"""

        def must_start_upper(value):
            if value and not value[0].isupper():
                raise ValidationError("大文字で始まる必要があります。")

        class Named(Model):
            name = StrColumn(validators=[must_start_upper])
            class Meta:
                table_name = "named"

        obj = Named(name="alice")
        with pytest.raises(ValidationError) as exc_info:
            obj.validate()

        original_msg = exc_info.value.detail[0]["message"]

        for locale in ("ja", "en"):
            translated = translate_detail(exc_info.value.detail, locale)
            assert translated[0]["message"] == original_msg, (
                f"Custom message should pass through unchanged for locale={locale!r}"
            )
        assert translated[0]["rule"] == "custom"


# ── 直接インポートでも動くこと ─────────────────────────────────

class TestImport:
    def test_importable_from_kakaorm(self):
        from kakaorm import translate_detail, SUPPORTED_LOCALES  # noqa: F401

    def test_importable_from_kakaorm_i18n(self):
        from kakaorm.i18n import translate_detail, SUPPORTED_LOCALES  # noqa: F401
