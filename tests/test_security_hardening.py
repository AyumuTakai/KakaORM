"""
セキュリティ強化（v0.4.8）の回帰テスト
======================================
SQL 文字列に直接埋め込まれる値の検証と、情報漏えい対策を確認する。

  1. limit() / offset() の型検証
  2. Lag / Lead の default バインド化・offset 検証
  3. order_by() / WindowFunc.over() のホワイトリスト検証
  4. エイリアス・CTE 名・列参照の識別子検証
  5. quote_identifier のエスケープ
  6. DDL パラメータ（check / on_delete / max_length / Meta.indexes）の検証
  7. 接続 URL のパスワード伏せ字
  8. クエリログのパラメータ伏せ字
  9. マイグレーション（ファイル名・downgrade の改ざん検知）
"""

import json
import logging
import tempfile
import warnings

import pytest

import kakaorm
from kakaorm import Model, StrColumn, IntColumn
from kakaorm._sql import redact_url
from kakaorm.columns.base import Case, Count, Lag, Lead, RowNumber, Sum, When
from kakaorm.columns.types import DecimalColumn, ForeignKey
from kakaorm.engine import AioMySQLEngine, AioSQLiteEngine, AsyncpgEngine, Psycopg3Engine
from kakaorm.migration import VersionedMigrator


class Acct(Model):
    name   = StrColumn(nullable=False)
    secret = StrColumn(nullable=True)
    score  = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "acct"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Acct)
    await Acct.create(name="alice", secret="S3CRET", score=10)
    await Acct.create(name="bob", secret="HUNTER2", score=20)
    yield eng
    await eng.disconnect()


# ── 1. limit / offset ─────────────────────────────────────────

class TestLimitOffset:

    @pytest.mark.parametrize("bad", [
        "1 UNION SELECT 99, name, secret FROM acct",
        "10",
        1.5,
        None,
    ])
    def test_limit_rejects_non_int(self, bad):
        with pytest.raises(TypeError, match="limit must be an int"):
            Acct.all().limit(bad)

    def test_offset_rejects_string(self):
        with pytest.raises(TypeError, match="offset must be an int"):
            Acct.all().offset("0; DROP TABLE acct")

    def test_bool_is_rejected(self):
        with pytest.raises(TypeError):
            Acct.all().limit(True)

    def test_negative_is_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            Acct.all().limit(-1)
        with pytest.raises(ValueError, match=">= 0"):
            Acct.all().offset(-5)

    async def test_int_still_works(self, engine):
        rows = await Acct.all().order_by(Acct.id.asc).limit(1).offset(1)
        assert [r.name for r in rows] == ["bob"]


# ── 2. Lag / Lead ─────────────────────────────────────────────

class TestWindowDefaultBinding:
    PAYLOAD = "x') AS v, (SELECT group_concat(secret) FROM acct) AS leaked --"

    def test_default_is_bound_not_inlined(self):
        sql, params = Acct.all().select(
            Acct.id, Lag(Acct.name, 1, self.PAYLOAD).over(order_by=[Acct.id.asc]).label("prev")
        )._build_sql()
        assert "group_concat" not in sql
        assert self.PAYLOAD in params

    async def test_payload_is_returned_as_plain_value(self, engine):
        rows = await Acct.all().select(
            Acct.id, Lead(Acct.name, 1, self.PAYLOAD).over(order_by=[Acct.id.asc]).label("nxt")
        )
        assert rows[-1]["nxt"] == self.PAYLOAD
        assert all("leaked" not in r for r in rows)

    async def test_numeric_default_keeps_type(self, engine):
        rows = await Acct.all().select(
            Acct.id, Lag(Acct.score, 1, 0).over(order_by=[Acct.id.asc]).label("prev")
        )
        assert rows[0]["prev"] == 0

    def test_default_params_follow_select_order_before_where(self):
        _, params = (
            Acct.where(Acct.score > 5)
                .select(Lag(Acct.name, 1, "d").over(order_by=[Acct.id.asc]).label("p"))
                ._build_sql()
        )
        assert params == ["d", 5]

    @pytest.mark.parametrize("bad", ["1) FROM acct; --", -1, 1.0])
    def test_offset_is_validated(self, bad):
        with pytest.raises((TypeError, ValueError)):
            Lag(Acct.name, bad)


# ── 3. order_by ───────────────────────────────────────────────

class TestOrderByValidation:

    @pytest.mark.parametrize("bad", [
        "score DESC; DROP TABLE acct; --",
        "(CASE WHEN (SELECT substr(secret,1,1) FROM acct)='S' THEN id END) DESC",
        "score DESC, (SELECT 1)",
        "1",
        "score -- comment",
    ])
    def test_rejects_expressions(self, bad):
        with pytest.raises(ValueError, match="Invalid order_by term"):
            Acct.all().order_by(bad)

    @pytest.mark.parametrize("ok", ["score", "score DESC", "acct.score asc", "score DESC NULLS LAST"])
    async def test_accepts_plain_column_strings(self, engine, ok):
        await Acct.all().order_by(ok)

    async def test_accepts_column_and_agg_expressions(self, engine):
        await Acct.all().order_by(Acct.score.desc, Acct.id)
        rows = await (
            Acct.all().select(Acct.name, Count(Acct.id).label("n"))
                .group_by(Acct.name).order_by(Count(Acct.id).desc)
        )
        assert len(rows) == 2

    def test_rejects_non_string(self):
        with pytest.raises(TypeError):
            Acct.all().order_by(123)

    def test_window_order_by_and_partition_are_validated(self):
        with pytest.raises(ValueError):
            RowNumber().over(order_by=["id) FROM acct; --"])
        with pytest.raises(ValueError):
            RowNumber().over(partition_by=["name, (SELECT 1)"])
        with pytest.raises(ValueError):
            Sum(Acct.score).over(order_by=["id; --"])


# ── 4. 識別子 ────────────────────────────────────────────────

class TestIdentifierValidation:

    def test_agg_label(self):
        with pytest.raises(ValueError, match="Invalid label"):
            Count(Acct.id).label("n FROM acct; --")

    def test_window_label(self):
        with pytest.raises(ValueError, match="Invalid label"):
            RowNumber().over(order_by=[Acct.id.asc]).label("r; --")

    def test_case_label(self):
        with pytest.raises(ValueError, match="Invalid label"):
            Case(When(Acct.score > 1, then="a"), default="b").label("c) --")

    async def test_aggregate_alias(self, engine):
        with pytest.raises(ValueError, match="Invalid aggregate alias"):
            await Acct.all().aggregate(**{"t FROM acct; --": Sum(Acct.score)})

    def test_cte_name(self):
        with pytest.raises(ValueError, match="Invalid CTE name"):
            Acct.all().with_cte("x AS (SELECT 1); --", Acct.all())

    def test_group_by_and_select_strings(self):
        with pytest.raises(ValueError):
            Acct.all().group_by("name; DROP TABLE acct")
        with pytest.raises(ValueError):
            Acct.all().select("name, (SELECT secret FROM acct)")
        with pytest.raises(ValueError):
            Sum("score) FROM acct; --")

    async def test_plain_identifiers_still_work(self, engine):
        rows = await Acct.all().select("name", "acct.score").order_by("name")
        assert [r.name for r in rows] == ["alice", "bob"]
        assert Count("*")._having_expr() == "COUNT(*)"


# ── 5. quote_identifier ───────────────────────────────────────

class TestQuoteIdentifier:

    @pytest.mark.parametrize("eng", [AsyncpgEngine("postgresql://x"), Psycopg3Engine("postgresql://x")])
    def test_postgres_doubles_quotes(self, eng):
        assert eng.quote_identifier('a"b') == '"a""b"'

    def test_mysql_doubles_backticks(self):
        eng = AioMySQLEngine("h", 3306, "u", "p", "d")
        assert eng.quote_identifier("a`b") == "`a``b`"

    def test_sqlite_rejects_closing_bracket(self):
        with pytest.raises(ValueError):
            AioSQLiteEngine(":memory:").quote_identifier("a]; DROP TABLE x; --")

    @pytest.mark.parametrize("bad", ["", "a\x00b"])
    def test_rejects_empty_and_nul(self, bad):
        with pytest.raises(ValueError):
            AioSQLiteEngine(":memory:").quote_identifier(bad)

    def test_table_name_validated_at_definition(self):
        with pytest.raises(ValueError, match="Invalid table name"):
            type("Bad", (Model,), {"Meta": type("Meta", (), {"table_name": "x; DROP TABLE y"})})

    def test_reserved_word_table_name_is_allowed(self):
        cls = type("Sel", (Model,), {"Meta": type("Meta", (), {"table_name": "select"})})
        assert cls._meta.table_name == "select"


# ── 6. DDL パラメータ ────────────────────────────────────────

class TestDDLValidation:

    @pytest.mark.parametrize("bad", ["score > 0); DROP TABLE acct; --", "score > 0 /* x */", "a -- b"])
    def test_check_rejects_statement_tokens(self, bad):
        with pytest.raises(ValueError):
            IntColumn(check=bad)

    def test_check_normal_expression_ok(self):
        assert IntColumn(check="score >= 0").check == "score >= 0"

    def test_on_delete_whitelist(self):
        with pytest.raises(ValueError, match="Invalid on_delete"):
            ForeignKey(Acct, on_delete="CASCADE; DROP TABLE acct")
        assert ForeignKey(Acct, on_delete="set null").on_delete == "SET NULL"

    def test_numeric_type_params(self):
        with pytest.raises(TypeError):
            StrColumn(max_length="10); DROP TABLE acct; --")
        with pytest.raises(TypeError):
            DecimalColumn("10", 2)

    def test_index_must_reference_known_columns(self):
        with pytest.raises(ValueError, match="unknown column"):
            type("Idx", (Model,), {
                "name": StrColumn(),
                "Meta": type("Meta", (), {"table_name": "idx_t", "indexes": [("name", "nope")]}),
            })


# ── 7. URL 伏せ字 ────────────────────────────────────────────

class TestUrlRedaction:

    @pytest.mark.parametrize("url, expected", [
        ("postgresql+asyncpg://app:p%40ss@db:5432/main", "postgresql+asyncpg://app:***@db:5432/main"),
        ("mysql+aiomysql://root:secret@localhost/db", "mysql+aiomysql://root:***@localhost/db"),
        ("postgresql://db/main?user=a&password=secret", "postgresql://db/main?user=a&password=***"),
        ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
    ])
    def test_redact_url(self, url, expected):
        assert redact_url(url) == expected

    async def test_unsupported_url_error_hides_password(self):
        with pytest.raises(ValueError) as exc:
            await kakaorm.connect("oracle://scott:tiger@db/orcl")
        assert "tiger" not in str(exc.value)

    def test_missing_await_warning_hides_password(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            kakaorm.connect("postgresql+asyncpg://u:topsecret@h/db")
            import gc
            gc.collect()
        assert caught
        assert all("topsecret" not in str(w.message) for w in caught)


# ── 8. クエリログ ────────────────────────────────────────────

class TestQueryLogParams:

    async def test_params_hidden_by_default(self, engine, caplog):
        engine.query_logging = True
        try:
            with caplog.at_level(logging.DEBUG, logger="kakaorm.sql"):
                await Acct.where(Acct.secret == "S3CRET").execute()
        finally:
            engine.query_logging = False
        assert "S3CRET" not in caplog.text
        assert "param(s) hidden" in caplog.text

    async def test_params_shown_when_opted_in(self, engine, caplog):
        engine.query_logging = True
        engine.query_log_params = True
        try:
            with caplog.at_level(logging.DEBUG, logger="kakaorm.sql"):
                await Acct.where(Acct.secret == "S3CRET").execute()
        finally:
            engine.query_logging = False
            engine.query_log_params = False
        assert "S3CRET" in caplog.text


# ── 9. マイグレーション ──────────────────────────────────────

class MigTarget(Model):
    name = StrColumn()

    class Meta:
        table_name = "mig_target"


class TestMigrationHardening:

    async def test_autogenerate_rejects_path_traversal(self, engine):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Invalid migration name"):
                await VersionedMigrator(engine).autogenerate([MigTarget], tmpdir, name="../../evil")

    async def test_downgrade_detects_tampered_history(self, engine):
        with tempfile.TemporaryDirectory() as tmpdir:
            m = VersionedMigrator(engine)
            await m.autogenerate([MigTarget], tmpdir, name="init")
            await m.run_files(tmpdir)
            # 履歴テーブルの DOWN SQL を書き換える（アプリ権限での改ざんを想定）
            await engine.execute(
                "UPDATE kakaorm_migrations SET down_sql = %s",
                [json.dumps(["DROP TABLE acct"])],
            )
            with pytest.raises(RuntimeError, match="tampered"):
                await m.downgrade(directory=tmpdir)
            assert await m._table_exists("acct")
            assert await m._table_exists("mig_target")

    async def test_downgrade_refuses_db_only_sql(self, engine):
        with tempfile.TemporaryDirectory() as tmpdir:
            m = VersionedMigrator(engine)
            await m.ensure_history_table()
            await m.record("../../etc/evil", down_sql=json.dumps(["DROP TABLE acct"]))
            with pytest.raises(RuntimeError):
                await m.downgrade(directory=tmpdir)
            await m.record("9999_ghost", down_sql=json.dumps(["DROP TABLE acct"]))
            with pytest.raises(FileNotFoundError):
                await m.downgrade(directory=tmpdir)
            assert await m._table_exists("acct")

    async def test_downgrade_with_directory_uses_file(self, engine):
        with tempfile.TemporaryDirectory() as tmpdir:
            m = VersionedMigrator(engine)
            await m.autogenerate([MigTarget], tmpdir, name="init")
            await m.run_files(tmpdir)
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # directory 指定時は警告なし
                assert await m.downgrade(directory=tmpdir) == 1
            assert not await m._table_exists("mig_target")

    async def test_downgrade_without_directory_warns(self, engine):
        m = VersionedMigrator(engine)
        with pytest.warns(FutureWarning, match="directory"):
            await m.downgrade()

    async def test_steps_zero_does_nothing(self, engine):
        with tempfile.TemporaryDirectory() as tmpdir:
            m = VersionedMigrator(engine)
            await m.autogenerate([MigTarget], tmpdir, name="init")
            await m.run_files(tmpdir)
            assert await m.downgrade(steps=0, directory=tmpdir) == 0
            assert await m._table_exists("mig_target")
            with pytest.raises(ValueError):
                await m.downgrade(steps=-1, directory=tmpdir)
