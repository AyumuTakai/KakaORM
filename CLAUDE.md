# KakaORM — Claude Code 作業ガイド

> このファイルは Claude Code が KakaORM リポジトリを操作するときに自動で読み込まれる。
> バージョンアップのたびに必ず更新すること。

---

## 現在バージョン

**v0.4.5**（`kakaorm/__init__.py` と `pyproject.toml` の両方に記載）

---

## リポジトリ構成

```
kakaorm/
├── kakaorm/
│   ├── __init__.py          公開 API エクスポート・__version__
│   ├── engine.py            Engine 基底クラス + 4ドライバ実装
│   │                        （AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine）
│   ├── model.py             Model 基底クラス・メタクラス・CRUD
│   ├── query.py             QuerySet（遅延クエリビルダ）
│   ├── columns/
│   │   ├── base.py          Column / ColumnMeta / WhereClause / AggFunc / WindowFunc / Case
│   │   └── types.py         IntColumn / StrColumn / FloatColumn / BoolColumn /
│   │                        DateTimeColumn / DateColumn / TimeColumn / DecimalColumn / ForeignKey
│   ├── relationship.py      has_many / has_one / belongs_to
│   ├── migration/
│   │   └── __init__.py      Migrator / VersionedMigrator / MigrationPlan
│   ├── validators.py        ValidationError + built-in validators
│   ├── soft_delete.py       SoftDeleteModel
│   ├── archive.py           ArchiveModel
│   └── cli/                 kakaorm CLI
├── tests/                   pytest テストスイート
├── examples/                FastAPI / Flask / Blog の使用例
├── docs/
│   ├── REFERENCE.md         完全 API リファレンス（英語）
│   ├── REFERENCE.ja.md      完全 API リファレンス（日本語）
│   ├── FASTAPI.md / .ja.md  FastAPI 統合ガイド
│   └── FLASK.md  / .ja.md   Flask 統合ガイド
├── README.md                英語 README（一次情報）
├── README.ja.md             日本語 README
├── CHANGELOG.md             Keep a Changelog 形式
├── llms.txt                 AI エージェント向けチートシート
└── CLAUDE.md                このファイル
```

---

## 重要な設計ルール

### engine.py — `_raw_*` パターン

v0.4.5 以降、クエリのログ差し込みのためにレイヤーが2段になっている。

```
Engine._fetch / _execute / _fetchval     ← ログ付きラッパー（基底クラスが実装）
        ↓
Engine._raw_fetch / _raw_execute / _raw_fetchval  ← ドライバ実装（各サブクラスが実装）
```

- サブクラスに新しいメソッドを追加するときは **`_raw_*`** に実装する
- 基底クラス内の ORM 内部メソッド（`_insert` / `_update` 等）は `self._fetch` / `self._execute` を呼ぶ（ログが通る）
- `_raw_*` を直接呼んではいけない

### columns/base.py — Column.__init__

`Column.__init__` は `*args` を受け取り、位置引数が渡された場合に即 `TypeError` を出す。
サブクラスで `__init__` を定義するときは `*args` を受け取って `super().__init__(*args, **kwargs)` に渡すこと。

ただし `ForeignKey` と `DecimalColumn` は意図的な位置引数を持つ（例外）。

### model.py — Model.__init__

未知フィールド・ColumnMeta・WhereClause を値として受け取った場合に `TypeError` を出す。
`difflib.get_close_matches` でタイポ候補も提示する。

---

## テスト

```bash
# 全テスト（SQLite ベース・約 1.5 秒）
python -m pytest tests/ -x -q

# 特定ファイル
python -m pytest tests/test_crud.py -v
```

- テストは `tests/conftest.py` の `engine` fixture（`:memory:` SQLite）を共有
- 新機能を追加したらテストも追加する

---

## バージョンアップ手順

バージョンを上げるときは以下を **必ず同時に** 更新する。

1. `kakaorm/__init__.py` — `__version__ = "x.y.z"`
2. `pyproject.toml` — `version = "x.y.z"`
3. `CHANGELOG.md` — 先頭に新エントリを追加（Keep a Changelog 形式）
4. `llms.txt` — ファイル冒頭の `Version: x.y.z` を更新
5. `CLAUDE.md`（このファイル）— 「現在バージョン」を更新

**CHANGELOG エントリの形式:**

```markdown
## [x.y.z] - YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...
```

---

## ドキュメント更新ルール

### 日英同時更新

`README.md` と `README.ja.md`、`docs/REFERENCE.md` と `docs/REFERENCE.ja.md` は常に同時に更新する。片方だけ更新してはいけない。

### 更新が必要なドキュメント

| 変更の種類 | 更新するファイル |
|---|---|
| 新 API 追加 | REFERENCE.md / .ja.md、README.md / .ja.md（主要なものは）、llms.txt |
| エラーメッセージ変更 | REFERENCE.md / .ja.md の「Error Message Reference」セクション |
| マイグレーション API 変更 | REFERENCE.md / .ja.md の「Migrations」と「Upgrade Guide」 |
| バージョンアップ | CHANGELOG.md、llms.txt、CLAUDE.md（このファイル） |

---

## よくある作業パターン

### 新しい Column 型を追加する

1. `kakaorm/columns/types.py` に `class XxxColumn(Column[T])` を追加
2. `__init__` に `*args` を含める: `def __init__(self, *args: Any, ..., **kwargs: Any)`
3. `kakaorm/__init__.py` の `__all__` に追加
4. `docs/REFERENCE.md` / `.ja.md` のカラム型テーブルに追加
5. `llms.txt` のカラム型テーブルに追加
6. テストを追加

### 新しい Engine メソッドを追加する（全 DB 対応）

1. `Engine` 基底クラスに `@abstractmethod _raw_xxx()` を追加
2. 基底クラスに `_xxx()` ログラッパーを追加
3. 全4サブクラス（AsyncpgEngine / AioSQLiteEngine / AioMySQLEngine / Psycopg3Engine）に `_raw_xxx()` を実装
4. テストを追加

### エラーメッセージを改善する

1. 実装を変更（`model.py` / `query.py` / `columns/base.py`）
2. `docs/REFERENCE.md` / `.ja.md` の「Error Message Reference」セクションを更新

---

## コミット規約

```
v{version}: {概要}

### Added / Changed / Fixed
- 変更内容の箇条書き

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

コミット前に必ず `python -m pytest tests/ -x -q` を通す。

---

## 未実装の主要機能（TODO.md より抜粋）

実装を提案・依頼されたときに参考にする。

- `[ ]` SQL 文字列関数（REPLACE / CONCAT / SUBSTR 等）
- `[ ]` UNION / INTERSECT
- `[ ]` 複合主キー
- `[ ]` カラム型変更（ALTER TABLE MODIFY COLUMN）
- `[ ]` テーブル継承（single / joined / concrete）
- `[ ]` セーブポイント
- `[ ]` 既存 DB からのスキーマ反映（introspection）
- `[ ]` `order_by()` へのユーザー入力のホワイトリスト検証（現状はアプリ側対応）
