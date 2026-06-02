"""
バリデーション
==============
カラム定義に ``validators=[...]`` を渡すと、
``save()`` 実行前に自動的に検証が走る。

使い方::

    from kakaorm import StrColumn, ValidationError
    from kakaorm.validators import min_length, max_length, min_value, max_value, regex

    class User(Model):
        name  = StrColumn(nullable=False, validators=[min_length(2), max_length(50)])
        age   = IntColumn(nullable=True,  validators=[min_value(0), max_value(150)])
        email = StrColumn(nullable=False, validators=[regex(r"^[^@]+@[^@]+$")])

バリデーションエラーは ``ValidationError`` で送出される。
``error.errors`` は ``{"field_name": ["メッセージ", ...], ...}`` の辞書。
"""

from __future__ import annotations

import re as _re
from typing import Any, Callable


# ── 例外 ──────────────────────────────────────────────────────

class ValidationError(Exception):
    """
    バリデーション失敗を表す例外。

    Attributes:
        errors:
            後方互換の辞書形式。``{"field": ["message", ...], ...}``
        detail:
            構造化エラーのリスト。``Model.validate()`` が組み立てる。
            各要素は以下のキーを持つ辞書::

                {
                    "status":   "validation_error",
                    "field":    "name",
                    "rule":     "min_length",
                    "message":  "2 文字以上で入力してください。",
                    "received": "",
                    "expected_min": 2,   # ルール固有の追加キー
                }

    Example::

        try:
            await user.save()
        except ValidationError as e:
            # 後方互換
            print(e.errors)
            # {"name": ["2 文字以上で入力してください。"], "age": ["..."]}}

            # 構造化
            for issue in e.detail:
                print(issue["field"], issue["rule"], issue["received"])
    """

    def __init__(
        self,
        errors: "dict[str, list[str]] | str",
        *,
        _issue: "dict | None" = None,
    ) -> None:
        if isinstance(errors, str):
            self.errors: dict[str, list[str]] = {"__all__": [errors]}
        else:
            self.errors = errors
        # 単体バリデータが付与する構造化メタデータ（model.validate() が読み取る）
        self._issue: dict | None = _issue
        # model.validate() がすべての失敗をまとめて格納する構造化リスト
        self.detail: list[dict] = []
        super().__init__(str(self.errors))


# ── バリデータファクトリ ──────────────────────────────────────
# 各関数はバリデータ（callable）を返す。
# バリデータのシグネチャ: (value: Any) -> None
# 失敗時は ValidationError(message) を送出する。

def min_length(n: int) -> Callable[[Any], None]:
    """文字列の最小文字数を検証する。"""
    def validator(value: Any) -> None:
        if value is not None and len(value) < n:
            raise ValidationError(
                f"{n} 文字以上で入力してください。",
                _issue={"rule": "min_length", "received": value, "expected_min": n},
            )
    return validator


def max_length(n: int) -> Callable[[Any], None]:
    """文字列の最大文字数を検証する。"""
    def validator(value: Any) -> None:
        if value is not None and len(value) > n:
            raise ValidationError(
                f"{n} 文字以下で入力してください。",
                _issue={"rule": "max_length", "received": value, "expected_max": n},
            )
    return validator


def min_value(n: "int | float") -> Callable[[Any], None]:
    """数値の最小値を検証する。"""
    def validator(value: Any) -> None:
        if value is not None and value < n:
            raise ValidationError(
                f"{n} 以上の値を入力してください。",
                _issue={"rule": "min_value", "received": value, "expected_min": n},
            )
    return validator


def max_value(n: "int | float") -> Callable[[Any], None]:
    """数値の最大値を検証する。"""
    def validator(value: Any) -> None:
        if value is not None and value > n:
            raise ValidationError(
                f"{n} 以下の値を入力してください。",
                _issue={"rule": "max_value", "received": value, "expected_max": n},
            )
    return validator


def regex(pattern: str, message: str | None = None) -> Callable[[Any], None]:
    """文字列が正規表現パターンに一致するか検証する。"""
    compiled = _re.compile(pattern)
    default_msg = f"値が正規表現パターン '{pattern}' に一致しません。"

    def validator(value: Any) -> None:
        if value is not None and not compiled.search(str(value)):
            raise ValidationError(
                message or default_msg,
                _issue={"rule": "regex", "received": value, "pattern": pattern},
            )
    return validator


def one_of(*choices: Any) -> Callable[[Any], None]:
    """値が指定した選択肢のいずれかであることを検証する。"""
    allowed = set(choices)

    def validator(value: Any) -> None:
        if value is not None and value not in allowed:
            raise ValidationError(
                f"値は {list(choices)} のいずれかである必要があります。",
                _issue={"rule": "one_of", "received": value, "choices": list(choices)},
            )
    return validator
