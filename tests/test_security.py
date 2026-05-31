"""
セキュリティ回帰テスト
======================
ORM に関連する既知の脆弱性カテゴリを検証する。

カバーするカテゴリ:
  1. マスアサインメント (Mass Assignment)       — create() / save()
  2. update() カラム名インジェクション           — 修正済み
  3. WHERE 句値のパラメータ化                    — SQLインジェクション耐性
  4. LIKE / IN 句のパラメータ化                  — SQLインジェクション耐性
  5. NULL インジェクション                       — IS NULL 正規化
  6. セカンドオーダーインジェクション            — 保存→再利用時の安全性
  7. order_by() への生文字列渡し                 — 開発者向け注意事項の文書化
  8. insert_into() 宛先カラム名の検証            — 修正済み
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn, BoolColumn


# ── テスト用モデル ─────────────────────────────────────────────

class Victim(Model):
    name     = StrColumn(nullable=False)
    role     = StrColumn(nullable=False, default="user")
    secret   = StrColumn(nullable=True)
    views    = IntColumn(nullable=False, default=0)
    is_admin = BoolColumn(nullable=False, default=False)

    class Meta:
        table_name = "victim"


class Archive(Model):
    title   = StrColumn(nullable=False)
    content = StrColumn(nullable=True)

    class Meta:
        table_name = "archive"


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(Victim)
    await eng.create_table(Archive)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    u1 = await Victim.create(name="Alice", role="user",  views=10, is_admin=False)
    u2 = await Victim.create(name="Bob",   role="admin", views=20, is_admin=True)
    return {"alice": u1, "bob": u2}


# ──────────────────────────────────────────────────────────────
# 1. マスアサインメント (Mass Assignment)
# ──────────────────────────────────────────────────────────────

class TestMassAssignment:
    """
    ユーザー入力を直接 create() / save() に渡すと、意図しない
    フィールドが書き込まれる恐れがある（マスアサインメント脆弱性）。
    """

    async def test_create_rejects_unknown_fields(self, engine):
        """モデルに定義されていないフィールドは TypeError で拒否される。"""
        with pytest.raises(TypeError, match="Unknown field"):
            await Victim.create(name="Eve", role="user", is_superuser=True)

    async def test_create_rejects_internal_attrs(self, engine):
        """_is_new など内部属性もモデルカラムでないため拒否される。"""
        with pytest.raises(TypeError, match="Unknown field"):
            await Victim.create(name="Eve", role="user", _is_new=False)

    async def test_create_rejects_engine_override(self, engine):
        """_engine をカラムとして渡そうとしても拒否される。"""
        with pytest.raises(TypeError, match="Unknown field"):
            await Victim.create(name="Eve", role="user", _engine="evil")

    async def test_user_dict_with_extra_keys_is_rejected(self, engine):
        """JSON ボディ等から生成した辞書を ** 展開した場合も拒否される。"""
        user_input = {
            "name": "Eve",
            "role": "user",
            "is_admin": True,        # 許可フィールドだが意図しない昇格
            "unknown_col": "injected",  # 未知フィールド → TypeError
        }
        with pytest.raises(TypeError, match="Unknown field"):
            await Victim.create(**user_input)

    async def test_known_field_privilege_escalation_is_possible_without_allowlist(self, engine):
        """
        既知フィールドへの意図しない書き込みはアプリ層で防ぐ必要がある。
        ORM は未知フィールドのみ拒否し、既知フィールドの権限チェックは行わない。
        この挙動を文書化するテスト（アプリ側で allowlist 実装が必要）。
        """
        user_input = {"name": "Eve", "role": "user", "is_admin": True}
        eve = await Victim.create(**user_input)
        # ORM は is_admin=True を通す → アプリ側でフィールド制限が必要
        assert eve.is_admin is True


# ──────────────────────────────────────────────────────────────
# 2. update() カラム名インジェクション（修正済み）
# ──────────────────────────────────────────────────────────────

class TestUpdateColumnInjection:
    """
    QuerySet.update() のカラム名（キーワード引数名）が SQL に直接展開される
    問題を修正済みであることを検証する。
    """

    async def test_update_rejects_unknown_column(self, engine, seeded):
        """未知のカラム名は ValueError で拒否される。"""
        with pytest.raises(ValueError, match="Unknown column"):
            await Victim.where(Victim.id == seeded["alice"].id).update(
                nonexistent_col="injected"
            )

    async def test_update_rejects_injection_payload_in_key(self, engine, seeded):
        """カラム名に SQL メタキャラクタを含む場合も ValueError で拒否される。"""
        payload = {"is_admin = true, dummy": "x"}
        with pytest.raises(ValueError, match="Unknown column"):
            await Victim.where(Victim.id == seeded["alice"].id).update(**payload)

    async def test_update_rejects_semicolon_injection(self, engine, seeded):
        """セミコロンを使ったステートメント分割インジェクションを拒否する。"""
        payload = {"views": 0, "name = 'hacked'; --": "x"}
        with pytest.raises(ValueError, match="Unknown column"):
            await Victim.where(Victim.id == seeded["alice"].id).update(**payload)

    async def test_update_normal_usage_still_works(self, engine, seeded):
        """修正後も正常な update() が動作すること。"""
        await Victim.where(Victim.id == seeded["alice"].id).update(views=999)
        alice = await Victim.get(Victim.id == seeded["alice"].id)
        assert alice.views == 999

    async def test_update_multiple_valid_columns(self, engine, seeded):
        """複数の正常カラムを同時に更新できること。"""
        await Victim.where(Victim.id == seeded["alice"].id).update(
            views=500, role="moderator"
        )
        alice = await Victim.get(Victim.id == seeded["alice"].id)
        assert alice.views == 500
        assert alice.role == "moderator"

    async def test_update_rejects_mixed_valid_and_injected(self, engine, seeded):
        """正常カラムと不正カラムが混在する場合も拒否される。"""
        payload = {"views": 1, "role = 'admin'; --": "injected"}
        with pytest.raises(ValueError, match="Unknown column"):
            await Victim.where(Victim.id == seeded["alice"].id).update(**payload)

    async def test_bulk_update_via_request_json_pattern(self, engine, seeded):
        """
        `await Model.where(...).update(**request.json())` パターンで
        攻撃者が制御するキーを持つ JSON を渡した場合に拒否されること。
        """
        attacker_json = {
            "views": 0,
            "is_admin = true, views": 999,
        }
        with pytest.raises(ValueError, match="Unknown column"):
            await Victim.all().update(**attacker_json)


# ──────────────────────────────────────────────────────────────
# 3. WHERE 句値のパラメータ化
# ──────────────────────────────────────────────────────────────

class TestWhereParameterization:
    """
    WHERE 句の値は常にバインドパラメータとして送出され、
    SQL 文字列に直接展開されないことを確認する。
    """

    async def test_string_value_with_single_quote_is_safe(self, engine):
        """シングルクォートを含む値が安全にバインドされること。"""
        await Victim.create(name="O'Brien", role="user")
        result = await Victim.where(Victim.name == "O'Brien")
        assert len(result) == 1
        assert result[0].name == "O'Brien"

    async def test_classic_sqli_payload_in_value_is_safe(self, engine):
        """古典的なSQLiペイロードが値として渡されてもインジェクションされない。"""
        await Victim.create(name="normal", role="user")
        # ペイロードが WHERE の値に入っても、他レコードは取得されない
        payload = "' OR '1'='1"
        results = await Victim.where(Victim.name == payload)
        assert results == []

    async def test_union_based_payload_in_value_is_safe(self, engine):
        """UNION ベースのインジェクションペイロードが値として無害化される。"""
        payload = "x' UNION SELECT id, name, role, secret, views, is_admin FROM victim --"
        results = await Victim.where(Victim.name == payload)
        assert results == []

    async def test_stacked_query_payload_in_value_is_safe(self, engine, seeded):
        """スタックドクエリのペイロードが値として渡されても実行されない。"""
        payload = "Alice'; DROP TABLE victim; --"
        results = await Victim.where(Victim.name == payload)
        assert results == []
        # victim テーブルが DROP されていないことを確認
        count = await Victim.all().count()
        assert count == 2  # seeded には 2 件

    async def test_null_byte_in_value_is_safe(self, engine):
        """NULL バイトを含む値が安全に扱われること。"""
        payload = "Alice\x00evil"
        results = await Victim.where(Victim.name == payload)
        assert results == []


# ──────────────────────────────────────────────────────────────
# 4. LIKE / IN 句のパラメータ化
# ──────────────────────────────────────────────────────────────

class TestLikeAndInParameterization:
    """
    LIKE / IN 句も値をバインドパラメータとして扱うことを確認する。
    """

    async def test_like_with_sqli_payload_is_safe(self, engine, seeded):
        """LIKE のパターンに SQL インジェクションペイロードが含まれても安全。"""
        payload = "Alice' OR 'x'='x"
        results = await Victim.where(Victim.name.like(payload))
        assert results == []

    async def test_in_clause_with_sqli_payload_is_safe(self, engine, seeded):
        """IN リストの要素が SQL ペイロードでも安全にバインドされること。"""
        payloads = ["Alice", "' OR '1'='1", "x' UNION SELECT * FROM victim --"]
        results = await Victim.where(Victim.name.in_(payloads))
        # "Alice" だけが一致し、ペイロードによる追加取得はない
        assert len(results) == 1
        assert results[0].name == "Alice"

    async def test_not_in_clause_with_sqli_payload_is_safe(self, engine, seeded):
        """NOT IN も同様に安全であること。"""
        payload = ["' OR '1'='1"]
        results = await Victim.where(Victim.name.not_in(payload))
        # ペイロードは一致しないためすべてのレコードが返る
        assert len(results) == 2


# ──────────────────────────────────────────────────────────────
# 5. NULL インジェクション / IS NULL 正規化
# ──────────────────────────────────────────────────────────────

class TestNullHandling:
    """
    None との比較が `= NULL` ではなく `IS NULL` / `IS NOT NULL` に
    正規化されることを確認する。
    （`= NULL` は常に偽となり認証バイパスに悪用されうる）
    """

    async def test_equality_with_none_generates_is_null(self, engine):
        """`col == None` が `IS NULL` を生成すること。"""
        clause = Victim.secret == None  # noqa: E711
        assert "IS NULL" in clause.sql
        assert "%s" not in clause.sql  # バインドパラメータは不要

    async def test_inequality_with_none_generates_is_not_null(self, engine):
        """`col != None` が `IS NOT NULL` を生成すること。"""
        clause = Victim.secret != None  # noqa: E711
        assert "IS NOT NULL" in clause.sql
        assert "%s" not in clause.sql

    async def test_is_null_query_returns_correct_rows(self, engine, seeded):
        """IS NULL クエリが正しく動作すること。"""
        await Victim.create(name="NullSecret", role="user", secret=None)
        results = await Victim.where(Victim.secret == None)  # noqa: E711
        assert any(r.name == "NullSecret" for r in results)

    async def test_none_value_in_parameterized_query_does_not_bypass(self, engine, seeded):
        """
        None をバインド値として渡しても IS NULL にはならず、
        認証バイパスに悪用できないこと。
        WHERE `name` = ? に None を渡しても IS NULL とは解釈されない。
        """
        # NULL と等値比較する WHERE は明示的に == None で書く必要がある
        results = await Victim.where(Victim.name == None)  # noqa: E711
        # name が NULL のレコードは存在しないため空リスト
        assert results == []


# ──────────────────────────────────────────────────────────────
# 6. セカンドオーダーインジェクション
# ──────────────────────────────────────────────────────────────

class TestSecondOrderInjection:
    """
    SQLi ペイロードを DB に保存し、後でクエリの値として再利用したとき
    インジェクションが発生しないことを確認する。
    """

    async def test_stored_sqli_payload_does_not_execute_on_refetch(self, engine):
        """
        SQLi ペイロードをレコードとして保存し、そのまま検索条件に
        使っても他のレコードが漏洩しないこと。
        """
        # 正常なレコードを作成
        await Victim.create(name="LegitUser", role="user", secret="TOP_SECRET")

        # ペイロードを name として保存（第一段階）
        payload = "' OR '1'='1"
        await Victim.create(name=payload, role="user", secret="nothing")

        # 保存済みペイロードを取得して検索条件として再利用（第二段階）
        bad_user = await Victim.get(Victim.name == payload)
        results = await Victim.where(Victim.name == bad_user.name)

        # ペイロードが保存されたレコード 1 件だけが返り、LegitUser は漏洩しない
        assert len(results) == 1
        assert results[0].secret != "TOP_SECRET"

    async def test_stored_union_payload_does_not_execute(self, engine):
        """UNION ベースのペイロードを保存・再利用してもインジェクションされない。"""
        union_payload = (
            "x' UNION SELECT id,name,role,secret,views,is_admin "
            "FROM victim WHERE '1'='1"
        )
        await Victim.create(name=union_payload, role="user")
        await Victim.create(name="TargetUser", role="admin", secret="SENSITIVE")

        results = await Victim.where(Victim.name == union_payload)
        # UNION が実行されていれば TargetUser も返るが、返らないこと
        assert len(results) == 1
        assert results[0].name == union_payload

    async def test_update_with_stored_payload_as_value_is_safe(self, engine, seeded):
        """
        DB から取得した値（ペイロード含む）を update() の「値」として
        使っても安全であること（バインドパラメータとして扱われる）。
        """
        payload = "Alice'; UPDATE victim SET is_admin=1; --"
        await Victim.create(name=payload, role="user")

        evil_record = await Victim.get(Victim.name == payload)
        # 取得した name をそのまま別レコードに update()
        await Victim.where(Victim.id == seeded["alice"].id).update(
            name=evil_record.name
        )
        # is_admin が書き換わっていないことを確認
        # (SQLite は BOOLEAN を 0/1 で返すため not を使う)
        alice = await Victim.get(Victim.id == seeded["alice"].id)
        assert not alice.is_admin
        assert alice.name == payload  # 値として正常に保存される


# ──────────────────────────────────────────────────────────────
# 7. order_by() への生文字列渡し（既知の注意点）
# ──────────────────────────────────────────────────────────────

class TestOrderByRawString:
    """
    order_by() は ColumnMeta.asc / .desc を経由するのが安全な使い方。
    生文字列を渡す場合は開発者が責任を持つ必要がある。
    この挙動を文書化するテスト。
    """

    async def test_column_meta_asc_desc_is_safe(self, engine, seeded):
        """ColumnMeta 経由の asc/desc は安全（推奨パターン）。"""
        results = await Victim.all().order_by(Victim.views.asc)
        assert results[0].views <= results[-1].views

    async def test_raw_string_order_by_executes_as_is(self, engine, seeded):
        """
        生文字列は SQL にそのまま展開される。
        ユーザー入力を直接渡してはいけないことを示す（開発者向け注意）。
        """
        # 正常な生文字列は動作する
        results = await Victim.all().order_by("views ASC")
        assert results[0].views <= results[-1].views

    async def test_user_controlled_order_by_is_dangerous(self, engine, seeded):
        """
        ユーザー入力を order_by() に直接渡すのは危険。
        アプリ層で許可済みカラム名のみ受け付けるホワイトリストが必要。
        このテストは「脆弱なパターンが存在する」ことの記録であり、
        発見された場合はアプリ側での対策が必要。
        """
        allowed_columns = {"views", "name", "role"}

        def safe_order_by(user_input: str) -> str:
            col, _, direction = user_input.partition(" ")
            direction = direction.upper()
            if col not in allowed_columns or direction not in ("ASC", "DESC", ""):
                raise ValueError(f"Invalid order_by: {user_input!r}")
            return f"{col} {direction}".strip()

        # 正常入力 → 通過
        safe = safe_order_by("views DESC")
        results = await Victim.all().order_by(safe)
        assert results[0].views >= results[-1].views

        # 不正入力 → アプリ側でブロック
        with pytest.raises(ValueError):
            safe_order_by("views DESC; DROP TABLE victim; --")


# ──────────────────────────────────────────────────────────────
# 8. insert_into() 宛先カラム名の検証（修正済み）
# ──────────────────────────────────────────────────────────────

class TestInsertIntoColumnNames:
    """
    insert_into() の mapping キー（宛先カラム名）が dest_model._meta.columns で
    検証され、update() と同様に不正なカラム名を拒否することを確認する。
    """

    async def test_insert_into_valid_mapping_works(self, engine, seeded):
        """正常な insert_into() が動作すること。"""
        inserted = await (
            Victim.where(Victim.id == seeded["alice"].id)
            .insert_into(Archive, title=Victim.name, content=Victim.role)
        )
        assert inserted == 1
        archives = await Archive.all()
        assert archives[0].title == "Alice"

    async def test_insert_into_mapping_key_is_validated(self, engine, seeded):
        """
        insert_into() の mapping キーに存在しないカラム名を渡すと
        ValueError が発生すること。
        """
        with pytest.raises(ValueError, match="Unknown column"):
            await (
                Victim.where(Victim.id == seeded["alice"].id)
                .insert_into(
                    Archive,
                    title=Victim.name,
                    injected_col=Victim.role,  # Archive に存在しないカラム
                )
            )


# ──────────────────────────────────────────────────────────────
# 9. WHERE 句の論理演算子（AND/OR/NOT）のパラメータ化
# ──────────────────────────────────────────────────────────────

class TestCompoundWhereParameterization:
    """
    AND / OR / NOT で結合した複合条件でもすべての値が
    バインドパラメータとして扱われることを確認する。
    """

    async def test_and_condition_values_are_parameterized(self, engine, seeded):
        """AND 結合でも各値がバインドされる。"""
        payload = "' OR '1'='1"
        results = await Victim.where(
            (Victim.name == "Alice") & (Victim.role == payload)
        )
        assert results == []

    async def test_or_condition_values_are_parameterized(self, engine, seeded):
        """OR 結合でもインジェクションされない。"""
        payload = "user' OR '1'='1"
        results = await Victim.where(
            (Victim.name == "NonExistent") | (Victim.role == payload)
        )
        assert results == []

    async def test_not_condition_values_are_parameterized(self, engine, seeded):
        """NOT 条件の値もバインドされる。"""
        payload = "user' OR '1'='1"
        results = await Victim.where(Victim.role != payload)
        # ペイロードは "user" や "admin" に一致しないため全件返る
        assert len(results) == 2

    async def test_exclude_values_are_parameterized(self, engine, seeded):
        """exclude() も内部的に NOT (clause) に変換され安全。"""
        payload = "' OR '1'='1"
        results = await Victim.all().exclude(Victim.name == payload)
        # ペイロードに一致するレコードはないため全件返る
        assert len(results) == 2
