import re


class IntentType:
    DB_ONLY = "DB_ONLY"
    KB_ONLY = "KB_ONLY"
    HYBRID = "HYBRID"
    AMBIGUOUS = "AMBIGUOUS"


DB_KEYWORDS = [
    "部门", "邮箱", "上级", "经理", "项目", "迟到", "考勤", "绩效",
    "KPI", "职级", "入职", "主管", "同事", "员工", "多少人",
    "谁", "多少", "几个", "哪些", "负责", "参与",
]

DB_DATA_KEYWORDS = [
    "部门", "邮箱", "上级", "经理", "项目", "职级", "入职",
    "主管", "同事", "员工",
]

DB_ACTION_KEYWORDS = [
    "迟到", "考勤", "绩效", "KPI",
    "多少人", "谁", "多少", "几个", "哪些", "负责", "参与",
]

KB_KEYWORDS = [
    "年假", "请假", "病假", "事假", "调休", "加班", "报销", "出差",
    "制度", "规定", "规则", "流程", "怎么", "如何", "标准", "规范",
    "远程办公", "五险一金", "试用期", "福利", "体检", "晋升",
    "调薪", "培训", "费用", "标准", "条件", "要求",
    "扣钱", "扣款", "处罚", "宵夜", "打车",
]

HYBRID_KEYWORDS = [
    "符合", "晋升条件", "满足", "有资格", "能不能升", "够不够", "达标",
]

POLICY_KEYWORDS = [
    "晋升", "条件", "符合", "报销", "年假", "加班", "调休",
    "请假", "病假", "事假", "出差", "标准", "要求", "规则",
    "规定", "制度", "福利",
]

EMPLOYEE_NAMES = ["张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十", "CEO"]
DEPARTMENT_NAMES = ["研发部", "产品部", "市场部", "管理层"]

VAGUE_PATTERNS = [
    r"最近", r"有什么事", r"在忙", r"怎么样", r"情况", r"进展", r"近况",
]

SQL_PATTERNS = [
    r"SELECT", r"FROM", r"WHERE", r"DROP", r"DELETE",
    r"INSERT", r"UPDATE", r"ALTER", r"CREATE",
    r"OR\s+'\d+'='\d+'", r"OR\s+\d+\s*=\s*\d+",
]

ENTITY_REFERENCE_PATTERNS = [
    r"CEO",
    r"离职",
    r"[那这]个\s*员工",
    r"[张李王赵周吴郑孙冯陈褚卫蒋沈韩杨朱秦尤许何吕施]\w",
]


def is_hybrid_question(question: str) -> bool:
    has_employee = any(name in question for name in EMPLOYEE_NAMES)
    has_policy = any(kw in question for kw in POLICY_KEYWORDS)
    return has_employee and has_policy


def _has_entity_reference(question: str) -> bool:
    if any(name in question for name in EMPLOYEE_NAMES):
        return True
    for pattern in ENTITY_REFERENCE_PATTERNS:
        if re.search(pattern, question):
            return True
    return False


def _is_vague_question(question: str) -> bool:
    for pattern in VAGUE_PATTERNS:
        if re.search(pattern, question):
            has_entity = _has_entity_reference(question)
            has_specific = any(kw in question for kw in DB_KEYWORDS + KB_KEYWORDS)
            if not has_entity and not has_specific:
                return True
    return False


def _looks_like_sql(question: str) -> bool:
    for pattern in SQL_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return True
    return False


def classify_intent(question: str) -> str:
    if _looks_like_sql(question):
        return IntentType.DB_ONLY

    if _is_vague_question(question):
        return IntentType.AMBIGUOUS

    db_score = 0
    kb_score = 0
    hybrid_score = 0

    for kw in DB_KEYWORDS:
        if kw in question:
            db_score += 1
    for kw in KB_KEYWORDS:
        if kw in question:
            kb_score += 1
    for kw in HYBRID_KEYWORDS:
        if kw in question:
            hybrid_score += 1

    has_entity = _has_entity_reference(question)
    has_department = any(dept in question for dept in DEPARTMENT_NAMES)
    has_project_id = bool(re.search(r'PRJ-\d+', question))
    has_employee_id = bool(re.search(r'EMP-\d+', question))

    if has_entity:
        db_score += 2
    if has_department:
        db_score += 1
    if has_project_id:
        db_score += 1
    if has_employee_id:
        db_score += 1

    if hybrid_score > 0 and has_entity:
        return IntentType.HYBRID

    if kb_score >= 2 and kb_score > db_score:
        return IntentType.KB_ONLY
    if db_score >= 1 and db_score > kb_score:
        if not has_entity and not has_department and not has_employee_id:
            has_data_kw = any(kw in question for kw in DB_DATA_KEYWORDS)
            if not has_data_kw:
                return IntentType.KB_ONLY
        return IntentType.DB_ONLY
    if db_score >= 1 and kb_score >= 1:
        if has_entity or has_employee_id:
            return IntentType.HYBRID
        return IntentType.KB_ONLY
    if kb_score >= 1:
        return IntentType.KB_ONLY
    if db_score >= 1:
        return IntentType.DB_ONLY

    return IntentType.AMBIGUOUS
