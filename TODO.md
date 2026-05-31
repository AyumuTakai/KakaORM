# TODO — SQLAlchemy 比較で不足している機能

## クエリ機能

- [ ] GROUP BY / HAVING
- [ ] 集計関数 (SUM / AVG / MAX / MIN)
- [ ] JOIN サポート (INNER / LEFT / RIGHT)
/* 優先順位:低 */
- [ ] サブクエリ / 派生テーブル
- [ ] ウィンドウ関数
- [ ] UNION / INTERSECT
- [ ] CTE (WITH 句)

## モデル・スキーマ

- [ ] リレーション定義 (`relationship()` 相当)
- [ ] 複合主キー
- [ ] CHECK 制約
- [ ] 複合インデックス
/* 優先順位:低 */
- [ ] Lazy / Eager ローディング
- [ ] テーブル継承 (single / joined / concrete)
- [ ] カスタム型 (`TypeDecorator` 相当)

## トランザクション・セッション

- [ ] 明示的トランザクション / ロールバック
/* 優先順位:低 */
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
/* 優先順位:低 */
- [ ] 既存 DB からのスキーマ反映
- [ ] Oracle / MSSQL サポート
