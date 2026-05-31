# TODO — 未実装機能一覧

## クエリ機能

- [ ] TRUNCATE (DELETE と異なりシーケンスもリセット)

#### 低優先

- [ ] サブクエリ / 派生テーブル (UPDATE / DELETE の WHERE 句でも必要)
- [ ] CASE WHEN 式 (UPDATE の SET 句での条件分岐)
- [ ] SQL 文字列関数 (REPLACE / CONCAT / SUBSTR 等)
- [ ] ウィンドウ関数
- [ ] UNION / INTERSECT
- [ ] CTE (WITH 句)

## モデル・スキーマ

- [ ] 複合主キー (PRIMARY KEY(col1, col2))
- [ ] ユーザー定義主キー (auto id を使わない任意カラムを PK に指定)
- [ ] NUMERIC / DECIMAL 型 (FloatColumn は DOUBLE PRECISION で精度が異なる)
- [ ] DATE 型 / TIME 型 (DateTimeColumn は TIMESTAMP; 日付のみ・時刻のみの型がない)
- [ ] CHECK 制約
- [ ] 複合インデックス

#### 低優先

- [ ] リレーション定義 (`relationship()` 相当)
- [ ] Lazy / Eager ローディング
- [ ] テーブル継承 (single / joined / concrete)
- [ ] カスタム型 (`TypeDecorator` 相当)

## DDL 操作

- [ ] DROP TABLE CASCADE オプション

#### 低優先

- [ ] CREATE INDEX / DROP INDEX
- [ ] ALTER TABLE RENAME

## トランザクション・セッション

- [ ] 明示的トランザクション / ロールバック

#### 低優先

- [ ] セッションスコープ管理
- [ ] セーブポイント

## マイグレーション

- [ ] バージョン管理・履歴
- [ ] ダウングレード
- [ ] カラム型変更
- [ ] 自動生成 (autogenerate)

## その他

- [ ] バルクインサート (高速一括投入)
- [ ] Raw SQL との統合強化
- [ ] イベントフック (before_insert / after_update 等)

#### 低優先

- [ ] 既存 DB からのスキーマ反映
- [ ] Oracle / MSSQL サポート
