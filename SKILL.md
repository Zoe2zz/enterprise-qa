---
name: enterprise-qa
description: >-
  当用户消息以 @qa 开头时，必须触发此 skill（企业智能问答助手）。
  支持通过自然语言查询企业内部数据，包括员工信息（部门、上级、项目）、
  考勤数据、绩效考核（结构化数据）或公司制度
  （年假、报销、晋升规则、会议纪要等非结构化知识）。
  支持混合查询（如"王五符合晋升条件吗"），在多轮对话中能继承上下文。
---

# 企业智能问答助手 Skill

## ⚡ 触发规则（必须遵守）

**任何 agent / 龙虾看到此 SKILL.md 后必须遵守以下规则：**

1. 用户消息以 **`@hr`** 开头 → **必须触发**本 skill，走企业问答引擎
2. 去掉 `@hr` 前缀，把剩余文本直接传给问答引擎（不要绕路去搜记忆、搜文件）
3. 本 skill 对 HR/企业相关问题有最高优先级
4. 不支持 `@hr` 前缀的非 HR 问题，不要由此 skill 处理

本 Skill 提供了企业问答引擎的全部核心模块。通过 `{baseDir}/scripts/enterprise_qa/`
下的 Python 包实现查询逻辑，**不需要额外的终端 UI 或对话人设**。

## 前置条件

- Python 3.10+
- 依赖：`pip install -r {baseDir}/scripts/requirements.txt`
- 配置文件 `{baseDir}/scripts/config.yaml` 已填入有效的 API Key

## 核心接口

```python
from enterprise_qa import create_qa_engine

engine = create_qa_engine("{baseDir}/scripts/config.yaml")
answer = engine.answer("张三的部门是什么？", history_text="")
# → "张三的部门是研发部。\n> 来源：Employees 表"
```

## 使用方式（给我/OpenClaw代理）

### 1. 导入引擎

```python
import sys, os
sys.path.insert(0, r"{baseDir}/scripts")
from enterprise_qa import create_qa_engine

qa_engine = create_qa_engine(r"{baseDir}/scripts/config.yaml")
```

### 2. 对话历史管理

QA 历史**单独存储**，不混入代理的通用记忆。格式是一个 JSON 列表，放在
`{baseDir}/scripts/qa_history.json`：

```json
[
  {"q": "张三的部门是什么？", "a": "张三的部门是研发部。"},
  {"q": "那张三呢？", "a": "张三的部门是研发部。"}
]
```

**管理规则：**
- 每次收到问题 → 从 `qa_history.json` 读取历史 → 格式化为 `history_text` → 调用 `engine.answer()`
- 回答后 → 追加到 `qa_history.json`（保留最近 10 轮）
- 用户说"清空对话/重置" → 清空 `qa_history.json`

### 3. 格式化历史

```python
import json

def _load_qa_history() -> list:
    path = r"{baseDir}/scripts/qa_history.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def _save_qa_history(history: list):
    path = r"{baseDir}/scripts/qa_history.json"
    # 只保留最近 10 轮
    history = history[-10:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _format_history(history: list) -> str:
    lines = []
    for item in history:
        lines.append(f"用户：{item['q']}")
        lines.append(f"助手：{item['a']}")
    return "\n".join(lines)
```

### 4. 完整处理流程

```
用户提问
  ↓
[我] 从 qa_history.json 读取历史 → 格式化
  ↓
[我] 调用 engine.answer(question, history_text)
  ↓     ├── safety.py     ← SQL注入 + 命令检测
  ↓     ├── nlu.py        ← LLM 意图提取
  ↓     ├── intent.py     ← 关键词分类（后备）
  ↓     ├── db_engine.py  ← NL→SQL 查询
  ↓     └── kb_engine.py  ← BM25 知识库检索
  ↓
[我] 拿到回答 → 显示给用户 → 写入 qa_history.json
```

**要点：**
- 不需要再包装"小Q"人设——我（OpenClaw代理）就是对话界面
- 多轮对话由 `qa_history.json` 维护，不混入我的个人记忆
- 用户说退出/重置 QA 会话时清空 `qa_history.json`

## 架构概览

```
用户提问
    │
    ▼
┌──────────────────────┐
│   safety.py          │  ← SQL注入 + 终端命令检测
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│   nlu.py             │  ← LLM 意图提取（咀嚼层）
└──────┬───────────────┘
       │
       ├── 无实体 ──► 追问澄清
       │
       └── 有实体 ──► intent.py 关键词分类（NLU 后备）
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
       db_engine    kb_engine   编排器混合
       NL→SQL      BM25 检索   DB+KB 融合
```

## 核心模块

| 模块 | 职责 |
|------|------|
| `safety.py` | 输入安全检测 |
| `nlu.py` | LLM 意图+实体提取，支持多轮继承 |
| `intent.py` | 关键词意图分类（NLU 后备） |
| `db_engine.py` | NL→SQL 生成+执行 |
| `kb_engine.py` | 纯 Python BM25 检索 |
| `orchestrator.py` | 三阶段编排，HYBRID 双路解耦 |
| `config.py` | 配置加载 |

## 测试（无需 API）

```bash
cd {baseDir}/scripts
python -m pytest tests/ -v
```
