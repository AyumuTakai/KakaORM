"""
Model クラス
============
メタクラスがクラス定義時にカラムを自動収集する。
Pydantic v2 プロトコル (__get_pydantic_core_schema__ / __get_pydantic_json_schema__)
を実装しており、FastAPI の response_model に直接指定できる。

設計のポイント:
  - モデルクラス自体がクエリのエントリポイント (User.where(...))
  - ColumnMeta が演算子オーバーロードでWhereClauseを生成
  - save() / delete() は常に await が必要 → asyncの一貫性を強制
  - _is_new フラグで INSERT / UPDATE を判別する
  - Pydantic は optional 依存。未インストールでも通常の ORM 機能は動作する
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Type, TypeVar

if TYPE_CHECKING:
    from kakaorm.query import QuerySet

from kakaorm.columns.base import Column, ColumnMeta, WhereClause
from kakaorm.columns.types import IntColumn
from kakaorm.validators import ValidationError

T = TypeVar("T", bound="Model")


class ModelMeta:
    """モデルのメタ情報コンテナ。"""

    def __init__(
        self,
        table_name: str,
        columns: dict[str, Column],
        pk_name: str = "id",
        indexes: list[tuple[str, ...]] | None = None,
    ) -> None:
        self.table_name = table_name
        self.columns = columns
        self.pk_name = pk_name
        self.indexes: list[tuple[str, ...]] = indexes or []

    @property
    def is_auto_pk(self) -> bool:
        """主キーカラムが自動採番（auto_increment）かどうか。"""
        pk_col = self.columns.get(self.pk_name)
        return pk_col is not None and getattr(pk_col, "auto_increment", False)


class AsyncORMMeta(type):
    """
    Modelのメタクラス。

    クラス定義時に:
      1. Column インスタンスを収集し _meta に保存
      2. 各 Column を ColumnMeta でラップしてクラス属性に差し替え
         → User.age は ColumnMeta インスタンスになる
      3. 暗黙の id: IntColumn(primary_key=True) を追加 (明示されていなければ)
      4. Meta.indexes から複合インデックスを収集
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "AsyncORMMeta":
        columns: dict[str, Column] = {}

        # 親クラスのカラムを継承
        for base in bases:
            if hasattr(base, "_meta"):
                columns.update(base._meta.columns)

        # このクラスで宣言されたカラムを収集
        for attr_name, value in list(namespace.items()):
            if isinstance(value, Column):
                value._name = attr_name
                columns[attr_name] = value

        # 主キーを特定 / なければ暗黙の id を追加
        pk_name = "id"
        has_pk = any(c.primary_key for c in columns.values())
        if has_pk:
            for attr_name, col in columns.items():
                if col.primary_key:
                    pk_name = attr_name
                    break
        elif name != "Model":
            id_col = IntColumn(primary_key=True, auto_increment=True, nullable=False)
            id_col._name = "id"
            columns["id"] = id_col
            namespace["id"] = id_col  # 後で ColumnMeta に変換

        cls = super().__new__(mcs, name, bases, namespace)

        # テーブル名: Meta クラスで上書き可能、デフォルトはクラス名の小文字
        table_name = name.lower()
        inner_meta = namespace.get("Meta")
        if inner_meta and hasattr(inner_meta, "table_name"):
            table_name = inner_meta.table_name

        # 複合インデックス: Meta.indexes = [("col_a", "col_b"), ...]
        indexes: list[tuple[str, ...]] = []
        if inner_meta and hasattr(inner_meta, "indexes"):
            for idx in inner_meta.indexes:
                if isinstance(idx, str):
                    indexes.append((idx,))
                else:
                    indexes.append(tuple(idx))

        cls._meta = ModelMeta(
            table_name=table_name,
            columns=columns,
            pk_name=pk_name,
            indexes=indexes,
        )

        # ColumnMeta でラップしてクラス属性に差し替え
        for col_name, col in columns.items():
            cm = ColumnMeta(col)
            cm._name = col_name
            cm._table = table_name
            setattr(cls, col_name, cm)

        return cls


class Model(metaclass=AsyncORMMeta):
    """
    すべてのモデルの基底クラス。

    使い方:
        class User(Model):
            name: str = StrColumn(nullable=False)
            age:  int = IntColumn(nullable=False)
            email: str = StrColumn(unique=True)

        # クエリ
        users = await User.where(User.age >= 20).all()
        user  = await User.get(User.id == 1)

        # 保存
        user = User(name="Alice", age=30)
        await user.save()

        # 削除
        await user.delete()

    イベントフック:
        class User(Model):
            async def before_insert(self) -> None:
                self.created_at = datetime.utcnow()

            async def after_update(self) -> None:
                print(f"User {self.id} updated")
    """

    _meta: ClassVar[ModelMeta]
    _engine: ClassVar[Any] = None  # Engine インスタンス (connect() で設定)

    def __init__(self, **kwargs: Any) -> None:
        # カラム定義にないキーを拒否
        for key in kwargs:
            if key not in self._meta.columns:
                raise TypeError(f"Unknown field: {key!r} for model {type(self).__name__}")
        self._data: dict[str, Any] = {}
        for col_name, col in self._meta.columns.items():
            val = kwargs.get(col_name, col.default)
            self._data[col_name] = val
        # DB から取得したインスタンスは False、新規生成は True
        self._is_new: bool = True

    def __repr__(self) -> str:
        pk_name = self._meta.pk_name
        pk = self._data.get(pk_name, "?")
        return f"<{type(self).__name__} {pk_name}={pk}>"

    def __getattribute__(self, name: str) -> Any:
        # _で始まる属性・クラスメソッドは通常通り返す
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        # カラム名ならインスタンスの _data から返す (ColumnMetaを返さない)
        try:
            meta = object.__getattribute__(self, "_meta")
            if name in meta.columns:
                data = object.__getattribute__(self, "_data")
                return data.get(name)
        except AttributeError:
            pass
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        elif name in self._meta.columns:
            self._data[name] = value
        else:
            object.__setattr__(self, name, value)

    # ── イベントフック（サブクラスでオーバーライド）───────────────

    async def before_insert(self) -> None:
        """INSERT 直前に呼ばれる。サブクラスでオーバーライドして使う。"""

    async def after_insert(self) -> None:
        """INSERT 完了直後に呼ばれる。"""

    async def before_update(self) -> None:
        """UPDATE 直前に呼ばれる。"""

    async def after_update(self) -> None:
        """UPDATE 完了直後に呼ばれる。"""

    async def before_delete(self) -> None:
        """DELETE 直前に呼ばれる。"""

    async def after_delete(self) -> None:
        """DELETE 完了直後に呼ばれる。"""

    # ── クラスメソッド: クエリエントリポイント ─────────────────

    @classmethod
    def where(cls: Type[T], *clauses: WhereClause) -> "QuerySet[T]":
        qs = cls.all()
        for c in clauses:
            qs = qs.where(c)
        return qs

    @classmethod
    def all(cls: Type[T]) -> "QuerySet[T]":
        from kakaorm.query import QuerySet
        return QuerySet(cls)

    @classmethod
    async def get(cls: Type[T], *clauses: WhereClause) -> T:
        """条件に一致する 1 件を返す。0 件は NotFound、複数件は MultipleResults を送出。"""
        qs = cls.all()
        for c in clauses:
            qs = qs.where(c)
        results = await qs.limit(2).execute()
        if not results:
            raise cls.NotFound(f"{cls.__name__} not found")
        if len(results) > 1:
            raise cls.MultipleResults(f"Multiple {cls.__name__} found")
        return results[0]

    @classmethod
    async def first(cls: Type[T]) -> "T | None":
        return await cls.all().first()

    @classmethod
    async def last(cls: Type[T]) -> "T | None":
        return await cls.all().last()

    @classmethod
    async def get_or_none(cls: Type[T], *clauses: WhereClause) -> "T | None":
        try:
            return await cls.get(*clauses)
        except cls.NotFound:
            return None

    @classmethod
    async def create(cls: Type[T], **kwargs: Any) -> T:
        """インスタンスを作成して即 INSERT し、DB 生成の値 (id等) を返す。"""
        instance = cls(**kwargs)
        await instance.save()
        return instance

    @classmethod
    async def get_or_create(
        cls: Type[T],
        defaults: "dict[str, Any] | None" = None,
        **lookup: Any,
    ) -> "tuple[T, bool]":
        """
        lookup フィールドで検索し、存在すれば返し、なければ作成する。

        :param defaults: 新規作成時のみ適用する追加フィールド。
        :param lookup: 検索条件（フィールド名 = 値）。
        :returns: ``(instance, created)`` のタプル。
                  ``created`` が ``True`` なら新規作成、``False`` なら既存を返した。

        例::

            author, created = await Author.get_or_create(
                email="alice@example.com",
                defaults={"name": "Alice"},
            )
        """
        from functools import reduce
        import operator

        clauses = [getattr(cls, k) == v for k, v in lookup.items()]
        clause = reduce(operator.and_, clauses) if len(clauses) > 1 else clauses[0]
        instance = await cls.get_or_none(clause)
        if instance is not None:
            return instance, False
        create_kwargs = {**lookup, **(defaults or {})}
        return await cls.create(**create_kwargs), True

    @classmethod
    async def update_or_create(
        cls: Type[T],
        defaults: "dict[str, Any] | None" = None,
        **lookup: Any,
    ) -> "tuple[T, bool]":
        """
        lookup フィールドで検索し、存在すれば ``defaults`` で更新し、なければ作成する。

        :param defaults: 更新 / 作成時に適用するフィールド。
        :param lookup: 検索条件（フィールド名 = 値）。
        :returns: ``(instance, created)`` のタプル。

        例::

            post, created = await Post.update_or_create(
                slug="hello-world",
                defaults={"title": "Hello World", "published": True},
            )
        """
        from functools import reduce
        import operator

        clauses = [getattr(cls, k) == v for k, v in lookup.items()]
        clause = reduce(operator.and_, clauses) if len(clauses) > 1 else clauses[0]
        instance = await cls.get_or_none(clause)
        if instance is None:
            create_kwargs = {**lookup, **(defaults or {})}
            return await cls.create(**create_kwargs), True
        for key, value in (defaults or {}).items():
            setattr(instance, key, value)
        await instance.save()
        return instance, False

    @classmethod
    async def truncate(cls, *, restart_identity: bool = True) -> None:
        """
        テーブルの全行を削除し、オートインクリメントシーケンスをリセットする。

        通常の ``where().delete()`` と異なり、シーケンスも初期化される。

        例::

            await User.truncate()           # 全行削除 + ID リセット
            await User.truncate(restart_identity=False)  # 全行削除のみ
        """
        if cls._engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        await cls._engine.truncate(cls, restart_identity=restart_identity)

    @classmethod
    async def bulk_create(
        cls: Type[T],
        instances: list[T],
        *,
        batch_size: int = 500,
    ) -> list[T]:
        """
        複数インスタンスを最小限の SQL で一括 INSERT する。

        通常の ``create()`` が N 件で N 回の INSERT を発行するのに対し、
        ``bulk_create()`` は ``batch_size`` 件ごとに 1 回の INSERT にまとめる。

        例::

            posts = [Post(title=f"記事{i}", views=0) for i in range(1000)]
            await Post.bulk_create(posts)
            # → INSERT INTO post (...) VALUES (...), (...), ... × 2 回

        :param instances: 未保存の Model インスタンスのリスト。
        :param batch_size: 1 回の INSERT に含める最大行数。
        :returns: id が設定された同じインスタンスのリスト。
        """
        if not instances:
            return []
        if cls._engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        for i in range(0, len(instances), batch_size):
            await cls._engine._bulk_insert(cls, instances[i : i + batch_size])
        return instances

    @classmethod
    async def bulk_update(
        cls: "Type[T]",
        instances: "list[T]",
        fields: "list[str] | None" = None,
        *,
        batch_size: int = 500,
    ) -> "list[T]":
        """
        複数インスタンスを最小限の SQL で一括 UPDATE する。

        通常の ``save()`` が N 件で N 回の UPDATE を発行するのに対し、
        ``bulk_update()`` は ``batch_size`` 件ごとにまとめて処理する。

        例::

            posts = await Post.where(Post.published == False)
            for post in posts:
                post.views = 0
            await Post.bulk_update(posts, fields=["views"])
            # → 1 回の executemany で全件更新

        :param instances: 更新済みの Model インスタンスのリスト。
        :param fields: 更新するフィールド名のリスト。None の場合は全非 PK フィールドを更新。
        :param batch_size: 1 バッチに含める最大件数。
        :returns: 同じインスタンスのリスト（in-place 更新）。
        """
        if not instances:
            return []
        if cls._engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        for i in range(0, len(instances), batch_size):
            await cls._engine._bulk_update(instances[i : i + batch_size], fields)
        return instances

    # ── インスタンスメソッド ──────────────────────────────────

    def validate(self) -> None:
        """
        カラム定義の ``validators`` を実行し、失敗があれば ``ValidationError`` を送出する。

        ``save()`` から自動的に呼ばれるが、保存前に手動で呼び出すこともできる。

        例::

            user = User(name="", age=-1)
            try:
                user.validate()
            except ValidationError as e:
                print(e.errors)
                # {"name": ["2 文字以上で入力してください。"], "age": ["0 以上の値を入力してください。"]}
        """
        errors: dict[str, list[str]] = {}
        for name, col in self._meta.columns.items():
            if not col.validators:
                continue
            value = self._data.get(name)
            for validator in col.validators:
                try:
                    validator(value)
                except ValidationError as e:
                    errors.setdefault(name, []).extend(
                        msg
                        for msgs in e.errors.values()
                        for msg in msgs
                    )
        if errors:
            raise ValidationError(errors)

    async def save(self) -> None:
        """INSERT または UPDATE を実行する。_is_new が True なら INSERT。"""
        if self._engine is None:
            raise RuntimeError("No engine connected. Call kakaorm.connect() first.")
        self.validate()
        if self._is_new:
            await self.before_insert()
            await self._engine._insert(self)
            self._is_new = False
            await self.after_insert()
        else:
            await self.before_update()
            await self._engine._update(self)
            await self.after_update()

    async def delete(self) -> None:
        """DELETE を実行する。"""
        if self._engine is None:
            raise RuntimeError("No engine connected.")
        pk_name = self._meta.pk_name
        pk_val = self._data.get(pk_name)
        if pk_val is None:
            raise ValueError("Cannot delete an unsaved model instance.")
        await self.before_delete()
        await self._engine._delete(type(self), pk_val)
        await self.after_delete()

    def to_dict(self) -> dict[str, Any]:
        """現在のフィールド値を辞書として返す。"""
        return dict(self._data)

    # ── Pydantic v2 プロトコル ────────────────────────────────

    def model_dump(
        self,
        *,
        exclude_none: bool = False,
        exclude: "set[str] | None" = None,
    ) -> "dict[str, Any]":
        """
        Pydantic 互換のシリアライズメソッド。

        例::

            user.model_dump()
            # → {"id": 1, "name": "Alice", "age": 30}

            user.model_dump(exclude_none=True)
            user.model_dump(exclude={"password"})
        """
        data = self.to_dict()
        if exclude:
            data = {k: v for k, v in data.items() if k not in exclude}
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        return data

    @classmethod
    def model_validate(cls: "Type[T]", obj: Any) -> "T":
        """
        Pydantic 互換のバリデーション・変換メソッド。
        dict・同型インスタンス・from_attributes 対応オブジェクトを受け取る。

        例::

            user = User.model_validate({"name": "Alice", "age": 30})
            user = User.model_validate(other_user)
        """
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, dict):
            known = {k: v for k, v in obj.items() if k in cls._meta.columns}
            return cls(**known)
        # from_attributes: 任意オブジェクトの属性から生成
        data = {
            col_name: getattr(obj, col_name, None)
            for col_name in cls._meta.columns
        }
        instance = cls(**data)
        instance._is_new = False
        return instance

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """
        Pydantic v2 コアスキーマ。FastAPI の response_model に直接指定できるようにする。

        - バリデーション: dict → Model インスタンスに変換
        - シリアライズ: Model インスタンス → dict (to_dict() 経由)

        例::

            @app.get("/users/{id}", response_model=User)
            async def get_user(id: int):
                return await User.get(User.id == id)
        """
        try:
            from pydantic_core import core_schema as cs
        except ImportError:
            raise ImportError(
                "Pydantic との統合には pydantic が必要です: pip install pydantic"
            )

        def _validate(v: Any) -> Any:
            if isinstance(v, cls):
                return v
            if isinstance(v, dict):
                known = {k: val for k, val in v.items() if k in cls._meta.columns}
                return cls(**known)
            # from_attributes 的な使い方
            data = {
                col_name: getattr(v, col_name, None)
                for col_name in cls._meta.columns
            }
            instance = cls(**data)
            instance._is_new = False
            return instance

        return cs.no_info_plain_validator_function(
            _validate,
            serialization=cs.plain_serializer_function_ser_schema(
                lambda v: v.to_dict(),
                info_arg=False,
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema: Any, handler: Any) -> "dict[str, Any]":
        """
        Pydantic v2 JSON スキーマ。Swagger UI / OpenAPI ドキュメントに
        カラム定義を反映させる。
        """
        from kakaorm.columns.types import (
            IntColumn, StrColumn, FloatColumn, BoolColumn,
            DateTimeColumn, DateColumn, TimeColumn, DecimalColumn, ForeignKey,
        )

        properties: dict[str, Any] = {}
        required: list[str] = []

        for col_name, col in cls._meta.columns.items():
            # カラム型 → JSON Schema 型マッピング
            if isinstance(col, (IntColumn, ForeignKey)):
                prop: dict[str, Any] = {"type": "integer"}
            elif isinstance(col, StrColumn):
                prop = {"type": "string"}
                if getattr(col, "max_length", None):
                    prop["maxLength"] = col.max_length  # type: ignore[attr-defined]
            elif isinstance(col, FloatColumn):
                prop = {"type": "number"}
            elif isinstance(col, BoolColumn):
                prop = {"type": "boolean"}
            elif isinstance(col, DateTimeColumn):
                prop = {"type": "string", "format": "date-time"}
            elif isinstance(col, DateColumn):
                prop = {"type": "string", "format": "date"}
            elif isinstance(col, TimeColumn):
                prop = {"type": "string", "format": "time"}
            elif isinstance(col, DecimalColumn):
                prop = {"type": "string", "format": "decimal"}
            else:
                prop = {}

            if col.nullable:
                prop = {"anyOf": [prop, {"type": "null"}]}

            properties[col_name] = prop

            is_required = (
                not col.nullable
                and col.default is None
                and not getattr(col, "auto_increment", False)
                and not getattr(col, "auto_now_add", False)
            )
            if is_required:
                required.append(col_name)

        result: dict[str, Any] = {
            "type": "object",
            "title": cls.__name__,
            "properties": properties,
        }
        if required:
            result["required"] = required
        return result

    # ── カスタム例外 ──────────────────────────────────────────
    class NotFound(Exception):
        pass

    class MultipleResults(Exception):
        pass
