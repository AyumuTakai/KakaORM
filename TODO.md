# TODO — 未実装機能一覧

## クエリ機能

- [x] TRUNCATE (DELETE と異なりシーケンスもリセット)

#### 低優先

- [x] サブクエリ (WHERE col IN/NOT IN (SELECT ...) 対応)
- [x] CASE WHEN 式 (SELECT 列・UPDATE SET 句での条件分岐)
- [ ] SQL 文字列関数 (REPLACE / CONCAT / SUBSTR 等)
- [ ] ウィンドウ関数
- [ ] UNION / INTERSECT
- [ ] CTE (WITH 句)

## モデル・スキーマ

- [ ] 複合主キー (PRIMARY KEY(col1, col2))
- [x] ユーザー定義主キー (auto id を使わない任意カラムを PK に指定)
- [x] NUMERIC / DECIMAL 型 (FloatColumn は DOUBLE PRECISION で精度が異なる)
- [x] DATE 型 / TIME 型 (DateTimeColumn は TIMESTAMP; 日付のみ・時刻のみの型がない)
- [x] CHECK 制約
- [x] 複合インデックス

#### 低優先

- [x] リレーション定義 (`relationship()` 前向きFK・逆参照)
- [ ] Lazy / Eager ローディング
- [ ] テーブル継承 (single / joined / concrete)
- [ ] カスタム型 (`TypeDecorator` 相当)

## DDL 操作

- [x] DROP TABLE CASCADE オプション

#### 低優先

- [ ] CREATE INDEX / DROP INDEX
- [ ] ALTER TABLE RENAME

## トランザクション・セッション

- [x] 明示的トランザクション / ロールバック

#### 低優先

- [ ] セッションスコープ管理
- [ ] セーブポイント

## マイグレーション

- [x] バージョン管理・履歴 (VersionedMigrator / kakaorm_migrations テーブル)
- [ ] ダウングレード
- [ ] カラム型変更
- [ ] 自動生成 (autogenerate)

## その他

- [x] バルクインサート (高速一括投入)
- [x] Raw SQL との統合強化
- [x] イベントフック (before_insert / after_insert / before_update / after_update / before_delete / after_delete)

#### 低優先

- [ ] 既存 DB からのスキーマ反映
- [ ] Oracle / MSSQL サポート
