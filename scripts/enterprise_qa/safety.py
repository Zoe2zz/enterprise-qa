import re

DANGEROUS_PATTERNS = [
    "SELECT", "DROP", "DELETE", "INSERT", "UPDATE",
    "ALTER", "CREATE", "UNION", "OR 1=1", "OR '1'='1",
    "OR \"1\"=\"1", "--", "/*", "*/", ";",
]

COMMAND_PREFIXES = [
    "python", "pip", "npm", "yarn", "node", "git",
    "cd ", "ls ", "dir ", "rm ", "cp ", "mv ",
    "chmod", "echo", "cat ", "grep", "find",
    "docker", "kubectl", "curl ", "wget ",
]


def is_sql_injection_attempt(text: str) -> bool:
    text_upper = text.upper().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in text_upper:
            return True
    return False


def is_command_input(text: str) -> bool:
    stripped = text.strip().lower()
    for prefix in COMMAND_PREFIXES:
        if stripped.startswith(prefix):
            return True
    return False


def validate_question(question: str) -> tuple[bool, str]:
    if not question or not question.strip():
        return False, "请输入有效的问题。"

    if is_sql_injection_attempt(question):
        return False, "检测到不安全的输入，已拦截。请使用自然语言提问。"

    if is_command_input(question):
        return False, f"看起来您输入的是一个终端命令，而不是想问的问题。请直接输入您想查询的内容，比如「张三的部门是什么？」"

    return True, question.strip()
