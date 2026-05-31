"""
リレーション定義 — FK ナビゲーション用デスクリプタ
====================================================
モデルクラス上に宣言し、await することで関連オブジェクトをロードする。

使い方::

    class Author(Model):
        name = StrColumn(nullable=False)
        posts    = has_many("Post",    foreign_key="author_id")
        profile  = has_one("Profile",  foreign_key="author_id")

    class Post(Model):
        author_id = ForeignKey(Author)
        author    = belongs_to(Author, foreign_key="author_id")

    post   = await Post.get(Post.id == 1)
    author = await post.author       # → Author | None

    author = await Author.get(Author.id == 1)
    posts  = await author.posts      # → list[Post]
    profile = await author.profile   # → Profile | None
"""

from __future__ import annotations

from typing import Any


class _CachedProxy:
    """
    プリフェッチ済みの値を await で即時返すプロキシ。

    ``prefetch()`` でキャッシュされたリレーション値を
    通常の ``await post.author`` と同じ記法で返す。
    """

    __slots__ = ("_value",)

    def __init__(self, value: Any) -> None:
        self._value = value

    def __await__(self):
        async def _return() -> Any:
            return self._value
        return _return().__await__()

    def __repr__(self) -> str:
        return f"<CachedProxy value={self._value!r}>"


def _check_prefetch_cache(obj: Any, name: str) -> "_CachedProxy | None":
    """
    インスタンスの _prefetch_cache にキャッシュがあれば _CachedProxy を返す。
    なければ None を返す。
    """
    try:
        cache = object.__getattribute__(obj, "_prefetch_cache")
        if name in cache:
            return _CachedProxy(cache[name])
    except AttributeError:
        pass
    return None


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
        single: bool = False,
        fk_field: str = "",
    ) -> None:
        self._related_model = related_model
        self._fk_value = fk_value
        self._many = many
        self._single = single   # has_one: True (list ではなく単体を返す)
        self._fk_field = fk_field

    def __await__(self):
        return self._load().__await__()

    async def _load(self) -> Any:
        model = self._resolve_model()
        if self._many:
            fk_col = getattr(model, self._fk_field)
            results = await model.where(fk_col == self._fk_value).execute()
            if self._single:
                return results[0] if results else None
            return results
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

    def resolve_related_model(self) -> Any:
        """関連モデルクラスを返す。文字列の場合は Model サブクラスから解決する。"""
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

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        # プリフェッチキャッシュがあれば即時返す
        cached = _check_prefetch_cache(obj, self._name)
        if cached is not None:
            return cached
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
    1対1の逆参照リレーション。関連先モデルのFKで検索し、単体を返す。

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

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        # プリフェッチキャッシュがあれば即時返す
        cached = _check_prefetch_cache(obj, self._name)
        if cached is not None:
            return cached
        pk_val = obj._data.get(obj._meta.pk_name)
        return _RelationshipProxy(
            self._related_model, pk_val, many=True, single=True, fk_field=self._foreign_key
        )

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
