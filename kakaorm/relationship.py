"""
リレーション定義 — FK ナビゲーション用デスクリプタ
====================================================
モデルクラス上に宣言し、await することで関連オブジェクトをロードする。

使い方::

    class Author(Model):
        name = StrColumn(nullable=False)
        # 1対多の逆参照
        posts = has_many("Post", foreign_key="author_id")

    class Post(Model):
        author_id = ForeignKey(Author)
        # 多対1の前向きFK
        author = belongs_to(Author, foreign_key="author_id")

    # 使用例
    post = await Post.get(Post.id == 1)
    author = await post.author          # → Author | None

    author = await Author.get(Author.id == 1)
    posts  = await author.posts         # → list[Post]
"""

from __future__ import annotations

from typing import Any


class _RelationshipProxy:
    """
    リレーション用デスクリプタがインスタンスアクセス時に返すプロキシ。
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
            return await model.where(fk_col == self._fk_value).execute()
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


class _RelationshipDescriptor:
    """リレーション定義の基底クラス。"""

    def __init__(
        self,
        related_model: Any,
        *,
        foreign_key: str,
        many: bool = False,
    ) -> None:
        self._related_model = related_model
        self._foreign_key = foreign_key
        self._many = many
        self._name = ""

    def __set_name__(self, owner: Any, name: str) -> None:
        self._name = name

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        if self._many:
            pk_name = obj._meta.pk_name
            pk_val = obj._data.get(pk_name)
            return _RelationshipProxy(
                self._related_model, pk_val, many=True, fk_field=self._foreign_key
            )
        else:
            fk_val = obj._data.get(self._foreign_key)
            return _RelationshipProxy(self._related_model, fk_val)


class has_many(_RelationshipDescriptor):
    """
    1対多の逆参照リレーション。

    :param related_model: 関連先モデルクラス（または文字列でのクラス名）。
    :param foreign_key:   関連先モデルのFKカラム名。

    例::

        class Author(Model):
            posts = has_many("Post", foreign_key="author_id")

        author = await Author.get(Author.id == 1)
        posts = await author.posts  # list[Post]
    """

    def __init__(self, related_model: Any, *, foreign_key: str) -> None:
        super().__init__(related_model, foreign_key=foreign_key, many=True)

    def __repr__(self) -> str:
        return f"<has_many {self._related_model!r} fk={self._foreign_key!r}>"


class has_one(_RelationshipDescriptor):
    """
    1対1の逆参照リレーション。

    :param related_model: 関連先モデルクラス（または文字列でのクラス名）。
    :param foreign_key:   関連先モデルのFKカラム名。

    例::

        class Author(Model):
            profile = has_one("Profile", foreign_key="author_id")

        author = await Author.get(Author.id == 1)
        profile = await author.profile  # Profile | None
    """

    def __init__(self, related_model: Any, *, foreign_key: str) -> None:
        super().__init__(related_model, foreign_key=foreign_key, many=True)

    def __repr__(self) -> str:
        return f"<has_one {self._related_model!r} fk={self._foreign_key!r}>"


class belongs_to(_RelationshipDescriptor):
    """
    多対1の前向きFKリレーション。

    :param related_model: 関連先モデルクラス（または文字列でのクラス名）。
    :param foreign_key:   このモデルのFKカラム名。

    例::

        class Post(Model):
            author_id = ForeignKey(Author)
            author = belongs_to(Author, foreign_key="author_id")

        post = await Post.get(Post.id == 1)
        author = await post.author  # Author | None
    """

    def __init__(self, related_model: Any, *, foreign_key: str) -> None:
        super().__init__(related_model, foreign_key=foreign_key, many=False)

    def __repr__(self) -> str:
        return f"<belongs_to {self._related_model!r} fk={self._foreign_key!r}>"
