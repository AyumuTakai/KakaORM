"""
SQL 断片の検証ヘルパー（内部モジュール）
=========================================
SQL 文字列に直接埋め込まれる値（識別子・ORDER BY 句・LIMIT 値など）を検証する。
バインドパラメータで渡せない箇所はすべてここを通すこと。

  - SQLFragment        ORM 内部が生成した信頼済み SQL 断片（str サブクラス）
  - validate_identifier テーブル名・エイリアス・CTE 名などの単一識別子
  - validate_column_ref "col" / "table.col" 形式の列参照
  - validate_order_term "col [ASC|DESC] [NULLS FIRST|LAST]" 形式の ORDER BY 項
  - validate_non_negative_int LIMIT / OFFSET / 型パラメータなどの整数
  - redact_url          接続 URL のパスワードを伏せ字にする
"""

from __future__ import annotations

import operator
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# Python の識別子と同じ規則（Unicode 文字可・先頭は数字不可）
_IDENT = r"[^\W\d]\w*"
_IDENT_RE = re.compile(_IDENT)
_COLUMN_REF_RE = re.compile(rf"{_IDENT}(?:\.{_IDENT})?")
_ORDER_TERM_RE = re.compile(
    rf"{_IDENT}(?:\.{_IDENT})?(?:\s+(?:ASC|DESC))?(?:\s+NULLS\s+(?:FIRST|LAST))?",
    re.IGNORECASE,
)
# ?password=... / &pwd=... 形式のクエリパラメータ
_QUERY_PASSWORD_RE = re.compile(r"([?&](?:password|passwd|pwd)=)[^&#]*", re.IGNORECASE)


class SQLFragment(str):
    """
    ORM 内部が生成した信頼済み SQL 断片。

    ``ColumnMeta.asc`` / ``AggFunc.desc`` などが返す。
    ``order_by()`` 等はこの型の文字列を検証なしで受け付け、
    それ以外の素の ``str`` はホワイトリスト検証する。
    """

    __slots__ = ()


def validate_identifier(name: Any, what: str) -> str:
    """単一の SQL 識別子（英数字・アンダースコア、先頭は数字以外）であることを検証する。"""
    if not isinstance(name, str) or not _IDENT_RE.fullmatch(name):
        raise ValueError(
            f"Invalid {what}: {name!r}. "
            "Only letters, digits and underscores are allowed, and it must not start with a digit."
        )
    return name


def validate_column_ref(expr: Any, what: str) -> str:
    """``col`` または ``table.col`` 形式の列参照であることを検証する。"""
    if isinstance(expr, SQLFragment):
        return expr
    if not isinstance(expr, str) or not _COLUMN_REF_RE.fullmatch(expr):
        raise ValueError(
            f"Invalid {what}: {expr!r}. "
            "Pass a column (e.g. User.name) or a plain 'column' / 'table.column' string."
        )
    return expr


def validate_order_term(term: Any) -> str:
    """ORDER BY の 1 項を検証して SQL 文字列を返す。"""
    if isinstance(term, SQLFragment):
        return term
    if hasattr(term, "_qualified"):
        # ColumnMeta をそのまま渡した場合は昇順
        return f"{term._qualified()} ASC"
    if not isinstance(term, str):
        raise TypeError(
            f"order_by() expects a column expression such as User.name.asc, got {type(term).__name__}"
        )
    if not _ORDER_TERM_RE.fullmatch(term.strip()):
        raise ValueError(
            f"Invalid order_by term: {term!r}.\n"
            "  Use a column expression: .order_by(User.name.asc, User.id.desc)\n"
            "  Plain strings must look like 'column', 'table.column', 'column DESC'.\n"
            "  Never pass unvalidated user input to order_by(); map it to a column first."
        )
    return term.strip()


def validate_non_negative_int(n: Any, what: str) -> int:
    """0 以上の整数であることを検証する（bool・文字列・float は不可）。"""
    if isinstance(n, bool):
        raise TypeError(f"{what} must be an int, got bool")
    try:
        value = operator.index(n)
    except TypeError:
        raise TypeError(
            f"{what} must be an int, got {type(n).__name__} ({n!r}). "
            f"Convert user input explicitly, e.g. int(request_value)."
        ) from None
    if value < 0:
        raise ValueError(f"{what} must be >= 0, got {value}")
    return value


def redact_url(url: Any) -> str:
    """接続 URL に含まれるパスワードを ``***`` に置き換える。"""
    text = _QUERY_PASSWORD_RE.sub(r"\1***", str(url))
    try:
        parts = urlsplit(text)
    except ValueError:
        return "<unparseable url>"
    if parts.password is None:
        return text
    userinfo = f"{parts.username}:***" if parts.username else ":***"
    host = parts.hostname or ""
    if ":" in host:  # IPv6
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{userinfo}@{host}" + (f":{port}" if port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
