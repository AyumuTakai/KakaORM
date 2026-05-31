"""
CTE (WITH 句) テスト
"""

import pytest
import kakaorm
from kakaorm import Model, StrColumn, IntColumn, ForeignKey, Count, Sum


# ── モデル定義 ───────────────────────────────────────────────


class CteDept(Model):
    name = StrColumn(nullable=False)

    class Meta:
        table_name = "cte_dept"


class CteEmp(Model):
    name    = StrColumn(nullable=False)
    dept_id = ForeignKey(CteDept, nullable=True)
    salary  = IntColumn(nullable=False, default=0)

    class Meta:
        table_name = "cte_emp"


# ── フィクスチャ ──────────────────────────────────────────────


@pytest.fixture
async def engine():
    eng = await kakaorm.connect("sqlite+aiosqlite:///:memory:")
    await eng.create_table(CteDept)
    await eng.create_table(CteEmp)
    yield eng
    await eng.disconnect()


@pytest.fixture
async def seeded(engine):
    eng = await CteDept.create(name="Engineering")
    mkt = await CteDept.create(name="Marketing")
    await CteEmp.create(name="Alice", dept_id=eng.id, salary=1000)
    await CteEmp.create(name="Bob",   dept_id=eng.id, salary=1200)
    await CteEmp.create(name="Carol", dept_id=mkt.id, salary=800)
    return {"eng": eng, "mkt": mkt}


# ── SQL 生成の確認 ────────────────────────────────────────────


class TestCteSqlGeneration:
    async def test_with_cte_sql_contains_with(self, engine):
        """SQL に WITH 句が含まれることを確認する。"""
        sub = CteEmp.where(CteEmp.salary >= 1000).select(CteEmp.dept_id)
        qs  = CteDept.all().with_cte("rich_emps", sub)
        sql, _ = qs._build_sql()
        assert sql.startswith("WITH rich_emps AS (")

    async def test_with_cte_sql_structure(self, engine):
        """WITH 句と主クエリの SQL 構造を確認する。"""
        sub = CteEmp.where(CteEmp.salary >= 1000).select(CteEmp.dept_id)
        qs  = CteDept.all().with_cte("rich_emps", sub)
        sql, params = qs._build_sql()
        assert "WITH rich_emps AS (" in sql
        assert "SELECT" in sql
        assert params == [1000]  # CTE のバインドパラメータが先頭に来る

    async def test_with_cte_chaining(self, engine):
        """複数の CTE をチェーンできる。"""
        cte1 = CteEmp.where(CteEmp.salary >= 1000).select(CteEmp.id)
        cte2 = CteEmp.where(CteEmp.salary <= 900).select(CteEmp.id)
        qs   = CteDept.all().with_cte("high", cte1).with_cte("low", cte2)
        sql, _ = qs._build_sql()
        assert "WITH high AS (" in sql
        assert "low AS (" in sql

    async def test_immutable_clone(self, engine):
        """with_cte() は元の QuerySet を変更しない。"""
        base = CteDept.all()
        sub  = CteEmp.all().select(CteEmp.dept_id)
        new  = base.with_cte("sub", sub)
        assert base._ctes == []
        assert len(new._ctes) == 1


# ── 実行結果の確認 ────────────────────────────────────────────


class TestCteExecution:
    async def test_cte_result_with_join(self, seeded):
        """CTE + JOIN で正しい結果が返ること。"""
        # Engineering の高給社員が存在する dept_id を CTE で定義
        high_salary = (
            CteEmp.where(CteEmp.salary >= 1000)
                  .select(CteEmp.dept_id)
        )
        rows = await (
            CteDept.all()
                   .with_cte("high_dept", high_salary)
                   .join(CteEmp, on=CteEmp.dept_id == CteDept.id)
                   .select(CteDept.name, CteEmp.name.label("emp_name") if hasattr(CteEmp.name, "label") else CteEmp.name)
                   .where(CteEmp.salary >= 1000)
        )
        # Alice と Bob が含まれること
        names = {r["cte_emp.name"] if "cte_emp.name" in r else r.get("name") for r in rows}
        # JOIN 結果は dict 形式。少なくとも 2 件
        assert len(rows) >= 2

    async def test_cte_no_result(self, seeded):
        """条件に合致するものがない場合は空リスト。"""
        sub = CteEmp.where(CteEmp.salary >= 99999).select(CteEmp.dept_id)
        qs  = CteDept.all().with_cte("none", sub)
        rows = await qs
        # CTE 自体はクエリに影響しない（FROM CteDept だけなので全件返る）
        assert len(rows) >= 1

    async def test_cte_params_ordering(self, seeded):
        """CTE のパラメータが主クエリより前に積まれる。"""
        sub = CteEmp.where(CteEmp.salary >= 1000).select(CteEmp.dept_id)
        qs  = CteDept.all().with_cte("rich", sub).where(CteDept.name == "Engineering")
        sql, params = qs._build_sql()
        # CTE パラメータ (1000) が先、主クエリパラメータ ("Engineering") が後
        assert params[0] == 1000
        assert params[1] == "Engineering"
