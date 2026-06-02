"""
kakaorm.i18n — バリデーションエラーのローカライズ
====================================================

``ValidationError.detail`` のメッセージを任意のロケールに翻訳する
ヘルパーを提供する。

使い方::

    from kakaorm import ValidationError
    from kakaorm.i18n import translate_detail

    try:
        await user.save()
    except ValidationError as e:
        issues = translate_detail(e.detail, locale="en")
        for issue in issues:
            print(f"[{issue['field']}] {issue['message']}")
        # [name]  Must be at least 2 characters long.
        # [age]   Must be at least 0 (got -1).
        # [email] Invalid format.

対応ロケール:
    - "ja" — 日本語（デフォルト）
    - "en" — 英語

未対応ロケールを指定すると ``ValueError`` を送出する。
未知のルール（カスタムバリデータ等）は元の ``message`` をそのまま保持する。
"""

from __future__ import annotations

from typing import Any

# ── メッセージカタログ ─────────────────────────────────────────
# 各エントリは issue dict を受け取り、翻訳済みメッセージ文字列を返す callable。
# issue に含まれるキー: field, rule, received, + ルール固有キー
# (expected_min, expected_max, pattern, choices など)

_CATALOG: dict[str, dict[str, Any]] = {
    "ja": {
        "min_length": lambda i: f"{i['expected_min']} 文字以上で入力してください。",
        "max_length": lambda i: f"{i['expected_max']} 文字以下で入力してください。",
        "min_value":  lambda i: f"{i['expected_min']} 以上の値を入力してください。",
        "max_value":  lambda i: f"{i['expected_max']} 以下の値を入力してください。",
        "regex":      lambda i: f"値が正規表現パターン '{i['pattern']}' に一致しません。",
        "one_of":     lambda i: f"値は {i['choices']} のいずれかである必要があります。",
    },
    "en": {
        "min_length": lambda i: f"Must be at least {i['expected_min']} character(s) long.",
        "max_length": lambda i: f"Must be at most {i['expected_max']} character(s) long.",
        "min_value":  lambda i: f"Must be at least {i['expected_min']} (got {i['received']}).",
        "max_value":  lambda i: f"Must be at most {i['expected_max']} (got {i['received']}).",
        "regex":      lambda i: "Invalid format.",
        "one_of":     lambda i: f"Must be one of {i['choices']} (got {i['received']!r}).",
    },
}

#: 対応ロケールの集合。
SUPPORTED_LOCALES: frozenset[str] = frozenset(_CATALOG.keys())


def translate_detail(
    detail: list[dict],
    locale: str = "ja",
) -> list[dict]:
    """
    ``ValidationError.detail`` のメッセージを指定ロケールに翻訳した
    新しいリストを返す。

    元の ``detail`` は変更しない（イミュータブル）。
    未知のルール（カスタムバリデータ等）は元の ``message`` をそのまま保持する。

    Args:
        detail: ``ValidationError.detail`` をそのまま渡す。
        locale: 翻訳先ロケール。``"ja"``（デフォルト）または ``"en"``。

    Returns:
        ``message`` キーが翻訳済みの新しい dict のリスト。
        その他のキー（``field``, ``rule``, ``received``, ルール固有キー）は保持する。

    Raises:
        ValueError: 未対応のロケールを指定した場合。

    Example::

        from kakaorm.i18n import translate_detail

        try:
            await user.save()
        except ValidationError as e:
            en_issues = translate_detail(e.detail, locale="en")
            # FastAPI レスポンスに使う場合
            raise HTTPException(422, detail=en_issues)
    """
    if locale not in _CATALOG:
        raise ValueError(
            f"Unsupported locale {locale!r}. "
            f"Supported locales: {sorted(SUPPORTED_LOCALES)}"
        )

    catalog = _CATALOG[locale]
    result: list[dict] = []

    for issue in detail:
        rule = issue.get("rule", "custom")
        if rule in catalog:
            translated = catalog[rule](issue)
        else:
            # カスタムバリデータや将来追加されるルールは元のメッセージをそのまま使う
            translated = issue.get("message", "")

        result.append({**issue, "message": translated})

    return result
