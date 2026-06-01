# TODO — 未実装機能一覧

## クエリ機能

- [x] TRUNCATE (DELETE と異なりシーケンスもリセット)

#### 低優先

- [x] サブクエリ (WHERE col IN/NOT IN (SELECT ...) 対応)
- [x] CASE WHEN 式 (SELECT 列・UPDATE SET 句での条件分岐)
- [x] CTE (WITH 句) (`QuerySet.with_cte(name, queryset)`)
- [x] ウィンドウ関数 (`RowNumber` / `Rank` / `DenseRank` / `Lag` / `Lead` / `Sum().over()` 等)
- [ ] SQL 文字列関数 (REPLACE / CONCAT / SUBSTR 等)
- [ ] UNION / INTERSECT (汎用 QuerySet API)
- [x] `Model.find(pk)` ショートハンド — PK による1件取得を `get_or_none(Model.id == pk)` より簡潔に書ける `find(pk)` メソッドを追加する (ActiveRecord の `find` / Django の `get(pk=...)` 相当)

## モデル・スキーマ

- [ ] 複合主キー (PRIMARY KEY(col1, col2))
- [x] ユーザー定義主キー (auto id を使わない任意カラムを PK に指定)
- [x] NUMERIC / DECIMAL 型 (FloatColumn は DOUBLE PRECISION で精度が異なる)
- [x] DATE 型 / TIME 型 (DateTimeColumn は TIMESTAMP; 日付のみ・時刻のみの型がない)
- [x] CHECK 制約
- [x] 複合インデックス

#### 低優先

- [x] リレーション定義 (`relationship()` 前向きFK・逆参照)
- [x] Eager ローディング (`prefetch()` — has_many / has_one / belongs_to を一括取得、N+1 解消)
- [x] 論理削除 (`SoftDeleteModel` — `deleted_at` による削除、`include_deleted()` / `only_deleted()` / `restore()` / `purge()`)
- [x] アーカイブ削除 (`ArchiveModel` — `archive_{table}` への移動、`include_deleted()` UNION ALL / `restore()` / `purge()`)
- [x] 削除戦略の `autogenerate()` 連携 — `ArchiveModel` のアーカイブテーブルを自動的に差分計算の対象に含める
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
- [x] ダウングレード (`VersionedMigrator.downgrade(steps)` / `MigrationPlan.apply_down()`)
- [x] `Migrator` 初期化 API の改善 — 現状は `Migrator(engine)` でエンジンを受け取った後に `plan([Model, ...])` を呼ぶ2ステップが必要。`Migrator(engine, [Model, ...])` のようにモデルリストをコンストラクタで受け取るか、`Migrator.auto(engine, [Model, ...])` のようなファクトリメソッドを追加し直感性を上げる
- [ ] カラム型変更
- [x] 自動生成 (autogenerate — `Migrator.autogenerate()` / `VersionedMigrator.run_files()`)

## セキュリティ

- [x] `update()` カラム名ホワイトリスト検証 (`_meta.columns` に存在しないキーを `ValueError` で拒否)
- [x] `insert_into()` 宛先カラム名ホワイトリスト検証 (同上)
- [x] セキュリティ回帰テスト (`test_security.py`) — マスアサインメント / SQLi パラメータ化 / NULL インジェクション / セカンドオーダー等
- [ ] `order_by()` へのユーザー入力を ORM 側でホワイトリスト検証する仕組み (現状はアプリ側対応が必要)

## その他

- [x] バルクインサート (高速一括投入)
- [x] Raw SQL との統合強化
- [x] イベントフック (before_insert / after_insert / before_update / after_update / before_delete / after_delete)
- [x] Engine クラスを `engine.py` に分離 (旧: `__init__.py` に混在)
- [x] `QuerySet` の WHERE / HAVING マージ・エンジン取得を共通ヘルパーに抽出
- [x] `has_one` 逆参照が `list` を返すバグを修正 (`Model | None` を返すように)
- [x] `StrColumn.ddl_fragment()` が `sql_type` を破壊的に書き換えるバグを修正
- [x] DDL 型変換 (`SERIAL→AUTOINCREMENT` 等) を `_adapt_ddl()` に一元化
- [x] Pydantic v2 プロトコル対応 (`model_dump` / `model_validate` / `__get_pydantic_core_schema__` / `__get_pydantic_json_schema__`) — FastAPI の `response_model` に直接指定可能

- [x] `connect()` の同期呼び出し時の明確なエラー — `await` を付けずに `kakaorm.connect(...)` を呼んだ場合、現状は `RuntimeWarning: coroutine was never awaited` が出るだけで原因が分かりにくい。`TypeError` または専用の `SyncCallError` で「`await kakaorm.connect(...)` と書いてください」と案内する

#### 低優先

- [ ] 既存 DB からのスキーマ反映
- [ ] Oracle / MSSQL サポート

## パッケージング・公開

- [x] `pyproject.toml` にパッケージメタデータ記述 (名前・バージョン・依存・optional-deps・URL)
- [x] MIT ライセンス (`LICENSE`)
- [x] `__version__` 定義 (`kakaorm/__init__.py`)
- [x] PEP 561 型情報マーカー (`kakaorm/py.typed`)
- [x] `CHANGELOG.md` 作成
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) — lint・テストマトリクス・MySQL・wheel ビルド
- [x] README にバッジ・ライセンスセクション・インストール手順を追記
- [x] ruff lint エラー修正 — 未使用 import 削除・`TYPE_CHECKING` ガードで循環 import を回避しつつ前方参照を解決
- [x] MySQL CI 修正 — MySQL 8.0 の `caching_sha2_password` 認証に必要な `cryptography` パッケージを追加
- [x] PyPI への初回アップロード (`twine upload dist/*`)
