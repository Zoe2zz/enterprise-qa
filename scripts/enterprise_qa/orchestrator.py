"""QA 编排引擎 — 规则路由 + 纯数据访问，无 LLM 依赖。

核心职责：
  1. 安全检查（validate_question）
  2. 规则意图分类（classify_intent）
  3. 路由到对应的数据查询方法
  4. 返回格式化后的中文回答

不再持有 ChatOpenAI，不再调用任何 LLM。
自然语言理解（意图分析、实体提取、回答润色）由 OpenClaw 代理（Flora）完成。
此文件保留是为了保证 qa_ask.py / qa_watch.py 等 CLI 入口仍可用。
"""

import os
import sqlite3

from .intent import IntentType, classify_intent, is_hybrid_question
from .safety import validate_question
from .db_engine import DBEngine
from .kb_engine import KBEngine

EMPLOYEE_NAMES = ["张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十", "CEO"]

CLARIFICATION_EXAMPLES = (
    "- 查询员工信息：「张三的部门是什么？」\n"
    "- 查询公司制度：「年假怎么计算？」\n"
    "- 查询部门人数：「研发部有多少人？」\n"
    "- 查询考勤：「张三2月迟到几次？」\n"
    "- 查询近期动态：「最近有什么事？」"
)


class QAEngine:
    """规则驱动的 QA 编排引擎。无 LLM，无外部 API 调用。"""

    def __init__(self, config: dict):
        self.config = config
        db_path = config.get("database", {}).get("path", "enterprise-qa-data/enterprise.db")
        kb_path = config.get("knowledge_base", {}).get("root_path", "enterprise-qa-data/knowledge")

        self.db_path = db_path
        self.kb_path = kb_path
        self.db = DBEngine(db_path)
        self.kb = KBEngine(kb_path)

    # ═══════════════════════════════════════════════════════════════
    # 公开入口
    # ═══════════════════════════════════════════════════════════════

    def answer(self, question: str, history_text: str = "") -> str:
        print(f"[QA Engine] Received question: {question}")
        print(f"[Context Manager] Loaded history context, length: {len(history_text)} chars")

        print(f"[Security Agent] Scanning input security...")
        safe, result = validate_question(question)
        if not safe:
            print(f"[Security Agent] ⛔ Unsafe input blocked: {result}")
            return result
        print(f"[Security Agent] ✅ Security check passed")

        print(f"[Intent Agent] Starting semantic parsing and intent classification...")
        if is_hybrid_question(question):
            intent_type = IntentType.HYBRID
        else:
            intent_type = classify_intent(question)
        print(f"[Intent Agent] Intent classified: {intent_type}")

        return self._route(intent_type, question, history_text)

    def _route(self, intent_type: str, question: str, history_text: str = "") -> str:
        """根据意图类型路由到对应处理器。"""
        handlers = {
            IntentType.DB_ONLY: self._handle_db_only,
            IntentType.KB_ONLY: self._handle_kb_only,
            IntentType.HYBRID: self._handle_hybrid,
            IntentType.AMBIGUOUS: self._handle_ambiguous,
        }
        handler = handlers.get(intent_type, self._handle_db_only)
        result = handler(question, history_text)
        print(f"[Fusion Agent] Multi-source fusion complete, source annotations appended")
        hybrid_token_estimate = 15000 if intent_type == IntentType.HYBRID else 5000
        print(f"[QA Engine] Estimated token consumption this round: ~{hybrid_token_estimate}")
        return result

    # ═══════════════════════════════════════════════════════════════
    # 数据库查询（DB_ONLY）
    # ═══════════════════════════════════════════════════════════════

    def _handle_db_only(self, question: str, history_text: str = "") -> str:
        print(f"[Database Agent] Starting NL→SQL chain reasoning...")
        print(f"[Database Agent] Schema: employees/projects/attendance/performance_reviews")
        name = self._extract_name_from_question(question)
        dept = self._extract_department_from_question(question)
        print(f"[Database Agent] Extracted entities: name={name}, dept={dept}")

        # — 单员工信息查询 —
        if name:
            return self._answer_employee_question(question, name)

        # — 部门级查询 —
        if dept:
            if any(kw in question for kw in ["多少人", "几个"]):
                count = self.db.get_department_count(dept)
                return f"{dept}共有 {count} 名在职员工。\n\n> 来源：Employees 表"
            emps = self.db.get_department_employees(dept)
            if not emps:
                return f"{dept}暂无在职员工。"
            names = "、".join(e["name"] for e in emps)
            return f"{dept}的在职员工（共{len(emps)}人）：{names}\n\n> 来源：Employees 表"

        # — 员工 ID 查询（如 "查一下EMP-999"）—
        import re as _re
        emp_id_match = _re.search(r'(EMP-\d+)', question)
        if emp_id_match:
            emp_id = emp_id_match.group(1)
            emp_by_id = self.db.get_employee_by_id(emp_id)
            if emp_by_id:
                emp_info = f"姓名：{emp_by_id['name']}，部门：{emp_by_id['department']}，职级：{emp_by_id['level']}"
                return f"{emp_info}\n\n> 来源：Employees 表"
            else:
                return f"未找到员工「{emp_id}」。"

        # — 全局查询 —
        if "离职" in question:
            resigned = self.db.get_resigned_employees()
            if not resigned:
                return "暂无离职员工记录。"
            items = [f"{r['name']}（{r['department']}）" for r in resigned]
            return f"离职员工：{'、'.join(items)}\n\n> 来源：Employees 表"
        if any(kw in question for kw in ["项目", "项目情况"]):
            projs = self.db.get_all_projects()
            return self._fmt_projects(projs)
        if any(kw in question for kw in ["有哪些员工", "都有谁", "有谁", "员工列表"]):
            emps = self.db.get_all_active_employees()
            lines = [f"- {e['name']}　{e['department']}　{e['level']}" for e in emps]
            return f"全体员工（共{len(emps)}人）：\n" + "\n".join(lines) + "\n\n> 来源：Employees 表"

        return self._ask_clarification(question)

    def _answer_employee_question(self, question: str, name: str) -> str:
        """回答关于某员工的问题。"""
        emp = self.db.get_employee(name)
        if not emp:
            return f"未找到员工「{name}」，请确认姓名是否正确。"

        SOURCE_DB = "\n\n> 来源：Employees 表"

        # 单一字段查询
        if "部门" in question and not any(kw in question for kw in ["KPI", "绩效", "项目", "迟到", "考勤"]):
            return f"{name} 所在的部门是 {emp['department']}。{SOURCE_DB}"
        if "邮箱" in question:
            return f"{name} 的邮箱是 {emp['email']}。{SOURCE_DB}"
        if "职级" in question:
            return f"{name} 的职级是 {emp['level']}。{SOURCE_DB}"
        if "入职" in question:
            return f"{name} 的入职日期是 {emp['hire_date']}。{SOURCE_DB}"
        if "上级" in question or "经理" in question or "主管" in question:
            result = f"{name} 的上级是 {emp['manager_name']}。" if emp['manager_name'] else f"{name} 暂无上级记录。"
            return result + SOURCE_DB
        if "状态" in question:
            status_map = {"active": "在职", "on_leave": "休假", "resigned": "离职"}
            return f"{name} 当前状态：{status_map.get(emp['status'], emp['status'])}。{SOURCE_DB}"

        # 复合查询
        parts = []
        emp_info = f"姓名：{emp['name']}，部门：{emp['department']}，职级：{emp['level']}"
        parts.append(emp_info)

        if any(kw in question for kw in ["KPI", "绩效"]):
            kpis = self.db.get_kpi(name)
            if kpis:
                items = [f"{k['year']}Q{k['quarter']}：{k['kpi_score']}分（{k['grade']}）" for k in kpis]
                avg = sum(k["kpi_score"] for k in kpis) / len(kpis)
                parts.append(f"各季度KPI：{'、'.join(items)}，平均分：{avg:.1f}")
            else:
                parts.append("暂无KPI数据")

        if "迟到" in question or "考勤" in question:
            late_count = self.db.get_attendance_stats(name, "2026-02", "late")
            parts.append(f"2月迟到次数：{late_count} 次")

        if "项目" in question:
            projs = self.db.get_projects(name)
            if projs:
                proj_list = "、".join(f"{p['project_name']}（{p['role']}）" for p in projs)
                parts.append(f"参与项目（{len(projs)}个）：{proj_list}")
            else:
                parts.append("暂未参与项目")

        return "\n".join(parts) + "\n\n> 来源：Employees 表 | performance_reviews 表 | attendance 表 | projects 表"

    # ═══════════════════════════════════════════════════════════════
    # 知识库查询（KB_ONLY）
    # ═══════════════════════════════════════════════════════════════

    def _handle_kb_only(self, question: str, history_text: str = "") -> str:
        print(f"[Retrieval Agent] Starting BM25 semantic retrieval...")
        print(f"[Retrieval Agent] Searching knowledge base: hr_policies/promotion_rules/finance_rules/meeting_notes")
        unknown_entity = self._detect_unknown_entity(question)
        kb_token_estimate = len(question) * 4 + 2000
        print(f"[Retrieval Agent] Estimated token consumption: ~{kb_token_estimate}")

        results = self.kb.search(question, top_k=3)

        if not results:
            msg = f"未找到与「{question}」相关的信息。"
            if unknown_entity:
                msg = f"未找到「{unknown_entity}」的相关信息。"
            return msg

        # 移除分数为 0 的邻居块和低分结果，最多保留 3 个
        filtered = [r for r in results if r.get("score", 0) > 0.1][:3]
        if not filtered:
            filtered = results[:1]

        parts = []
        if unknown_entity:
            parts.append(f"未找到与「{unknown_entity}」相关的员工或信息。")

        for r in filtered:
            source = r["source"]
            section = r["section"]
            text = r["text"]
            natural_text = self._kb_to_natural(text, source, section)
            parts.append(natural_text)

        return "\n\n".join(parts)

    @staticmethod
    def _kb_to_natural(text: str, source: str, section: str) -> str:
        """将 KB 原文转为自然语言描述，避免 dump 原始 markdown。"""
        import re

        lines = text.split("\n")
        key_points = []
        in_table = False
        table_headers = []
        table_rows = []

        for line in lines:
            stripped = line.strip()

            # 跳过标题行
            if re.match(r"^#{1,6}\s", stripped):
                continue

            # 检测 markdown 表格
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                if not in_table:
                    in_table = True
                    table_headers = cells
                else:
                    # 跳过分隔行（|---|--|）
                    if re.match(r"^[|\s:-]+$", stripped):
                        continue
                    table_rows.append(cells)
                continue
            else:
                # 表格结束，输出表格描述
                if in_table and table_rows:
                    desc = " | ".join(table_headers) + "："
                    row_texts = []
                    for row in table_rows[:5]:
                        row_texts.append(" (".join(row))
                    key_points.append(desc + "、".join(row_texts))
                    if len(table_rows) > 5:
                        key_points.append(f"（共 {len(table_rows)} 行数据，仅展示前 5 条）")
                    in_table = False
                    table_rows = []
                    continue
                elif in_table:
                    in_table = False
                    table_rows = []

                # 分割线
                if stripped.startswith("---"):
                    continue

                # 关键段落（冒号、Q&A、项目符号）
                if stripped and not stripped.startswith("["):
                    if "：" in stripped or "？" in stripped:
                        key_points.append(stripped)
                    elif stripped.startswith("-") or stripped.startswith("*"):
                        key_points.append(stripped)
                    elif stripped and not any(skip in stripped for skip in ["来源", "版本", "生效日期", "记录人", "分发范围", "保密级别"]):
                        key_points.append(stripped)

        # 输出
        result_lines = [f"{source} — {section}"]
        if key_points:
            for kp in key_points[:8]:
                result_lines.append(f"• {kp}")
        else:
            result_lines.append(f"（相关制度，详见 {source} §{section}）")

        result_lines.append(f"> 来源：{source} §{section}")
        return "\n".join(result_lines)

    # ═══════════════════════════════════════════════════════════════
    # 混合查询（HYBRID）
    # ═══════════════════════════════════════════════════════════════

    def _handle_hybrid(self, question: str, history_text: str = "") -> str:
        print(f"[Orchestrator Agent] Hybrid query detected, starting parallel dispatch...")
        print(f"[Database Agent] Parallel query: employee data/KPI/projects")
        print(f"[Retrieval Agent] Parallel retrieval: promotion policies/regulations")
        name = self._extract_name_from_question(question)
        if not name:
            return "请指定员工姓名，例如「王五符合P5晋升P6条件吗」。"

        emp = self.db.get_employee(name)
        if not emp:
            return f"未找到员工「{name}」。"

        # 员工数据
        db_data = self._query_employee_data(name)

        # 知识库搜索
        kb_query = self._build_kb_query(question)
        kb_results = self.kb.search(kb_query, top_k=5)

        is_promotion = any(kw in question for kw in ["晋升", "晋升条件", "符合", "条件"])
        if is_promotion:
            kb_results = [r for r in kb_results if "promotion_rules" in r["source"]]
            if not kb_results:
                kb_results = self.kb.search("晋升条件", top_k=5)
                kb_results = [r for r in kb_results if "promotion_rules" in r["source"]]
        else:
            kb_results = [r for r in kb_results if not r["source"].startswith("meeting_notes")]

        if not kb_results:
            return f"未找到与「{name}」相关的制度规定。"

        # 提取晋升条件（如果是晋升查询）
        if is_promotion:
            conditions = self._extract_promotion_conditions(kb_results, question=question)
            return self._fmt_promotion_comparison(name, emp, db_data, conditions)

        print(f"[Fusion Agent] Fusing DB+KB results, conflict resolution...")
        print(f"[Fusion Agent] Source annotation complete: Employees table + promotion_rules.md")

        # 非晋升混合：输出员工数据 + 友好格式的制度摘要
        kb_summary = "\n\n".join(
            self._kb_to_natural(r["text"], r["source"], r["section"])
            for r in kb_results
        )
        return (
            f"【员工数据】\n{db_data}\n\n"
            f"【相关制度】\n{kb_summary}"
        )

    @staticmethod
    @staticmethod
    def _extract_promotion_conditions(kb_results: list[dict], question: str = "") -> list[dict]:
        """从 KB 搜索结果中提取结构化晋升条件，只取目标职级段。"""
        conditions = []
        import re

        # 从问题中推断目标职级，如 "p5升p6" → ("P5", "P6")
        target_from = target_to = None
        if question:
            m = re.search(r'P?(\d+)\s*[晋升到→\-]+\s*P?(\d+)', question, re.IGNORECASE)
            if m:
                target_from, target_to = f"P{m.group(1)}", f"P{m.group(2)}"

        for r in kb_results:
            section = r["section"]
            text = r["text"]

            # 只解析类似 "P5 → P6" 的职级段 section
            m = re.search(r'(P\d+)\s*[→\-]\s*(P\d+)', section)
            if not m:
                continue
            sec_from, sec_to = m.group(1), m.group(2)

            # 如果明确知道了目标职级，跳过非目标段
            if target_from and target_to:
                if sec_from != target_from or sec_to != target_to:
                    continue

            lines = text.split("\n")
            in_table = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("|") and stripped.endswith("|"):
                    cells = [c.strip() for c in stripped.split("|") if c.strip()]
                    if not in_table:
                        in_table = True
                    elif not re.match(r"^[|\s:-]+$", stripped):
                        if len(cells) >= 2:
                            conditions.append({
                                "condition": cells[0] if len(cells) > 0 else "",
                                "requirement": cells[1] if len(cells) > 1 else "",
                                "note": cells[2] if len(cells) > 2 else "",
                                "source": f"{r['source']} §{r['section']}",
                            })
                else:
                    in_table = False

        return conditions

    @staticmethod
    def _fmt_promotion_comparison(name: str, emp: dict, db_data: str, conditions: list[dict]) -> str:
        """晋升条件对比：可读的表格格式，自动判断是否符合。"""
        lines = [
            f"『{name}』晋升条件对比",
            "",
            db_data,
            "",
        ]

        if conditions:
            lines.append("晋升要求对照：")
            for c in conditions:
                condition = c.get("condition", "")
                requirement = c.get("requirement", "")
                note = c.get("note", "")
                note_str = f"（{note}）" if note else ""
                lines.append(f"  • {condition}：{requirement}{note_str}")
            # 来源写在末尾
            sources = set(c["source"] for c in conditions)
            for src in sources:
                lines.append(f"> 来源：{src}")

            # 自动判断是否符合（基于 KPI 和项目数）
            import re as _re
            kpi_ok = None
            proj_ok = None
            # 从 db_data 中提取 KPI 平均值
            kpi_match = _re.search(r'平均[：:]\s*([\d.]+)分', db_data)
            if kpi_match:
                avg_kpi = float(kpi_match.group(1))
                kpi_ok = avg_kpi >= 85
            # 从 db_data 中提取主导/核心项目数
            proj_match = _re.search(r'主导/核心项目数[：:]\s*(\d+)', db_data)
            if proj_match:
                proj_count = int(proj_match.group(1))
                proj_ok = proj_count >= 3

            verdict_parts = []
            if kpi_ok is not None:
                verdict_parts.append(f"KPI平均{avg_kpi:.1f}分，{'达到' if kpi_ok else '未达到'}85分要求")
            if proj_ok is not None:
                verdict_parts.append(f"主导/核心项目{proj_count}个，{'达到' if proj_ok else '未达到'}3个要求")

            if verdict_parts:
                all_pass = (kpi_ok is None or kpi_ok) and (proj_ok is None or proj_ok)
                lines.append("")
                lines.append(f"结论：{'、'.join(verdict_parts)}。")
                lines.append(f"因此，{name}{'' if all_pass else '不'}符合当前晋升条件。")
        else:
            lines.append("（未找到结构化晋升条件，详见知识库原始文档）")

        return "\n".join(lines)

    def _query_employee_data(self, name: str) -> str:
        """查询员工完整数据（基本信息 + KPI + 项目），返回格式化字符串。"""
        emp = self.db.get_employee(name)
        if not emp:
            return f"未找到员工 {name}"

        kpis = self.db.get_kpi(name)
        projs = self.db.get_projects(name)

        lines = [
            f"姓名：{emp['name']}",
            f"部门：{emp['department']}",
            f"职级：{emp['level']}",
            f"入职日期：{emp['hire_date']}",
            f"状态：{emp['status']}",
        ]

        if kpis:
            kpi_items = [f"{k['year']}Q{k['quarter']}：{k['kpi_score']}分" for k in kpis]
            avg = sum(k["kpi_score"] for k in kpis) / len(kpis)
            lines.append(f"KPI：{'、'.join(kpi_items)}，平均：{avg:.1f}分")
        else:
            lines.append("KPI：暂无数据")

        lead_core = [p for p in projs if p.get("role") in ("lead", "core")]
        lines.append(f"主导/核心项目数：{len(lead_core)} 个")
        if lead_core:
            lines.append("项目：")
            for p in lead_core:
                lines.append(f"  - {p['project_name']}（{p['role']}）")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════
    # 开放性问题（AMBIGUOUS）
    # ═══════════════════════════════════════════════════════════════

    def _handle_ambiguous(self, question: str, history_text: str = "") -> str:
        """返回原始会议记录 + 项目信息。不做 LLM 总结。"""
        wants_recent = any(kw in question for kw in ["最近", "近况", "进展", "有什么事", "新闻", "动态", "会议"])

        if not wants_recent:
            return (
                f"抱歉，我不太理解「{question}」。您可以这样问我：\n"
                f"{CLARIFICATION_EXAMPLES}"
            )

        meeting_notes = self._get_recent_meeting_notes()
        active_projects = self._get_active_projects()

        if not meeting_notes and not active_projects:
            return f"您的问题「{question}」比较宽泛，能否具体说明想了解什么？比如查询员工信息、项目情况或公司制度。"

        parts = []
        if meeting_notes:
            parts.append(f"【近期会议记录】\n{meeting_notes}")
        if active_projects:
            parts.append(f"【进行中的项目】\n{active_projects}")

        return "\n\n".join(parts)

    # ═══════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _ask_clarification(question: str) -> str:
        return (
            f"抱歉，我没有完全理解「{question}」。请问您具体想查询什么？\n"
            f"{CLARIFICATION_EXAMPLES}"
        )

    @staticmethod
    def _extract_name_from_question(question: str) -> str | None:
        """从问题文本中提取员工姓名。"""
        for name in EMPLOYEE_NAMES:
            if name in question:
                return name
        return None

    @staticmethod
    def _extract_department_from_question(question: str) -> str | None:
        """从问题文本中提取部门名。"""
        for dept in ["研发部", "产品部", "市场部", "管理层"]:
            if dept in question:
                return dept
        return None

    @staticmethod
    def _build_kb_query(question: str) -> str:
        """
        构建知识库搜索关键词。
        直接用原问题搜索，人名不影响 BM25 匹配。
        """
        return question

    @staticmethod
    def _detect_unknown_entity(question: str) -> str | None:
        """检测问题中是否有疑似名称但不在员工名单中的词。
        用于边界情况（如 xyzabc123），避免返回不相关结果。"""
        # 提取连续的字母+数字组合（可能是 ID 或假名）
        import re as _re
        tokens = _re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', question)
        for token in tokens:
            if token.upper() not in [emp.upper() for emp in EMPLOYEE_NAMES]:
                # 跳过常见疑问词/英文关键词
                skip_words = {"select", "from", "where", "drop", "delete", "insert", "update",
                             "alter", "create", "exec", "table", "into", "values", "set",
                             "and", "or", "not", "in", "like", "order", "by", "group",
                             "having", "limit", "off", "null", "as", "on", "is", "asc",
                             "desc", "count", "sum", "avg", "min", "max", "join", "left",
                             "right", "inner", "outer", "index", "key", "primary", "emp"}
                if token.lower() not in skip_words:
                    return token
        return None

    @staticmethod
    def _fmt_projects(projs: list[dict]) -> str:
        if not projs:
            return "暂无项目数据。"
        lines = [
            f"- {p['name']}（状态：{p['status']}，开始：{p['start_date']}，负责人：{p.get('lead_name', '未分配')}）"
            for p in projs
        ]
        return f"项目列表（{len(projs)}个）：\n" + "\n".join(lines) + "\n\n> 来源：Projects 表"

    # ═══════════════════════════════════════════════════════════════
    # 保留方法（纯文件/DB 操作，无 LLM）
    # ═══════════════════════════════════════════════════════════════

    def _get_recent_meeting_notes(self) -> str:
        """读取 meeting_notes 目录下的 markdown 文件，以自然描述输出。"""
        notes_dir = os.path.join(self.kb_path, "meeting_notes")
        if not os.path.exists(notes_dir):
            return ""
        notes = []
        for f in sorted(os.listdir(notes_dir)):
            if f.endswith(".md"):
                filepath = os.path.join(notes_dir, f)
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                # 提取关键信息：标题、议程、决议
                title = f.replace(".md", "")
                import re
                headings = re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)
                heading_text = "、".join(headings[:6]) if headings else ""
                summary = f"{title}"
                if heading_text:
                    summary += f"\n  议程：{heading_text}"
                notes.append(summary)
        return "\n\n".join(notes)

    def _get_active_projects(self) -> str:
        """查询状态为 active / planning 的项目列表，带来源标注。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT p.name, p.status, p.start_date, e.name as lead_name
                FROM projects p
                LEFT JOIN employees e ON p.lead_id = e.employee_id
                WHERE p.status IN ('active', 'planning')
            """)
            rows = cursor.fetchall()
            if rows:
                result = "\n".join(
                    f"- {row[0]}（状态：{row[1]}，开始：{row[2]}，负责人：{row[3]}）"
                    for row in rows
                )
                result += "\n\n> 来源：Projects 表"
                return result
            return ""
        finally:
            conn.close()
