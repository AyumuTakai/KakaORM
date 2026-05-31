"""
relationship — FK ナビゲーション用デスクリプタ
===============================================
モデルクラス上に宣言し、await することで関連オブジェクトをロードする。

使い方::

    class Author(Model):
        name = StrColumn(nullable=False)
        # 逆参照 (1対多)
        posts = relationship("Post", foreign_key="author_id", reverse=True)

    class Post(Model):
        author_id = ForeignKey(Author)
        # 前向き FK (多対1)
        author = relationship(Author, foreign_key="author_id")

    # 使用例
    post = await Post.get(Post.id == 1)
    author = await post.author          # → Author | None

    author = await Author.get(Author.id == 1)
    posts  = await author.posts         # → list[Post]
"""

from __future__ import annotations

from typing import Any


class RelationshipProxy:
    """
    relationship デスクリプタがインスタンスアクセス時に返すプロキシ。
    await するとクエリを実行して関連オブジェクトを返す。
    """

    def __init__(
        self,
        related_model: Any,
        fk_value: Any,
        *,
        many: bool = False,
        fk_field: str = "",
    ) -> None:
        self._related_model = related_model
        self._fk_value = fk_value
        self._many = many
        self._fk_field = fk_field

    def __await__(self):
        return self._load().__await__()

    async def _load(self) -> Any:
        model = self._resolve_model()
        if self._many:
            fk_col = getattr(model, self._fk_field)
            return await model.filter(fk_col == self._fk_value).execute()
        else:
            pk_name = model._meta.pk_name
            pk_col = getattr(model, pk_name)
            return await model.get_or_none(pk_col == self._fk_value)

    def _resolve_model(self) -> Any:
        if isinstance(self._related_model, str):
            from kakaorm.model import Model
            for sub in _all_subclasses(Model):
                if sub.__name__ == self._related_model:
                    return sub
            raise LookupError(
                f"Model {self._related_model!r} not found. "
                "Make sure it is imported before accessing this relationship."
            )
        return self._related_model

    def __repr__(self) -> str:
        return f"<RelationshipProxy many={self._many} fk={self._fk_value!r}>"


def _all_subclasses(cls: type) -> list[type]:
    result = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_subclasses(sub))
    return result


class relationship:
    """
    モデル間リレーションを宣言するデスクリプタ。

    :param related_model: 関連先モデルクラス（または文字列でのクラス名）。
    :param foreign_key:   FK カラム名。
                          前向き FK の場合はこのモデルのカラム名。
                          逆参照の場合は関連先モデルのカラム名。
    :param reverse:       True のとき 1 対多の逆参照として動作する。
    """

    def __init__(
        self,
        related_model: Any,
        *,
        foreign_key: str,
        reverse: bool = False,
    ) -> None:
        self._related_model = related_model
        self._foreign_key = foreign_key
        self._reverse = reverse
        self._name = ""

    def __set_name__(self, owner: Any, name: str) -> None:
        self._name = name

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        if self._reverse:
            pk_name = obj._meta.pk_name
            pk_val = obj._data.get(pk_name)
            return RelationshipProxy(
                self._related_model, pk_val, many=True, fk_field=self._foreign_key
            )
        else:
            fk_val = obj._data.get(self._foreign_key)
            return RelationshipProxy(self._related_model, fk_val)

    def __repr__(self) -> str:
        return (
            f"<relationship {self._related_model!r} "
            f"fk={self._foreign_key!r} reverse={self._reverse}>"
        )
