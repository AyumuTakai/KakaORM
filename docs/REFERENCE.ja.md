# KakaORM — API リファレンス

[English](https://github.com/AyumuTakai/KakaORM/blob/main/docs/REFERENCE.md) | [← README](https://github.com/AyumuTakai/KakaORM/blob/main/README.ja.md)

---

## カラム型 — 共通オプション

```python
StrColumn(
    nullable=True,       # NULL 許可 (デフォルト: True)
    default=None,        # デフォルト値
    unique=False,        # UNIQUE 制約
    primary_key=False,   # 主キー
    index=False,         # 単一カラムインデックス
    check="value > 0",   # CHECK 制約
)
StrColumn(max_length=255)          # → VARCHAR(255)
IntColumn(auto_increment=True)     # → SERIAL PRIMARY KEY (PG) / AUTOINCREMENT (SQLite)
DateTimeColumn(auto_now_add=True)  # INSERT 時に現在時刻を自動設定
DateTimeColumn(auto_now=True)      # UPDATE 時に現在時刻を自動更新
ForeignKey(Author, on_delete="CASCADE")    # デフォルト: CASCADE
ForeignKey(Author, on_delete="SET NULL")   # 参照元を NULL にする
ForeignKey(Author, on_delete="RESTRICT")   # 削除を禁止
ForeignKey(Author, on_delete="NO ACTION")  # DB デフォルト動作
DecimalColumn(max_digits=10, decimal_places=2)  # NUMERIC(10, 2)
```

### カラム型の選び方

どの型を使うか迷ったときはこのガイドを参照してください。

**数値**

| 状況 | 使うべき型 |
|---|---|
| 整数 ID・カウント・フラグ | `IntColumn` |
| 価格・通貨・金融計算 | `DecimalColumn` — `FloatColumn` は浮動小数点誤差が蓄積するため不可 |
| 科学的計測・多少の丸め誤差が許容できるスコア | `FloatColumn` |

```python
# ✅ 正しい — 正確な十進演算
price    = DecimalColumn(max_digits=10, decimal_places=2)
tax_rate = DecimalColumn(max_digits=5,  decimal_places=4)

# ❌ 誤り — 浮動小数点では 0.1 + 0.2 ≠ 0.3 になることがある
price = FloatColumn()
```

**文字列**

| 状況 | 使うべき型 |
|---|---|
| 長さ不定のテキスト（本文・自己紹介・メモ） | `StrColumn()` → TEXT |
| 長さが決まっている入力（名前・スラッグ・コード） | `StrColumn(max_length=n)` → VARCHAR(n) |

```python
title   = StrColumn(max_length=200)   # VARCHAR(200) — DB レベルで長さを強制
content = StrColumn()                  # TEXT — 長さ制限なし
```

**日付・時刻**

| 状況 | 使うべき型 |
|---|---|
| タイムゾーン付き完全タイムスタンプ（created_at・イベント日時） | `DateTimeColumn` |
| 日付のみ、時刻不要（誕生日・期日） | `DateColumn` |
| 時刻のみ、日付不要（営業時間・スケジュール） | `TimeColumn` |

```python
created_at = DateTimeColumn(auto_now_add=True)  # UTC datetime
birthday   = DateColumn(nullable=True)           # 日付のみ
opens_at   = TimeColumn(nullable=True)           # 時刻のみ
```

**リレーション**

```python
# ✅ ForeignKey を使う — 参照整合性の強制と ON DELETE を自動処理
author_id = ForeignKey(Author, on_delete="CASCADE")

# ❌ 生の IntColumn は避ける — 制約なし、DDL のクォートも行われない
author_id = IntColumn()
```

**nullable の使い分け**

デフォルトは `nullable=True`（NULL 許可）です。値が必須のフィールドにだけ `nullable=False` を指定してください。

```python
name = StrColumn(nullable=False)   # 必須 — SQL で NOT NULL
bio  = StrColumn(nullable=True)    # 任意 — NULL を許可
```

> KakaORM のデフォルトは Django とは逆です（Django は `blank=False` がデフォルト）。
> Django 出身のチームは `nullable=False` の設定漏れに注意してください。

---

### DateTimeColumn — タイムスタンプ自動設定

`auto_now_add` / `auto_now` を使うと、現在の UTC 時刻が自動で挿入されます。

| オプション | 発火タイミング | 明示的な値で上書き可能？ |
|---|---|---|
| `auto_now_add=True` | INSERT のみ | 不可 — 常に `now()` が使われる |
| `auto_now=True` | UPDATE のたび | 不可 — 常に `now()` が使われる |

```python
class Post(Model):
    created_at = DateTimeColumn(auto_now_add=True, nullable=False)
    updated_at = DateTimeColumn(auto_now=True,     nullable=True)
```

- `bulk_create()` / `bulk_update()` でも正しく動作します（v0.4.3 以降）。
- `nullable=False` + `auto_now_add=True` の組み合わせは安全です。Migrator が `ADD COLUMN` 時に
  DB 側デフォルト値（PostgreSQL/MySQL: `CURRENT_TIMESTAMP`、SQLite: `'1970-01-01 00:00:00'`）を
  自動的に付与するため、既存行がエラーになりません。
- DB に保存される値は ISO 形式の文字列です。読み出し時に `from_db()` が自動的に
  `datetime` オブジェクトに変換します。

---

## バリデーション

カラム定義にバリデータを付与します。`save()` は INSERT / UPDATE の前に自動的にバリデータを実行します。失敗した場合は `ValidationError` を送出し、DB には何も書き込まれません。

```python
from kakaorm import Model, StrColumn, IntColumn, ValidationError
from kakaorm.validators import min_length, max_length, min_value, max_value, regex, one_of

class User(Model):
    name  = StrColumn(nullable=False, validators=[min_length(2), max_length(50)])
    age   = IntColumn(nullable=True,  validators=[min_value(0), max_value(150)])
    email = StrColumn(nullable=False, validators=[
        regex(r"^[^@]+@[^@]+\.[^@]+$", message="有効なメールアドレスを入力してください。")
    ])
    role  = StrColumn(nullable=True,  validators=[one_of("admin", "user", "guest")])

    class Meta:
        table_name = "user"
```

### エラーの捕捉

`ValidationError` は同じ失敗を 2 つの形式で参照できます:

| 属性 | 型 | 用途 |
|---|---|---|
| `e.errors` | `dict[str, list[str]]` | 後方互換のフィールド → メッセージ辞書 |
| `e.detail` | `list[dict]` | 構造化エントリ（失敗 1 件につき 1 要素） |

```python
user = User(name="A", age=-5, email="bad")
try:
    await user.save()
except ValidationError as e:
    # ── 従来形式（後方互換） ───────────────────────────────────
    print(e.errors)
    # {
    #   "name":  ["2 文字以上で入力してください。"],
    #   "age":   ["0 以上の値を入力してください。"],
    #   "email": ["有効なメールアドレスを入力してください。"],
    # }

    # ── 構造化形式 ────────────────────────────────────────────
    for issue in e.detail:
        print(issue)
    # {"status": "validation_error", "field": "name",  "rule": "min_length",
    #  "message": "2 文字以上で入力してください。", "received": "A", "expected_min": 2}
    # {"status": "validation_error", "field": "age",   "rule": "min_value",
    #  "message": "0 以上の値を入力してください。", "received": -5, "expected_min": 0}
    # {"status": "validation_error", "field": "email", "rule": "regex",
    #  "message": "...", "received": "bad", "pattern": "^[^@]+@[^@]+\\.[^@]+$"}
```

全フィールドのエラーを一度に収集するため、1 回の例外で全ての問題が分かります。

#### 構造化エントリのキー一覧

`e.detail` の各要素には以下のキーが必ず含まれます:

| キー | 値 |
|---|---|
| `status` | 常に `"validation_error"` |
| `field` | カラム名（例: `"name"`） |
| `rule` | バリデータ名または `"custom"` |
| `message` | 人間が読めるエラーメッセージ |
| `received` | バリデーションに失敗した実際の値 |

組み込みバリデータはルール固有のキーを追加します:

| ルール | 追加キー |
|---|---|
| `min_length` | `expected_min` |
| `max_length` | `expected_max` |
| `min_value` | `expected_min` |
| `max_value` | `expected_max` |
| `regex` | `pattern` |
| `one_of` | `choices` |

#### FastAPI との統合

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from kakaorm import ValidationError

@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.detail})
```

### エラーメッセージのローカライズ

`translate_detail()` で `e.detail` のメッセージを任意のロケールに変換できます。
元の `detail` リストは変更されません（新しいリストを返します）。

```python
from kakaorm.i18n import translate_detail, SUPPORTED_LOCALES

print(SUPPORTED_LOCALES)  # frozenset({"ja", "en"})

try:
    await user.save()
except ValidationError as e:
    issues = translate_detail(e.detail, locale="en")
    for issue in issues:
        print(f"[{issue['field']}] {issue['message']}")
    # [name]  Must be at least 2 characters long.
    # [score] Must be at least 0 (got -1).
    # [email] Invalid format.
    # [role]  Must be one of ['admin', 'user'] (got 'superuser').
```

**ロケール別メッセージ一覧:**

| ルール | `ja` | `en` |
|---|---|---|
| `min_length(n)` | n 文字以上で入力してください。 | Must be at least n character(s) long. |
| `max_length(n)` | n 文字以下で入力してください。 | Must be at most n character(s) long. |
| `min_value(n)` | n 以上の値を入力してください。 | Must be at least n (got {received}). |
| `max_value(n)` | n 以下の値を入力してください。 | Must be at most n (got {received}). |
| `regex(p)` | 値が正規表現パターン 'p' に一致しません。 | Invalid format. |
| `one_of(...)` | 値は [...] のいずれかである必要があります。 | Must be one of [...] (got {received}). |
| custom | *(元のメッセージをそのまま使用)* | *(元のメッセージをそのまま使用)* |

**FastAPI で `Accept-Language` ヘッダーに応じて動的切り替えする例:**

```python
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    lang = request.headers.get("Accept-Language", "ja")[:2]
    locale = lang if lang in SUPPORTED_LOCALES else "ja"
    return JSONResponse(status_code=422, content={"detail": translate_detail(exc.detail, locale)})
```

### 手動バリデーション

DB に触れずに `validate()` を直接呼び出すこともできます:

```python
user = User(name="Alice", age=30, email="alice@example.com")
user.validate()  # 問題があれば即座に ValidationError を送出
```

### ビルトインバリデータ

| バリデータ | チェック内容 |
|---|---|
| `min_length(n)` | `len(value) >= n` |
| `max_length(n)` | `len(value) <= n` |
| `min_value(n)` | `value >= n` |
| `max_value(n)` | `value <= n` |
| `regex(pattern, message=None)` | `re.search(pattern, value)` |
| `one_of(*choices)` | `value in choices` |

いずれも `None` 値はスキップします（存在チェックには `nullable=False` を使用してください）。

### カスタムバリデータ

`(value: Any) -> None` のシグネチャを持つ callable であればバリデータとして使えます。失敗時は `ValidationError` を送出してください:

```python
from kakaorm.validators import ValidationError

def no_spaces(value):
    if value and " " in value:
        raise ValidationError("ユーザー名にスペースは使用できません。")

class User(Model):
    username = StrColumn(nullable=False, validators=[no_spaces])
```

---

## イベントフック

`save()` / `delete()` の前後に任意の処理を差し込めます。Model を継承したクラスでメソッドをオーバーライドするだけです。

```python
import datetime
from kakaorm import Model, StrColumn, IntColumn, DateTimeColumn

class Article(Model):
    title      = StrColumn(nullable=False)
    version    = IntColumn(nullable=False, default=0)
    updated_at = DateTimeColumn(nullable=True)

    async def before_insert(self) -> None:
        # INSERT 直前: タイムスタンプを自動設定
        self.updated_at = datetime.datetime.utcnow()

    async def before_update(self) -> None:
        # UPDATE 直前: バージョンをインクリメント
        self.version = (self.version or 0) + 1
        self.updated_at = datetime.datetime.utcnow()

    async def after_delete(self) -> None:
        # DELETE 完了後: ログ出力など
        print(f"Article deleted: {self.title}")
```

利用可能なフック:

| フック            | タイミング           |
| ----------------- | -------------------- |
| `before_insert`   | `save()` (INSERT 前) |
| `after_insert`    | `save()` (INSERT 後) |
| `before_update`   | `save()` (UPDATE 前) |
| `after_update`    | `save()` (UPDATE 後) |
| `before_delete`   | `delete()` 前        |
| `after_delete`    | `delete()` 後        |

> `QuerySet.update()` / `QuerySet.delete()` はフックを経由しません。

---

## リレーション定義

`has_many()` / `has_one()` / `belongs_to()` で FK を通じた関連オブジェクトの取得を宣言的に記述できます。`await` するまでクエリは発行されません。

```python
from kakaorm import Model, StrColumn, ForeignKey, has_many, belongs_to

class Author(Model):
    name  = StrColumn(nullable=False)
    # 1対多の逆参照
    posts = has_many("Post", foreign_key="author_id")

    class Meta:
        table_name = "author"

class Post(Model):
    title     = StrColumn(nullable=False)
    author_id = ForeignKey(Author, nullable=True)
    # 多対1の前向き FK
    author = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "post"

# 使用例
post   = await Post.get(Post.id == 1)
author = await post.author          # → Author | None

author = await Author.get(Author.id == 1)
posts  = await author.posts         # → list[Post]
```

### リレーションの種類

| メソッド | 用途 | 戻り値 |
|----------|------|--------|
| `has_many()` | 1対多の逆参照 | `list[Model]` |
| `has_one()` | 1対1の逆参照（FK は相手側） | `Model \| None` |
| `belongs_to()` | 多対1の前向き FK | `Model \| None` |

`related_model` には文字列でクラス名を渡すことも可能です（循環 import 回避）。

```python
posts = has_many("Post", foreign_key="author_id")
```

**`has_one()` の使用例** — 著者と 1 対 1 で対応するプロフィール:

```python
from kakaorm import Model, StrColumn, IntColumn, ForeignKey, has_one, belongs_to

class Author(Model):
    name    = StrColumn(nullable=False)
    profile = has_one("Profile", foreign_key="author_id")  # FK は Profile 側

    class Meta:
        table_name = "author"

class Profile(Model):
    bio       = StrColumn(nullable=True)
    author_id = ForeignKey(Author, nullable=False)
    author    = belongs_to(Author, foreign_key="author_id")

    class Meta:
        table_name = "profile"

author  = await Author.get(Author.id == 1)
profile = await author.profile   # → Profile | None（author_id == author.id で検索）
```

### Eager loading（N+1 解消）

`prefetch()` を使うと、関連モデルを 1 クエリで一括取得してキャッシュします。

```python
# N+1 あり（デフォルト）
posts = await Post.all()
for post in posts:
    author = await post.author  # 投稿ごとに SELECT が走る

# N+1 解消: prefetch で一括取得
posts = await Post.all().prefetch("author")
for post in posts:
    author = await post.author  # キャッシュから返す（追加クエリなし）

# 複数のリレーションを同時にプリフェッチ
authors = await Author.all().prefetch("posts", "profile")
```

パフォーマンス比較:

| ケース | レコード数 | SQL クエリ数 |
|--------|-----------|-------------|
| prefetch なし | 10 | 11 (1 + 10) |
| prefetch なし | 100 | 101 (1 + 100) |
| prefetch あり | 10 | 2 |
| prefetch あり | 100 | 2 |

---

## QuerySet — クエリビルダ

`where()` などのメソッドは `QuerySet` を返します。`await` するまで SQL は実行されません。

```python
# 絞り込み (AND)
posts = await Post.where(Post.published == True).where(Post.views >= 100)

# 複合条件
posts = await Post.where(
    (Post.published == True) & (Post.views >= 100)
)

# OR / NOT
clause = (Post.views < 10) | (Post.published == False)
posts  = await Post.where(~clause)

# ソート・ページネーション
posts = await (
    Post.where(Post.published == True)
        .order_by(Post.views.desc)
        .limit(10)
        .offset(20)
)

# 特定カラムのみ SELECT（既存 SELECT を置換）
rows = await Post.all().select(Post.title, Post.views)

# 既存の SELECT に列を追加（置換しない）
base  = Post.all().select(Post.id, Post.title)
rows  = await base.also_select(Post.views, Post.author_id)
# → SELECT id, title, views, author_id FROM post

# COUNT / EXISTS
n      = await Post.where(Post.published == True).count()
exists = await Post.where(Post.title.like("%Python%")).exists()

# 非同期イテレーション（QuerySet は async for に対応）
async for post in Post.all().order_by(Post.views.desc):
    print(post.title)
```

### WHERE 演算子一覧

```python
Post.views == 100          # =
Post.views != 100          # !=
Post.views >= 100          # >=
Post.views >  100          # >
Post.views <= 100          # <=
Post.views <  100          # <
Post.score == None         # IS NULL
Post.score != None         # IS NOT NULL
Post.title.like("A%")      # LIKE
Post.title.ilike("a%")     # ILIKE
Post.views.in_([1, 2, 3])  # IN
Post.views.not_in([1, 2])  # NOT IN
Post.score.between(1, 5)   # BETWEEN
Post.score.is_null()       # IS NULL  (== None と同等)
Post.score.is_not_null()   # IS NOT NULL  (!= None と同等)
```

### 論理演算子

比較演算子が返す `WhereClause` を `&`（AND）・`|`（OR）・`~`（NOT）で組み合わせることで、複雑な条件を型安全に構築できます。

| 演算子 | SQL | 使い方 |
|--------|-----|--------|
| `&` | `AND` | `clause_a & clause_b` |
| `\|` | `OR` | `clause_a \| clause_b` |
| `~` | `NOT` | `~clause` |
| `.where().where()` | `AND` | メソッドチェーン |
| `.exclude(clause)` | `NOT (clause)` | 否定条件の糖衣構文 |

```python
# AND: & 演算子
posts = await Post.where(
    (Post.published == True) & (Post.views >= 100)
)
# WHERE (published = ?) AND (views >= ?)

# OR: | 演算子
posts = await Post.where(
    (Post.published == True) | (Post.author_id == 1)
)
# WHERE (published = ?) OR (author_id = ?)

# NOT: ~ 演算子
posts = await Post.where(~(Post.published == False))
# WHERE NOT (published = ?)

# AND チェーン: .where().where()
posts = await (
    Post.where(Post.published == True)
        .where(Post.views >= 100)
)
# WHERE (published = ?) AND (views >= ?)
# ※ .where() を重ねると常に AND で結合されます

# exclude: NOT の糖衣構文
posts = await Post.all().exclude(Post.published == False)
# WHERE NOT (published = ?)

# 複雑な組み合わせ
posts = await Post.where(
    (Post.published == True) &
    ((Post.views >= 1000) | (Post.author_id.in_([1, 2, 3]))) &
    ~Post.title.like("%draft%")
)
# WHERE (published = ?)
#   AND ((views >= ?) OR (author_id IN (?,?,?)))
#   AND NOT (title LIKE ?)
```

> **優先順位** — Python の演算子優先順位に従い、`~` が最も強く、`&` が `|` より強く結合します。
> 意図通りの条件になるよう、複合条件には括弧を付けることを推奨します。

### JOIN / GROUP BY / 集計

```python
from kakaorm import Count, Sum, Avg

# INNER JOIN
rows = await (
    Post.where(Post.published == True)
        .join(Author, on=Post.author_id == Author.id)
        .select(Post.title, Author.name)
)

# LEFT JOIN
rows = await (
    Author.all()
        .left_join(Post, on=Post.author_id == Author.id)
        .select(Author.name, Count(Post.id).label("post_count"))
        .group_by(Author.id, Author.name)
)

# RIGHT JOIN
rows = await (
    Post.all()
        .right_join(Author, on=Post.author_id == Author.id)
        .select(Post.title, Author.name)
)

# サブクエリ（IN / NOT IN）
from kakaorm import Subquery

active_authors = Author.where(Author.is_active == True).select(Author.id)
posts = await Post.where(Post.author_id.in_(Subquery(active_authors)))
# WHERE author_id IN (SELECT id FROM author WHERE is_active = ?)

# QuerySet をそのまま渡しても同じ動作をする
posts = await Post.where(Post.author_id.in_(active_authors))

# 集計
total = await Post.all().sum(Post.views)
stats = await Post.all().aggregate(
    total=Sum(Post.views),
    avg=Avg(Post.views),
)

# GROUP BY / HAVING
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .having(Count(Post.id) >= 2)
)
```

### 集計関数

#### クイック集計メソッド

`QuerySet` には単一集計を返すショートカットメソッドが用意されています。

```python
# 件数
n = await Post.all().count()                            # COUNT(*)
n = await Post.where(Post.published == True).count()    # WHERE 付き

# 合計・平均・最大・最小
total = await Post.all().sum(Post.views)
avg   = await Post.all().avg(Post.score)
hi    = await Post.all().max(Post.views)
lo    = await Post.all().min(Post.score)

# 存在確認
has_draft = await Post.where(Post.published == False).exists()  # bool
```

#### aggregate() — 複数集計の一括実行

1 回の SQL で複数の集計値を同時に取得します。

```python
from kakaorm import Sum, Avg, Max, Min, Count

stats = await Post.all().aggregate(
    total_views = Sum(Post.views),
    avg_score   = Avg(Post.score),
    max_views   = Max(Post.views),
    post_count  = Count(Post.id),
)
# {
#   "total_views": 12500,
#   "avg_score": 3.8,
#   "max_views": 2000,
#   "post_count": 42
# }

# WHERE フィルタとの組み合わせ
stats = await Post.where(Post.published == True).aggregate(
    published_views = Sum(Post.views),
    published_count = Count(Post.id),
)
```

#### SELECT での集計式

`select()` に集計クラスを渡すと、任意のカラムと集計値を混在させた行を取得できます。`.label()` で結果のキー名を指定します。

| クラス | SQL 関数 | 引数 |
|--------|----------|------|
| `Count(col)` | `COUNT(col)` | カラム省略で `COUNT(*)` |
| `Sum(col)` | `SUM(col)` | カラム必須 |
| `Avg(col)` | `AVG(col)` | カラム必須 |
| `Max(col)` | `MAX(col)` | カラム必須 |
| `Min(col)` | `MIN(col)` | カラム必須 |

```python
from kakaorm import Count, Sum, Avg

rows = await (
    Post.all()
        .select(
            Post.author_id,
            Count(Post.id).label("post_count"),
            Sum(Post.views).label("total_views"),
            Avg(Post.score).label("avg_score"),
        )
        .group_by(Post.author_id)
)
# [
#   {"author_id": 1, "post_count": 3, "total_views": 3600, "avg_score": 4.0},
#   {"author_id": 2, "post_count": 1, "total_views":  100, "avg_score": 3.5},
# ]
```

#### GROUP BY / HAVING

`.group_by()` でグループ化し、`.having()` で集計後の絞り込みを行います。
`having()` には集計クラスの比較演算子（`==`, `!=`, `>`, `>=`, `<`, `<=`）が使えます。

```python
from kakaorm import Count, Sum

# 投稿が 2 件以上ある著者を取得
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .having(Count(Post.id) >= 2)
)

# 合計ビュー数 1000 以上かつ投稿が 3 件以上の著者
rows = await (
    Post.all()
        .select(Post.author_id, Sum(Post.views).label("views"))
        .group_by(Post.author_id)
        .having(Sum(Post.views) >= 1000)
        .having(Count(Post.id) >= 3)     # .having() を重ねると AND で結合
)

# 集計結果でソート
rows = await (
    Post.all()
        .select(Post.author_id, Count(Post.id).label("cnt"))
        .group_by(Post.author_id)
        .order_by(Count(Post.id).desc)
)
```

### ウィンドウ関数

`OVER (PARTITION BY ... ORDER BY ...)` 句を生成するクラスが用意されています。
ウィンドウ関数は `SELECT` 句にのみ使用できます（`WHERE` / `HAVING` 不可）。

```python
from kakaorm import RowNumber, Rank, DenseRank, Lag, Lead, Sum, Avg

# 著者ごとの投稿順位
rows = await Post.all().select(
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views],          # 昇順
    ).label("row_num"),
)

# 全体ランキング（同率あり）
rows = await Post.all().select(
    Post.title,
    Post.views,
    Rank().over(order_by=[Post.views]).label("rank"),
    DenseRank().over(order_by=[Post.views]).label("dense_rank"),
)

# 1 つ前の行の views を取得（LAG）
rows = await Post.all().select(
    Post.title,
    Post.views,
    Lag(Post.views, 1, 0).over(order_by=[Post.views]).label("prev_views"),
)

# 1 つ後の行の views を取得（LEAD）
rows = await Post.all().select(
    Post.title,
    Post.views,
    Lead(Post.views, 1, 0).over(order_by=[Post.views]).label("next_views"),
)

# 累積合計（SUM OVER）
rows = await Post.all().select(
    Post.title,
    Post.views,
    Sum(Post.views).over(
        partition_by=[Post.author_id],
        order_by=[Post.views],
    ).label("cumulative_views"),
)
```

利用可能なウィンドウ関数クラス:

| クラス | SQL | 説明 |
|--------|-----|------|
| `RowNumber()` | `ROW_NUMBER()` | 連続した一意の行番号 |
| `Rank()` | `RANK()` | 同率同順位・次は飛ばす |
| `DenseRank()` | `DENSE_RANK()` | 同率同順位・次は飛ばさない |
| `Lag(col, n, default)` | `LAG(col, n, default)` | n 行前の値 |
| `Lead(col, n, default)` | `LEAD(col, n, default)` | n 行後の値 |
| `Sum(col).over(...)` | `SUM(col) OVER (...)` | 累積合計 |
| `Avg(col).over(...)` | `AVG(col) OVER (...)` | 移動平均 |
| `Max(col).over(...)` | `MAX(col) OVER (...)` | ウィンドウ最大値 |
| `Min(col).over(...)` | `MIN(col) OVER (...)` | ウィンドウ最小値 |

> **注意** ウィンドウ関数は SQLite ではサポートされていません。PostgreSQL・MySQL 8.0+・MariaDB 10.2+ で使用してください。

#### よく使うパターン

**グループ内 Top-N** — 著者ごとに閲覧数上位 3 件を取得する:

```python
from kakaorm import RowNumber

# 各投稿に著者内でのランクを付ける
ranked = await Post.all().select(
    Post.id,
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views.desc],   # 閲覧数が多い順 → rank 1
    ).label("rn"),
)

# Python 側でフィルタ（または CTE と組み合わせる）
top3 = [r for r in ranked if r["rn"] <= 3]
```

**移動平均** — 日別売上の 7 日間移動平均:

```python
from kakaorm import Avg

rows = await Sale.all().select(
    Sale.date,
    Sale.amount,
    Avg(Sale.amount).over(
        order_by=[Sale.date],
    ).label("moving_avg"),
).order_by(Sale.date)
```

**前期比較** — 当月と前月の売上を並べて表示:

```python
from kakaorm import Lag

rows = await MonthlyRevenue.all().select(
    MonthlyRevenue.month,
    MonthlyRevenue.revenue,
    Lag(MonthlyRevenue.revenue, 1, 0).over(
        order_by=[MonthlyRevenue.month],
    ).label("prev_revenue"),
).order_by(MonthlyRevenue.month)

# revenue - prev_revenue が前月比増減
```

### CTE（WITH 句）

CTE はサブクエリに名前を付けてメインクエリから参照する機能です。複雑なクエリを段階的に組み立てるときに可読性が上がります。

```python
# 高給社員がいる部署を CTE で定義して JOIN する
high_earners = (
    Employee.where(Employee.salary >= 1000)
            .select(Employee.dept_id)
)
rows = await (
    Department.all()
              .with_cte("rich_depts", high_earners)
              .join(Employee, on=Employee.dept_id == Department.id)
              .select(Department.name, Employee.name)
              .where(Employee.salary >= 1000)
)
```

#### よく使うパターン

**CTE + ウィンドウ関数でグループ内 Top-N**:

```python
from kakaorm import RowNumber

# CTE: 各投稿にランクを付ける
ranked_posts = Post.all().select(
    Post.id,
    Post.title,
    Post.author_id,
    Post.views,
    RowNumber().over(
        partition_by=[Post.author_id],
        order_by=[Post.views.desc],
    ).label("rn"),
)

# メインクエリ: ランク 3 以内のみ取得
top3 = await (
    Post.all()
        .with_cte("ranked", ranked_posts)
        .join_raw("ranked", on="post.id = ranked.id")
        .select(Post.title, Post.author_id, Post.views)
        .where_raw("ranked.rn <= 3")
)
```

**サブクエリの再利用** — 重いサブクエリを CTE にまとめて一度だけ計算させる:

```python
# アクティブユーザーの ID を CTE 化
active_users = User.where(User.is_active == True).select(User.id)

results = await (
    Order.all()
         .with_cte("actives", active_users)
         .join_raw("actives", on="order.user_id = actives.id")
         .select(Order.id, Order.total)
         .order_by(Order.total.desc)
         .limit(100)
)
```

**集計してからフィルタ** — ユーザーごとの合計購入額が高い顧客を取得:

```python
from kakaorm import Sum

# CTE: ユーザーごとの合計購入額
user_totals = (
    Order.all()
         .select(Order.user_id, Sum(Order.total).label("total_spend"))
         .group_by(Order.user_id)
)

# 合計 10,000 以上のユーザーを取得
vip_customers = await (
    User.all()
        .with_cte("totals", user_totals)
        .join_raw("totals", on="user.id = totals.user_id")
        .select(User.name, User.email)
        .where_raw("totals.total_spend >= 10000")
)
```

### UPDATE 式 (列参照)

```python
# 固定値
await Post.all().update(published=True)

# 列参照を含む式
await Post.all().update(views=Post.views + 1)
await Product.all().update(price=Product.price * 0.97)
```

### CASE WHEN 式

`Case` と `When` を使って SQL の `CASE WHEN ... THEN ... ELSE ... END` を表現します。
`select()` の列指定と `update()` の SET 値の両方で使えます。

```python
from kakaorm import Case, When

# SELECT での使用: 年齢カテゴリをラベルとして取得
rows = await User.all().select(
    User.id,
    User.name,
    Case(
        When(User.age >= 18, then="adult"),
        When(User.age >= 13, then="teen"),
        default="child",
    ).label("category"),
)
# → [{"id": 1, "name": "Alice", "category": "adult"}, ...]

# UPDATE での使用: 価格帯に応じてランクを一括更新
await Product.all().update(
    tier=Case(
        When(Product.price >= 10000, then="premium"),
        When(Product.price >= 3000,  then="standard"),
        default="budget",
    )
)
```

### INSERT ... SELECT

```python
await (
    Employee.where(Employee.hire_year <= 1993)
        .insert_into(Archive, emp_id=Employee.id, year=Employee.hire_year)
)
```

---

## Upsert — `get_or_create` / `update_or_create`

どちらのメソッドも lookup 条件をキーワード引数で受け取り、オプションで `defaults` 辞書を受け取ります。
戻り値は `(instance, created: bool)` のタプルです。

### `get_or_create`

lookup フィールドでレコードを検索し、存在すれば返し、なければ作成します。

```python
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "Alice"},
)
# created=True  → 新規作成（email + name で INSERT）
# created=False → 既存レコードを返す（defaults は無視）
```

`defaults` は新規作成時のみ lookup kwargs とマージされます:

```python
# 2 回目の呼び出し — レコードが既にある場合 defaults は適用されない
author, created = await Author.get_or_create(
    email="alice@example.com",
    defaults={"name": "変わらない"},
)
assert created is False
assert author.name == "Alice"  # 元の値が維持される
```

### `update_or_create`

lookup フィールドでレコードを検索し、存在すれば `defaults` で更新して保存、なければ作成します。

```python
post, created = await Post.update_or_create(
    slug="hello-world",
    defaults={"title": "Hello World", "published": True},
)
# created=True  → 新規作成（slug + defaults をマージ）
# created=False → 既存レコードを defaults で更新して保存
```

冪等な upsert パターン — 繰り返し呼び出しても安全です:

```python
for item in incoming_feed:
    await Article.update_or_create(
        external_id=item["id"],
        defaults={
            "title":      item["title"],
            "body":       item["body"],
            "updated_at": datetime.utcnow(),
        },
    )
```

### 複数の lookup フィールド

複数のキーワード引数を渡すと AND で検索します:

```python
post, created = await Post.update_or_create(
    title="Draft",
    author_id=author.id,
    defaults={"published": True},
)
```

---

## 一括操作（Bulk Operations）

多数のレコードを一度に挿入・更新する場合は bulk メソッドを使用してください。DB へのラウンドトリップ回数を減らしてパフォーマンスを大幅に改善できます。

### `bulk_create` — 一括 INSERT

```python
# インスタンスを作成（まだ保存しない）
posts = [Post(title=f"投稿 {i}", views=0) for i in range(1000)]

# 一括 INSERT（デフォルト batch_size=500 → 2 回の INSERT 文）
await Post.bulk_create(posts)

# 呼び出し後、各インスタンスに id が設定される
print(posts[0].id)  # e.g. 1
```

`batch_size` で 1 つの `INSERT … VALUES (…), (…), …` に含める行数を制御できます。
SQLite はバインド変数が 999 個までに制限されているため、カラム数が多い場合は小さくしてください。

```python
await Post.bulk_create(posts, batch_size=200)
```

`create()` ループとのパフォーマンス比較:

| 方法 | 1,000 件 | SQL 発行回数 |
|---|---|---|
| `create()` ループ | ~1,000 ms | 1,000 回 |
| `bulk_create()` | ~5 ms | 2 回 |

### `bulk_update` — 一括 UPDATE

```python
# レコードを取得して Python 側で変更し、一括で DB に書き戻す
posts = await Post.where(Post.published == False)
for post in posts:
    post.published = True
    post.views = 0

# 更新するフィールドのみ指定（推奨）
await Post.bulk_update(posts, fields=["published", "views"])
```

`fields` に更新対象のカラム名を渡します。
`fields=None`（デフォルト）にすると全非 PK カラムを更新します:

```python
await Post.bulk_update(posts)  # 全カラムを更新
```

`batch_size` の動作は `bulk_create` と同様です:

```python
await Post.bulk_update(posts, fields=["score"], batch_size=200)
```

### トランザクションとの組み合わせ

両メソッドともトランザクションコンテキストを尊重します:

```python
async with engine.transaction():
    await Post.bulk_create(new_posts)
    await Post.bulk_update(existing_posts, fields=["views"])
    # 例外が発生すると両方ともロールバックされる
```

---

## 削除戦略

KakaORM は継承する基底クラスを変えるだけで削除の挙動を切り替えられます。

### SoftDeleteModel — 論理削除

`deleted_at` カラムを自動追加し、`delete()` は物理削除ではなく `deleted_at` に現在時刻をセットします。

```python
from kakaorm import SoftDeleteModel, StrColumn

class Post(SoftDeleteModel):
    title = StrColumn(nullable=False)

    class Meta:
        table_name = "post"

# テーブル作成（deleted_at カラムが自動追加される）
await engine.create_table(Post)

post = await Post.create(title="Hello")
await post.delete()             # deleted_at をセット（物理削除しない）

# デフォルト: 削除済みを除外
posts = await Post.all()        # deleted_at IS NULL のみ

# 削除済みも含む
posts = await Post.include_deleted()

# 削除済みのみ
posts = await Post.only_deleted()

# 復元
await post.restore()

# 物理削除
await Post.only_deleted().purge()
```

QuerySet レベルの一括操作も同様に動作します。

```python
await Post.where(Post.title.like("%draft%")).delete()   # 一括論理削除
await Post.only_deleted().restore()                     # 一括復元
```

### ArchiveModel — アーカイブ削除

`delete()` はレコードを `archive_{table}` テーブルへ移動します（トランザクション内で INSERT + DELETE）。

```python
from kakaorm import ArchiveModel, StrColumn

class Log(ArchiveModel):
    body = StrColumn(nullable=False)

    class Meta:
        table_name = "log"

# メインテーブルとアーカイブテーブルをそれぞれ作成
await engine.create_table(Log)
await engine.create_archive_table(Log)  # archive_log テーブルを作成

log = await Log.create(body="event")
await log.delete()              # archive_log へ移動（トランザクション保証）

# デフォルト: メインテーブルのみ
logs = await Log.all()

# UNION ALL で両テーブルを取得
logs = await Log.include_deleted()

# アーカイブのみ
logs = await Log.only_deleted()

# メインテーブルへ復元
await log.restore()

# アーカイブから物理削除
await Log.only_deleted().purge()
```

### autogenerate との連携

`ArchiveModel` サブクラスは `autogenerate()` 実行時にアーカイブテーブルも自動的に差分計算の対象に含まれます。

```python
from kakaorm.migration import VersionedMigrator

migrator = VersionedMigrator(engine)
# Log テーブルと archive_log テーブルの両方が生成される
path = await migrator.autogenerate([Log], "./migrations", name="add_log")
```

### 削除戦略の比較

| 基底クラス | `delete()` の動作 | デフォルト SELECT | `include_deleted()` |
|---|---|---|---|
| `Model` | 物理削除 | 全件 | — |
| `SoftDeleteModel` | `deleted_at` をセット | `deleted_at IS NULL` | フィルタ解除 |
| `ArchiveModel` | `archive_{table}` へ移動 | メインテーブルのみ | UNION ALL |

---

## クエリログ

KakaORM はすべての SQL 文を Python 標準の `logging` モジュールに出力できます。
出力先は **`kakaorm.sql`** ロガー、レベルは `DEBUG` です。

### 有効化

```python
engine = await kakaorm.connect("sqlite+aiosqlite:///dev.db")
engine.query_logging = True   # ON
engine.query_logging = False  # OFF（デフォルト）
```

実行中であっても任意のタイミングで切り替えられます。

### ロガーの設定

```python
import logging

# すべての SQL を標準出力に表示
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("kakaorm.sql").setLevel(logging.DEBUG)
```

Web アプリでは開発時のみ有効にするのが一般的です。

```python
import os, logging

if os.getenv("SQL_LOG"):
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("kakaorm.sql").setLevel(logging.DEBUG)
    engine.query_logging = True
```

`SQL_LOG=1 uvicorn app:main` のように環境変数で制御できます。

### 出力形式

```
kakaorm.sql | INSERT  INSERT INTO [post] ([title], [views]) VALUES (?, ?) params=['Hello', 0]  (0.3ms)
kakaorm.sql | SELECT  SELECT COUNT(*) AS cnt FROM [post] WHERE views >= %s  params=[10]  (0.2ms)
kakaorm.sql | UPDATE  UPDATE [post] SET views = post.views + %s  params=[1]  (0.3ms)
kakaorm.sql | DELETE  DELETE FROM [post] WHERE [id] = ?  params=[2]  (0.1ms)
```

操作種別・完全な SQL・バインドパラメータ・経過時間（ミリ秒）が 1 行で確認できます。

> INSERT / SELECT / UPDATE / DELETE / COUNT などすべての ORM 操作を捕捉します。
> SQLite / MySQL の `bulk_create`（`executemany` 使用）はパフォーマンスのためクエリ層を
> バイパスするため、行ごとのログは出力されません。PostgreSQL では 1 件として表示されます。

---

## Raw SQL

ORM で表現が難しいクエリには Raw SQL を使用できます。

```python
# SELECT → list[dict]
rows = await engine.fetch(
    "SELECT p.title, a.name FROM post p JOIN author a ON p.author_id = a.id WHERE p.views > %s",
    [100],
)

# INSERT / UPDATE / DELETE → 影響行数
affected = await engine.execute(
    "UPDATE post SET views = 0 WHERE author_id = %s",
    [author_id],
)

# スカラー値
count = await engine.fetchval("SELECT COUNT(*) FROM post WHERE published = %s", [True])
```

---

## トランザクション

```python
async with engine.transaction():
    order = await Order.create(item="Widget", qty=1)
    await Stock.where(Stock.item == "Widget").update(qty=Stock.qty - 1)
    # 例外発生時は自動ロールバック
```

---

## マイグレーション

### 手動マイグレーション

```python
from kakaorm.migration import Migrator

migrator = Migrator(engine)

# ── 推奨: 1 行で完結（v0.4.2 追加）────────────────────────────
# 差分がある場合のみ適用。スキーマが最新なら何もしない。
await migrator.run([Author, Post])

# ── 詳細版: 適用前に SQL を確認したい場合─────────────────────
plan = await migrator.plan([Author, Post])
print(plan.sql)        # UP SQL
print(plan.down_sql)   # DOWN SQL（逆順）
print(plan.is_empty()) # 差分なしのとき True

# 適用 / ロールバック
await plan.apply()
await plan.apply_down()  # ロールバック

# カラム削除も含めた破壊的なプラン
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

> **`run()` vs `plan().apply()`** — `run()` はスキーマが最新のときは何もしないため、
> アプリ起動時に毎回呼んでも安全です。SQL を事前に確認・ログ出力したい場合や
> ロールバックを行いたい場合は `plan()` を使ってください。

### ファイルベースのマイグレーション（推奨）

```python
from kakaorm.migration import VersionedMigrator

migrator = VersionedMigrator(engine)

# 1. モデルと DB の差分から migration ファイルを自動生成
path = await migrator.autogenerate([User, Post], "./migrations", name="add_bio")
# → migrations/0001_add_bio.py が生成される

# 2. 未適用のマイグレーションを一括適用
n = await migrator.run_files("./migrations")

# 3. 直近 1 件をロールバック
await migrator.downgrade(steps=1)

# 適用履歴を確認
for record in await migrator.history():
    print(record.name, record.applied_at)
```

生成されるマイグレーションファイルの形式:

```python
# migrations/0001_add_bio.py
# Auto-generated by KakaORM

up = [
    "ALTER TABLE user ADD COLUMN bio TEXT DEFAULT NULL",
]

down = [
    "ALTER TABLE user DROP COLUMN bio",
]
```

---

## CLI コマンド

`pip install kakaorm` でインストールすると `kakaorm` コマンドが使えます。

> **インストール後にコマンドが見つからない場合**、Python の `bin` ディレクトリが `PATH` に含まれていない可能性があります。
> 代わりに `python -m kakaorm` を使うか、以下のように `PATH` に追加してください:
> ```bash
> # スクリプトのインストール先を確認
> python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
> # シェルのプロファイル（~/.zshrc や ~/.bashrc など）に追加
> export PATH="$PATH:/path/to/python/bin"
> ```

```bash
# プロジェクト初期化（migrations/ ディレクトリとコンフィグを生成）
kakaorm init

# モデルと DB の差分からマイグレーションファイルを生成
kakaorm makemigrations --models myapp.models --db sqlite+aiosqlite:///./dev.db --name add_user_bio

# 未適用マイグレーションをすべて適用
kakaorm migrate --db sqlite+aiosqlite:///./dev.db

# 直近 N 件をロールバック
kakaorm migrate --db sqlite+aiosqlite:///./dev.db --direction down --steps 1

# 適用済みマイグレーション履歴を表示
kakaorm showmigrations --db sqlite+aiosqlite:///./dev.db
```

| コマンド | 説明 |
|---|---|
| `init` | `migrations/` ディレクトリと設定ファイルを初期化する |
| `makemigrations` | モデル定義と DB スキーマの差分をファイルに出力する |
| `migrate` | 未適用マイグレーションを適用する（`--direction down` でロールバック） |
| `showmigrations` | 適用履歴をテーブル形式で表示する |

---

## エラーメッセージ リファレンス

よくある間違いに対して、KakaORM は原因と修正方法を示すエラーを送出します。

### フィールド名のタイポ

```python
User(naem="Alice")
# TypeError: Unknown field 'naem' for User.
#   Did you mean 'name'?
#   Available fields: id, name, email, age
```

宣言されていないキーワード引数を渡した場合に送出されます。
実在するフィールド名に近い場合は候補を提示します。

---

### ColumnMeta / WhereClause を値として渡した

```python
Post(title=Post.title)         # ColumnMeta — クラスレベルのカラムアクセサ
Post(title=(Post.views > 0))   # WhereClause — フィルタ条件
```

```
TypeError: Field 'title' received a ColumnMeta object.
  ColumnMeta is used for query building, not as a field value.
  To filter by this column: Post.where(Post.title == <value>)
  To set a value: Post(title=<actual value>)

TypeError: Field 'title' received a WhereClause object.
  WhereClause is a filter condition, not a field value.
  To filter rows: Post.where(<condition>)
  To set a value: Post(title=<actual value>)
```

クラスアクセス（`Post.title`）は `ColumnMeta` を返します。これは WHERE 句の構築用であり、
コンストラクタに渡す値ではありません。

---

### `update()` に WhereClause / ColumnMeta を渡した

```python
await Post.all().update(title=(Post.title == "foo"))  # WhereClause
await Post.all().update(views=Post.views)              # ColumnMeta
```

```
TypeError: Column 'title' in update() received a WhereClause.
  WhereClause is a filter condition, not a SET value.
  Use .where() to filter rows:
    .where(<condition>).update(title=<new value>)

TypeError: Column 'views' in update() received a ColumnMeta.
  To reference another column in an expression, use arithmetic operators:
    .update(views=views + 1)  → adds 1 to the current value
  To set a literal value: .update(views=<actual value>)
```

現在値を参照した演算は、`ColumnMeta` の算術演算子で `UpdateExpr` を生成して渡します。

```python
# ✅ 正しい — ColumnMeta の算術演算が UpdateExpr を生成する
await Post.all().update(views=Post.views + 1)
await Post.all().update(price=Post.price * 0.9)
```

---

### `Column()` に位置引数を渡した

```python
name = Column(str)     # TypeError
age  = IntColumn(int)  # TypeError
```

```
TypeError: Column() does not accept positional arguments.
  Use a type-specific column class instead:
  IntColumn, StrColumn, FloatColumn, BoolColumn, DateTimeColumn,
  DateColumn, TimeColumn, DecimalColumn, ForeignKey
```

---

## セキュリティ

kakaorm はクエリの値を常にバインドパラメータとして扱い、SQL インジェクションを防止します。

- **WHERE / LIKE / IN 句の値** — すべてバインドパラメータ経由で送出されます
- **`update()` のカラム名** — `_meta.columns` に存在しないキーは `ValueError` で拒否します
- **`insert_into()` の宛先カラム名** — 同様に `_meta.columns` でホワイトリスト検証します
- **`create()` のフィールド名** — 未知のフィールドは `TypeError` で拒否します。近いフィールド名がある場合は候補を提示します

> **アプリ側の注意点**
>
> `order_by()` は生文字列をそのまま SQL に展開します。
> ユーザー入力を ORDER BY に使う場合は、許可済みカラム名のみを受け付けるホワイトリストをアプリ側で実装してください。
>
> ```python
> ALLOWED = {"views", "title", "created_at"}
> col = user_input if user_input in ALLOWED else "id"
> results = await Post.all().order_by(f"{col} DESC")
> ```
>
> また、`create()` / `save()` は既知フィールドへの書き込みを制限しません。
> ユーザー入力から特権フィールド（`is_admin` など）を除外する処理はアプリ層で行ってください。

## アップグレードガイド

### v0.4.1 → v0.4.2

**`Migrator().run()` — 新しい 1 行 API**

以前はスキーマ変更の適用に 2 ステップが必要でした。

```python
# v0.4.1 — 引き続き動作するが冗長
plan = await migrator.plan([User, Post])
await plan.apply()
```

v0.4.2 から 1 行で書けるようになりました。

```python
# v0.4.2+ — 推奨
await migrator.run([User, Post])
```

`run()` はスキーマが最新のときは何もしないため、アプリ起動時に毎回呼んでも安全です。
`plan()` + `apply()` パターンは引き続き利用可能で、SQL を事前に確認したい場合に使えます。

---

**`VersionedMigrator.run()` → `run_manual()` に改名**

`VersionedMigrator.run(dict)` を使っていた場合は `run_manual(dict)` に変更してください。
継承した `run()` はモデルリストを受け取る新しい API です。

```python
# v0.4.1
await versioned_migrator.run({"up": [...], "down": [...]})

# v0.4.2+
await versioned_migrator.run_manual({"up": [...], "down": [...]})
```

---

### v0.4.2 → v0.4.3

**`DateTimeColumn(auto_now_add=True)` がバルク操作でも動作するように**

v0.4.3 以前は `auto_now_add` / `auto_now` が `save()` でのみ発火し、バルク操作では無視されていました。

```python
# v0.4.2 — auto_now_add が適用されなかった
await Post.bulk_create([Post(title="A"), Post(title="B")])

# v0.4.3+ — bulk_create / bulk_update でも正しく発火する
await Post.bulk_create([Post(title="A"), Post(title="B")])
```

コードの変更は不要です。以前に挿入されたタイムスタンプ欠落行は `NULL` / 空値のまま残ります。

---

**`nullable=False` + `auto_now_add=True` の ADD COLUMN**

v0.4.3 以前は、既存テーブルに `NOT NULL` かつ `auto_now_add=True` のカラムを追加すると
既存行の制約違反でマイグレーションが失敗していました。
v0.4.3 以降は Migrator が自動的に DB 側デフォルト値を注入するため、手動での回避策は不要です。

---

## テーブル名と予約語

KakaORM は各データベース固有の方法で識別子を自動クォートするため、SQL の予約語（`order`、`select`、`group` など）をテーブル名として特別な記述なしに使用できます。

```python
class Order(Model):
    class Meta:
        table_name = "order"  # KakaORM が自動的にクォート
```

> **手動でクォートしないでください。** クォート文字を自分で付けると二重クォートが発生します：
>
> ```python
> class Meta:
>     table_name = "[order]"   # ❌ SQLite で [[order]] になる
>     table_name = '"order"'   # ❌ 手動クォートは不要
>     table_name = '`order`'   # ❌ 手動クォートは不要
> ```
>
> 可能であれば予約語を避けた命名を推奨します（例: `order` の代わりに `orders`）。
