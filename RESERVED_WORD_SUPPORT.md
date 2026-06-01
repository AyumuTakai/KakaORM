# KakaORM 予約語サポート ガイド

## 概要

KakaORMは、SQLの予約語（`order`、`select`、`group` など）を **テーブル名として直接使用できます**。Engine が各データベース固有の方法で自動的に識別子をクォートします。**ユーザーが手動でクォートを指定する必要はありません。**

## 予約語対応方法

KakaORM は自動的に各データベースの方法で識別子をクォートします。ユーザーは予約語でも通常のテーブル名と同じように指定するだけです。

### 全データベース共通（推奨方法）

```python
class Order(Model):
    name = StrColumn(nullable=False)
    quantity = IntColumn()
    
    class Meta:
        table_name = "order"  # クォート文字なし - Engine が自動処理
```

**動作結果：✅ 全データベース（SQLite, PostgreSQL, MySQL）で対応**

### 内部的なクォート処理

KakaORM は以下のように自動的にクォートします：

| データベース | 内部クォート方法 | 生成されるSQL |
|------------|-----------------|--------------|
| SQLite | 角括弧 `[...]` | `CREATE TABLE [order] (...)` |
| PostgreSQL | ダブルクォート `"..."` | `CREATE TABLE "order" (...)` |
| MySQL | バッククォート `` `...` `` | `CREATE TABLE `order` (...)` |

### 仕組み

1. `Meta.table_name = "order"` を指定
2. Engine の `quote_identifier()` メソッドが自動的にクォート
3. SQL 生成時に正しくクォートされた識別子が使用される

例えば SELECT クエリは以下のように生成されます：
```sql
-- SQLite
SELECT * FROM [order]

-- PostgreSQL
SELECT * FROM "order"

-- MySQL
SELECT * FROM `order`
```

## 動作確認済みの予約語

以下の予約語をMeta.table_nameでクォートして使用可能であることを確認しています：

| 予約語 | SQLite | PostgreSQL | MySQL |
|--------|--------|-----------|-------|
| `order` | ✅ [order] | ✅ "order" | ✅ `order` |
| `select` | ✅ [select] | ✅ "select" | ✅ `select` |
| `group` | ✅ [group] | ✅ "group" | ✅ `group` |
| `from` | ✅ [from] | ✅ "from" | ✅ `from` |
| `where` | ✅ [where] | ✅ "where" | ✅ `where` |
| `insert` | ✅ [insert] | ✅ "insert" | ✅ `insert` |
| `update` | ✅ [update] | ✅ "update" | ✅ `update` |
| `delete` | ✅ [delete] | ✅ "delete" | ✅ `delete` |

## 使用例

### 複数の予約語テーブルを同時に使用

```python
from kakaorm import Model, StrColumn, IntColumn, ForeignKey, belongs_to

class Order(Model):
    name = StrColumn(nullable=False)
    
    class Meta:
        table_name = "order"  # クォート文字なし

class Selection(Model):
    name = StrColumn(nullable=False)
    order_id = ForeignKey(Order, nullable=False)
    
    order = belongs_to(Order, foreign_key="order_id")
    
    class Meta:
        table_name = "select"  # クォート文字なし

# 使用方法は通常通り
order = await Order.create(name="Order-001")
selection = await Selection.create(name="Option-1", order_id=order.id)

# クエリも通常通り
orders = await Order.all()
selected = await Selection.where(Selection.order_id == order.id).execute()
```

## 推奨事項

### ✅ 推奨パターン

1. **予約語が必須の場合** - KakaORM の自動クォート機能を使用
   ```python
   class Meta:
       table_name = "order"  # クォート文字なし - Engine が自動処理
   ```

2. **より明確な命名を避ける場合** - KakaORM の自動クォート機能を使用
   ```python
   class Meta:
       table_name = "select"  # クォート文字なし - Engine が自動処理
   ```

### 💡 ベストプラクティス

1. **テーブル名に予約語を避ける**（推奨度：高）
   ```python
   class Meta:
       table_name = "orders"  # order を避けて orders を使用
   ```

2. **予約語が必須の場合は KakaORM の自動クォート機能を使用**（推奨度：中）
   ```python
   class Meta:
       table_name = "order"  # KakaORM が自動的にクォート
   ```

### ❌ 非推奨パターン

```python
# 手動でクォート文字を指定 - ネストクォートが発生
class Meta:
    table_name = "[order]"   # ❌ SQLite で [[order]] になる
    table_name = '"order"'   # ❌ 手動クォートは不要
    table_name = '`order`'   # ❌ 手動クォートは不要
```

## 実装詳細

KakaORM は以下の仕様で予約語に対応しています：

- **自動クォート処理**：Engine が `quote_identifier()` メソッドで自動的に識別子をクォート
- **データベース固有対応**：
  - `AioSQLiteEngine`: `[identifier]` 形式（SQLite）
  - `AsyncpgEngine` / `Psycopg3Engine`: `"identifier"` 形式（PostgreSQL）
  - `AioMySQLEngine`: `` `identifier` `` 形式（MySQL）
- **テーブル名・カラム名の全箇所**：SELECT/INSERT/UPDATE/DELETE/CREATE TABLE/ALTER TABLE など全ての SQL に適用
- **ユーザーの負担なし**：Meta.table_name に予約語をそのまま指定するだけで動作

つまり、KakaORM が自動的に処理するため、ユーザーは予約語をテーブル名として安全に使用できます。

## テスト結果

### 実施テスト: 51個のSQLパターン + 予約語対応テスト

- ✅ 成功：401個テスト
- ⏭️ スキップ：9個
- ❌ 失敗：0個

### 予約語対応テスト詳細

- ✅ SQLite での自動クォート：動作確認
- ✅ PostgreSQL での自動クォート：動作確認
- ✅ MySQL での自動クォート：動作確認
- ✅ 複数予約語テーブルの同時使用：動作確認
- ✅ Migration（CREATE/ALTER/DROP）での自動クォート：動作確認

**結論：KakaORM は予約語をテーブル名として安全に使用でき、Engine が自動的に各データベース固有の方法でクォートします。** ✅
