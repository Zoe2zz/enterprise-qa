import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from enterprise_qa.config import load_config
from enterprise_qa.safety import validate_question, is_sql_injection_attempt
from enterprise_qa.intent import classify_intent, IntentType
from enterprise_qa.kb_engine import KBEngine
from enterprise_qa.db_engine import DBEngine


# ==================== 测试固件 ====================

@pytest.fixture(scope="module")
def config():
    return load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))


@pytest.fixture(scope="module")
def kb():
    return KBEngine(os.path.join(os.path.dirname(__file__), "..", "knowledge"))


@pytest.fixture(scope="module")
def db():
    cfg = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    return DBEngine(cfg["database"]["path"])


@pytest.fixture(scope="module")
def db_conn():
    db_path = os.path.join(os.path.dirname(__file__), "..", "enterprise.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ==================== 1. 安全检测测试 ====================

class TestSafety:
    def test_normal_question(self):
        assert validate_question("张三的部门是什么？") == (True, "张三的部门是什么？")

    def test_sql_injection_select(self):
        assert is_sql_injection_attempt("SELECT * FROM users WHERE '1'='1")

    def test_sql_injection_or(self):
        assert is_sql_injection_attempt("' OR '1'='1")

    @pytest.mark.parametrize("injection", [
        "DROP TABLE employees",
        "DELETE FROM employees",
        "UPDATE employees SET name='hacker'",
        "INSERT INTO employees VALUES (1)",
        "ALTER TABLE employees",
        "SELECT * FROM users; --",
        "SELECT * FROM users /* comment */",
    ])
    def test_all_injection_patterns(self, injection):
        assert validate_question(injection)[0] is False

    def test_empty_question(self):
        assert validate_question("")[0] is False

    def test_whitespace_question(self):
        assert validate_question("   ")[0] is False

    @pytest.mark.parametrize("cmd", [
        "python main.py",
        "pip install flask",
        "npm run dev",
        "git push origin main",
        "ls -la",
        "cd my-answer",
    ])
    def test_command_input_detected(self, cmd):
        safe, msg = validate_question(cmd)
        assert safe is False
        assert "终端命令" in msg


# ==================== 2. 意图分类测试 ====================

class TestIntent:
    def test_db_employee_dept(self):
        assert classify_intent("张三的部门是什么？") == IntentType.DB_ONLY

    def test_db_employee_email(self):
        assert classify_intent("李四的邮箱是多少？") == IntentType.DB_ONLY

    def test_db_project_list(self):
        assert classify_intent("张三负责哪些项目？") == IntentType.DB_ONLY

    def test_db_dept_count(self):
        assert classify_intent("研发部有多少人？") == IntentType.DB_ONLY

    def test_db_attendance(self):
        assert classify_intent("张三2月迟到几次？") == IntentType.DB_ONLY

    def test_kb_vacation(self):
        assert classify_intent("年假怎么计算？") == IntentType.KB_ONLY

    def test_kb_late_fee(self):
        assert classify_intent("迟到几次扣钱？") == IntentType.KB_ONLY

    def test_kb_reimbursement(self):
        assert classify_intent("差旅费报销标准是什么？") == IntentType.KB_ONLY

    def test_hybrid_promotion(self):
        assert classify_intent("王五符合P5晋升P6条件吗？") == IntentType.HYBRID

    def test_ambiguous_recent(self):
        assert classify_intent("最近有什么事？") == IntentType.AMBIGUOUS

    def test_sql_like_input(self):
        assert classify_intent("SELECT * FROM users WHERE '1'='1") == IntentType.DB_ONLY

    def test_kb_nonsense(self):
        assert classify_intent("xyzabc123 怎么报销") == IntentType.KB_ONLY

    def test_employee_id_query(self):
        assert classify_intent("查一下 EMP-999") == IntentType.DB_ONLY

    def test_db_project_query_routes_db(self):
        assert classify_intent("查一下项目情况") == IntentType.DB_ONLY

    def test_kb_only_single_keyword(self):
        assert classify_intent("报销") == IntentType.KB_ONLY

    def test_hybrid_equal_scores_with_employee(self):
        assert classify_intent("张三 报销 年假") == IntentType.HYBRID

    def test_db_with_employee(self):
        assert classify_intent("张三的邮箱是多少") == IntentType.DB_ONLY

    def test_db_ceo_department(self):
        assert classify_intent("CEO的部门是什么") == IntentType.DB_ONLY

    def test_db_resigned_employee(self):
        assert classify_intent("离职员工是哪个部门的") == IntentType.DB_ONLY

    def test_db_generic_person_ref(self):
        assert classify_intent("那个员工是哪个部门的") == IntentType.DB_ONLY

    def test_kb_action_without_entity(self):
        assert classify_intent("迟到会怎么样") == IntentType.KB_ONLY


# ==================== 3. 数据库测试 ====================

class TestDatabase:
    def test_table_exists(self, db_conn):
        r = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'").fetchone()
        assert r is not None

    def test_zhangsan_dept(self, db_conn):
        r = db_conn.execute("SELECT department FROM employees WHERE employee_id='EMP-001'").fetchone()
        assert r["department"] == "研发部"

    def test_lisi_manager(self, db_conn):
        r = db_conn.execute("SELECT manager_id FROM employees WHERE employee_id='EMP-002'").fetchone()
        assert r["manager_id"] == "EMP-000"

    def test_wangwu_profile(self, db_conn):
        r = db_conn.execute("SELECT * FROM employees WHERE employee_id='EMP-003'").fetchone()
        assert r["name"] == "王五" and r["department"] == "产品部" and r["level"] == "P5"

    def test_rd_count(self, db_conn):
        r = db_conn.execute("SELECT COUNT(*) as c FROM employees WHERE department='研发部' AND status='active'").fetchone()
        assert r["c"] == 4

    def test_zhangsan_project_count(self, db_conn):
        r = db_conn.execute("SELECT COUNT(*) as c FROM project_members WHERE employee_id='EMP-001'").fetchone()
        assert r["c"] == 4

    def test_zhangsan_feb_late(self, db_conn):
        r = db_conn.execute("SELECT COUNT(*) as c FROM attendance WHERE employee_id='EMP-001' AND status='late' AND date LIKE '2026-02-%'").fetchone()
        assert r["c"] == 2

    def test_wangwu_avg_kpi(self, db_conn):
        r = db_conn.execute("SELECT AVG(kpi_score) as avg FROM performance_reviews WHERE employee_id='EMP-003'").fetchone()
        assert abs(r["avg"] - 80.0) < 0.01

    def test_nonexistent_employee(self, db_conn):
        assert db_conn.execute("SELECT * FROM employees WHERE employee_id='EMP-999'").fetchone() is None


# ==================== 4. 数据库引擎单元测试 ====================

class TestDBEngine:
    def test_is_safe_sql_select(self, db):
        assert db._is_safe_sql("SELECT * FROM employees")

    def test_is_safe_sql_mixed_case(self, db):
        assert db._is_safe_sql("select * from employees")

    def test_is_safe_sql_drop(self, db):
        assert not db._is_safe_sql("DROP TABLE employees")

    def test_is_safe_sql_delete(self, db):
        assert not db._is_safe_sql("DELETE FROM employees")

    def test_is_safe_sql_insert(self, db):
        assert not db._is_safe_sql("INSERT INTO employees VALUES (1)")

    def test_is_safe_sql_update(self, db):
        assert not db._is_safe_sql("UPDATE employees SET name='x'")

    def test_is_safe_sql_non_select(self, db):
        assert not db._is_safe_sql("EXEC sp_help")

    def test_execute_valid(self, db):
        r = db._execute_sql("SELECT name FROM employees WHERE employee_id='EMP-001'")
        assert r[0]["name"] == "张三"

    def test_execute_empty(self, db):
        assert db._execute_sql("SELECT * FROM employees WHERE employee_id='EMP-999'") == []

    def test_execute_invalid(self, db):
        r = db._execute_sql("SELECT * FROM nonexistent")
        assert isinstance(r, dict) and "error" in r

    def test_execute_join(self, db):
        r = db._execute_sql("SELECT p.name FROM projects p JOIN project_members pm ON p.project_id=pm.project_id WHERE pm.employee_id='EMP-001'")
        assert len(r) >= 1

    def test_aggregate(self, db):
        r = db._execute_sql("SELECT COUNT(*) as c FROM employees WHERE department='研发部' AND status='active'")
        assert r[0]["c"] == 4


# ==================== 5. 知识库引擎测试 ====================

class TestKnowledgeBase:
    def test_loads_documents(self, kb):
        assert kb.retriever.doc_count > 0

    def test_search_vacation(self, kb):
        results = kb.search("年假怎么计算", top_k=3)
        assert len(results) > 0

    def test_search_late(self, kb):
        results = kb.search("迟到扣钱", top_k=3)
        assert len(results) > 0

    def test_search_promotion(self, kb):
        results = kb.search("P5晋升P6条件", top_k=3)
        assert len(results) > 0

    def test_search_finance(self, kb):
        results = kb.search("差旅费报销标准", top_k=3)
        assert len(results) > 0

    def test_nonsense_term(self, kb):
        results = kb.search("xyzabc123", top_k=3)
        assert len([r for r in results if r["score"] >= 0.5]) == 0

    def test_source_tracking(self, kb):
        results = kb.search("年假", top_k=1)
        assert "source" in results[0] and "section" in results[0]


# ==================== 6. 编排器测试 ====================

class TestOrchestrator:
    def test_safety_intercepts_sql(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        result = engine.answer("SELECT * FROM users WHERE '1'='1")
        assert "不安全" in result or "拦截" in result

    def test_safety_empty_question(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        result = engine.answer("")
        assert "有效" in result

    def test_db_employee_dept(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        result = engine.answer("张三的部门是什么")
        assert "研发部" in result

    def test_db_ceo_manager(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        result = engine.answer("张三的上级是谁")
        assert "CEO" in result

    def test_hybrid_promotion_raw_data(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        result = engine.answer("王五符合P5晋升P6条件吗")
        assert "晋升条件对比" in result
        assert "晋升要求对照" in result
        assert "来源：promotion_rules" in result


# ==================== 7. 配置测试 ====================

class TestConfig:
    def test_config_loads(self, config):
        assert "database" in config and "knowledge_base" in config

    def test_config_db_path(self, config):
        assert os.path.exists(config["database"]["path"])


# ==================== 8. 编排器辅助方法测试 ====================

class TestOrchestratorHelpers:
    def test_get_active_projects(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        projects = engine._get_active_projects()
        assert projects and "ReMe" in projects

    def test_get_recent_meeting_notes(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        notes = engine._get_recent_meeting_notes()
        assert "全员大会" in notes or "技术同步" in notes

    def test_no_meeting_notes_dir(self):
        from enterprise_qa import create_qa_engine
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        engine.kb_path = "/nonexistent"
        assert engine._get_recent_meeting_notes() == ""

    def test_no_active_projects(self):
        from enterprise_qa import create_qa_engine
        from unittest.mock import patch
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        engine = create_qa_engine(cfg_path)
        with patch('sqlite3.connect') as mock:
            mock.return_value.cursor.return_value.fetchall.return_value = []
            assert engine._get_active_projects() == ""


# ==================== 9. 配置环境变量覆盖测试 ====================

class TestConfigOverride:
    def test_env_db_override(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ENTERPRISE_QA_DB_PATH", "/fake/db.db")
            mp.delenv("ENTERPRISE_QA_KB_PATH", raising=False)
            cfg = load_config(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
            assert cfg["database"]["path"] == "/fake/db.db"

    def test_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")


# ==================== 10. KB引擎边界测试 ====================

class TestKBEdgeCases:
    def test_search_empty_corpus(self):
        kb = KBEngine(os.path.join(os.path.dirname(__file__), "..", "knowledge"))
        results = kb.search("", top_k=3)
        assert results == []

    def test_empty_kb_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KBEngine(tmpdir)
            assert kb.retriever.doc_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
