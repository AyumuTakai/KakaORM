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

### CTE（WITH 句）

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

# 差分プランを確認
plan = await migrator.plan([Author, Post])
print(plan.sql)       # UP SQL
print(plan.down_sql)  # DOWN SQL（逆順）

# 適用 / ロールバック
await plan.apply()
await plan.apply_down()  # ロールバック

# カラム削除も含めた破壊的なプラン
plan = await migrator.plan_with_drop([Author, Post])
await plan.apply()
```

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

## セキュリティ

kakaorm はクエリの値を常にバインドパラメータとして扱い、SQL インジェクションを防止します。

- **WHERE / LIKE / IN 句の値** — すべてバインドパラメータ経由で送出されます
- **`update()` のカラム名** — `_meta.columns` に存在しないキーは `ValueError` で拒否します
- **`insert_into()` の宛先カラム名** — 同様に `_meta.columns` でホワイトリスト検証します
- **`create()` のフィールド名** — 未知のフィールドは `TypeError` で拒否します

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
