"""数据库查询引擎 — 纯数据访问层，无 LLM 依赖。

提供一组无状态的纯数据查询方法，供 OpenClaw 代理（Flora）直接调用。
不作任何自然语言处理，不持有 LLM 客户端，不进行自然语言回答生成。
"""

import sqlite3
import re

CURRENT_DATE = "2026-03-27"

SCHEMA_DESCRIPTION = """
Database tables (SQLite):

1. employees (employee info)
   - employee_id (VARCHAR, PK): internal ID, EMP-001 format
   - name (VARCHAR): name in Chinese
   - department (VARCHAR): department
   - level (VARCHAR): P4-P10
   - hire_date (DATE): hire date
   - manager_id (VARCHAR): internal ID of manager
   - email (VARCHAR): email
   - status (VARCHAR): active/on_leave/resigned

2. projects (project records)
   - project_id (VARCHAR, PK): internal ID, PRJ-001 format
   - name (VARCHAR): project name
   - lead_id (VARCHAR): internal ID of project lead
   - status (VARCHAR): planning/active/on_hold/completed
   - start_date (DATE), end_date (DATE), budget (DECIMAL)

3. project_members (project-member mapping)
   - project_id (VARCHAR), employee_id (VARCHAR), role (VARCHAR): lead/core/contributor
   - join_date (DATE)

4. attendance (attendance records)
   - employee_id (VARCHAR), date (DATE), status (VARCHAR): on_time/late/absent/on_leave

5. performance_reviews (performance reviews)
   - employee_id (VARCHAR), year (INTEGER), quarter (INTEGER): 1-4
   - kpi_score (DECIMAL): 0-100, grade (VARCHAR): S/A/B/C

Important context:
- Current date: 2026-03-27 (Asia/Shanghai)
- All time calculations ("this year", "last month", "recent") must be based on 2026-03-27
- Attendance data: only Feb 2026
- Performance data: only 2025 (4 quarters)
- By default, only active employees (status='active') are counted in department/team queries
"""


class DBEngine:
    """纯数据访问引擎。无 LLM，无 prompt，无自然语言输出。"""

    def __init__(self, db_path: str):
        """
        初始化 DB 引擎。

        参数：
            db_path: SQLite 数据库文件路径

        不再接收 llm_config，不再创建 ChatOpenAI 客户端。
        """
        self.db_path = db_path

    # ═══════════════════════════════════════════════════════════════
    # 1. 员工基本信息
    # ═══════════════════════════════════════════════════════════════

    def get_employee(self, name: str) -> dict | None:
        """
        查询单员工基本信息（含上级姓名）。

        返回形如：
            {
                "name": "张三",
                "department": "研发部",
                "email": "zhangsan@example.com",
                "level": "P6",
                "hire_date": "2020-03-01",
                "status": "active",
                "manager_name": "李四"
            }
        未找到返回 None。
        """
        sql = """
            SELECT e.name, e.department, e.email, e.level,
                   e.hire_date, e.status,
                   COALESCE(m.name, '') AS manager_name
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.employee_id
            WHERE e.name = ?
        """
        rows = self._execute_sql(sql, (name,))
        if isinstance(rows, dict) or not rows:
            return None
        return rows[0]

    def get_employee_by_id(self, employee_id: str) -> dict | None:
        """
        按员工 ID（EMP-xxx）查询，返回结构同 get_employee。
        """
        sql = """
            SELECT e.name, e.department, e.email, e.level,
                   e.hire_date, e.status,
                   COALESCE(m.name, '') AS manager_name
            FROM employees e
            LEFT JOIN employees m ON e.manager_id = m.employee_id
            WHERE e.employee_id = ?
        """
        rows = self._execute_sql(sql, (employee_id,))
        if isinstance(rows, dict) or not rows:
            return None
        return rows[0]

    # ═══════════════════════════════════════════════════════════════
    # 2. 员工行为统计
    # ═══════════════════════════════════════════════════════════════

    def get_projects(self, name: str) -> list[dict]:
        """
        查询某员工参与的所有项目。

        返回：
            [
                {
                    "project_name": "ReMe",
                    "role": "lead",
                    "status": "active",
                    "start_date": "2026-01-15"
                },
                ...
            ]
        未参与任何项目返回 []。
        """
        sql = """
            SELECT p.name AS project_name, pm.role,
                   p.status, p.start_date
            FROM projects p
            JOIN project_members pm ON p.project_id = pm.project_id
            JOIN employees e ON pm.employee_id = e.employee_id
            WHERE e.name = ?
            ORDER BY pm.role
        """
        rows = self._execute_sql(sql, (name,))
        if isinstance(rows, dict):
            return []
        return rows

    def get_kpi(self, name: str) -> list[dict]:
        """
        查询某员工全部 KPI 记录。

        返回：
            [
                { "year": 2025, "quarter": 1, "kpi_score": 95.0, "grade": "S" },
                ...
            ]
        无记录返回 []。
        """
        sql = """
            SELECT pr.year, pr.quarter, pr.kpi_score, pr.grade
            FROM performance_reviews pr
            JOIN employees e ON pr.employee_id = e.employee_id
            WHERE e.name = ?
            ORDER BY pr.year, pr.quarter
        """
        rows = self._execute_sql(sql, (name,))
        if isinstance(rows, dict):
            return []
        return rows

    def get_attendance(self, name: str, month: str = "2026-02") -> list[dict]:
        """
        查询某员工指定月份考勤记录。

        参数：
            name: 员工姓名
            month: 格式 "YYYY-MM"，默认 "2026-02"（数据只覆盖此月）

        返回：
            [
                { "date": "2026-02-03", "status": "on_time" },
                ...
            ]
        """
        sql = """
            SELECT a.date, a.status
            FROM attendance a
            JOIN employees e ON a.employee_id = e.employee_id
            WHERE e.name = ? AND a.date LIKE ?
            ORDER BY a.date
        """
        like_pattern = month + "-%"
        rows = self._execute_sql(sql, (name, like_pattern))
        if isinstance(rows, dict):
            return []
        return rows

    def get_attendance_stats(self, name: str, month: str = "2026-02",
                             status_type: str = "late") -> int:
        """
        查询某员工指定月份指定考勤类型的次数。

        示例：get_attendance_stats("张三", "2026-02", "late") → 2
        """
        sql = """
            SELECT COUNT(*) AS count
            FROM attendance a
            JOIN employees e ON a.employee_id = e.employee_id
            WHERE e.name = ? AND a.date LIKE ? AND a.status = ?
        """
        like_pattern = month + "-%"
        rows = self._execute_sql(sql, (name, like_pattern, status_type))
        if isinstance(rows, dict) or not rows:
            return 0
        return rows[0]["count"]

    # ═══════════════════════════════════════════════════════════════
    # 3. 部门级查询
    # ═══════════════════════════════════════════════════════════════

    def get_department_employees(self, department: str) -> list[dict]:
        """
        查询某部门所有在职员工列表。

        返回：
            [
                { "name": "张三", "level": "P6", "email": "zhangsan@example.com" },
                ...
            ]
        """
        sql = """
            SELECT name, level, email
            FROM employees
            WHERE department = ? AND status = 'active'
            ORDER BY name
        """
        rows = self._execute_sql(sql, (department,))
        if isinstance(rows, dict):
            return []
        return rows

    def get_department_count(self, department: str) -> int:
        """查询某部门在职员工总数。"""
        sql = """
            SELECT COUNT(*) AS count
            FROM employees
            WHERE department = ? AND status = 'active'
        """
        rows = self._execute_sql(sql, (department,))
        if isinstance(rows, dict) or not rows:
            return 0
        return rows[0]["count"]

    def get_employees_by_manager(self, manager_name: str) -> list[dict]:
        """
        查询某上级管理的所有员工。

        返回：
            [
                { "name": "张三", "department": "研发部", "level": "P6" },
                ...
            ]
        """
        sql = """
            SELECT e.name, e.department, e.level
            FROM employees e
            JOIN employees m ON e.manager_id = m.employee_id
            WHERE m.name = ? AND e.status = 'active'
            ORDER BY e.name
        """
        rows = self._execute_sql(sql, (manager_name,))
        if isinstance(rows, dict):
            return []
        return rows

    # ═══════════════════════════════════════════════════════════════
    # 4. 全局查询
    # ═══════════════════════════════════════════════════════════════

    def get_all_active_employees(self) -> list[dict]:
        """返回所有在职员工 [{ name, department, level }, ...]"""
        sql = """
            SELECT name, department, level
            FROM employees
            WHERE status = 'active'
            ORDER BY department, name
        """
        rows = self._execute_sql(sql)
        if isinstance(rows, dict):
            return []
        return rows

    def get_all_projects(self) -> list[dict]:
        """
        返回所有项目。

        返回：
            [
                {
                    "name": "ReMe",
                    "status": "active",
                    "lead_name": "张三",
                    "start_date": "2026-01-15",
                    "budget": 500000.0
                },
                ...
            ]
        """
        sql = """
            SELECT p.name, p.status, p.start_date, p.budget,
                   COALESCE(e.name, '未分配') AS lead_name
            FROM projects p
            LEFT JOIN employees e ON p.lead_id = e.employee_id
            ORDER BY p.start_date
        """
        rows = self._execute_sql(sql)
        if isinstance(rows, dict):
            return []
        return rows

    def get_resigned_employees(self) -> list[dict]:
        """返回所有离职员工 [{ name, department, email }, ...]"""
        sql = """
            SELECT name, department, email
            FROM employees
            WHERE status = 'resigned'
            ORDER BY name
        """
        rows = self._execute_sql(sql)
        if isinstance(rows, dict):
            return []
        return rows

    # ═══════════════════════════════════════════════════════════════
    # 5. 辅助 / 安全
    # ═══════════════════════════════════════════════════════════════

    def raw_query(self, sql: str) -> list[dict]:
        """
        原始 SQL 查询接口。

        仅限调试和紧急场景，返回 list[dict]。
        会经过 _is_safe_sql 安全拦截（只允许 SELECT）。
        调用方负责格式化结果，此方法不做自然语言输出。
        """
        if not self._is_safe_sql(sql):
            raise ValueError("不安全的 SQL 语句，已拦截")
        result = self._execute_sql(sql)
        if isinstance(result, dict):
            raise RuntimeError(f"SQL 执行错误: {result.get('error', 'unknown')}")
        return result

    @staticmethod
    def is_safe_sql(sql: str) -> bool:
        """
        （公开版本）安全检测。

        返回 True 如果 SQL 是安全的 SELECT 查询。
        """
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith("SELECT"):
            return False
        dangerous = ["DROP", "DELETE", "INSERT", "UPDATE",
                     "ALTER", "CREATE", "EXEC"]
        for kw in dangerous:
            if re.search(rf'\b{kw}\b', sql_stripped):
                return False
        return True

    # ═══════════════════════════════════════════════════════════════
    # 6. 内部方法（原有核心实现，保留不变）
    # ═══════════════════════════════════════════════════════════════

    def _execute_sql(self, sql: str, params: tuple = ()) -> list[dict]:
        """
        执行 SQL 并返回行列表。

        支持参数化查询（? 占位符）。
        出错时返回 {"error": "错误信息"}（保持向后兼容）。

        参数：
            sql: SQL 语句（支持 ? 占位符）
            params: 参数元组，默认空
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description] if cursor.description else []
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def _is_safe_sql(self, sql: str) -> bool:
        """内部安全检测（保留现有实现不变）。"""
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith("SELECT"):
            return False
        dangerous = ["DROP", "DELETE", "INSERT", "UPDATE",
                     "ALTER", "CREATE", "EXEC"]
        for kw in dangerous:
            if re.search(rf'\b{kw}\b', sql_stripped):
                return False
        return True
