---
name: enterprise-qa
description: >-
  Must trigger this skill when a user message starts with @qa (Enterprise QA Assistant).
  Supports querying enterprise data via natural language, including employee info
  (department, manager, projects), attendance, performance reviews (structured data),
  or company policies (annual leave, expense reimbursement, promotion rules,
  meeting notes — unstructured knowledge).
  Supports hybrid queries (e.g., "Is Wang Wu eligible for promotion?"),
  with multi-turn context inheritance.
---

# Enterprise QA Assistant Skill

## ⚡ Trigger Rules (Mandatory)

**Any agent seeing this SKILL.md MUST follow these rules:**

1. User message starts with **`@hr`** → **MUST trigger** this skill, route to QA engine
2. Strip the `@hr` prefix, pass remaining text directly to the QA engine (do not search memory or files)
3. This skill has highest priority for HR/enterprise-related questions
4. Non-HR questions without `@hr` prefix should NOT be handled by this skill

This Skill provides all core modules of the enterprise QA engine. Query logic is
implemented via the Python package at `{baseDir}/scripts/enterprise_qa/`,
**No additional terminal UI or dialog persona required**.

## Prerequisites

- Python 3.10+
- Dependencies: `pip install -r {baseDir}/scripts/requirements.txt`
- Config file `{baseDir}/scripts/config.yaml` should have valid API Key

## Core Interface

```python
from enterprise_qa import create_qa_engine

engine = create_qa_engine("{baseDir}/scripts/config.yaml")
answer = engine.answer("What is Zhang San's department?", history_text="")
# → "Zhang San is in the R&D department.\n> Source: Employees table"
```

## Usage (for me / OpenClaw Agent)

### 1. Import Engine

```python
import sys, os
sys.path.insert(0, r"{baseDir}/scripts")
from enterprise_qa import create_qa_engine

qa_engine = create_qa_engine(r"{baseDir}/scripts/config.yaml")
```

### 2. Dialog History Management

QA history is stored **separately**, not mixed into the agent's general memory.
Format is a JSON list stored at `{baseDir}/scripts/qa_history.json`:

```json
[
  {"q": "What is Zhang San's department?", "a": "Zhang San is in R&D."},
  {"q": "And Zhang San?", "a": "Zhang San is in R&D."}
]
```

**Management rules:**
- Each question → read history from `qa_history.json` → format as `history_text` → call `engine.answer()`
- After answering → append to `qa_history.json` (keep last 10 turns)
- User says "clear/reset" → clear `qa_history.json`

### 3. Format History

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
    history = history[-10:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _format_history(history: list) -> str:
    lines = []
    for item in history:
        lines.append(f"User: {item['q']}")
        lines.append(f"Assistant: {item['a']}")
    return "\n".join(lines)
```

### 4. Complete Processing Flow

```
User asks question
  ↓
[Agent] Read history from qa_history.json → format
  ↓
[Agent] Call engine.answer(question, history_text)
  ↓     ├── safety.py     ← SQL injection + command detection
  ↓     ├── nlu.py        ← LLM intent extraction
  ↓     ├── intent.py     ← Keyword classification (fallback)
  ↓     ├── db_engine.py  ← NL→SQL query
  ↓     └── kb_engine.py  ← BM25 knowledge base retrieval
  ↓
[Agent] Get answer → display to user → write to qa_history.json
```

**Key points:**
- No need to wrap a "Xiao Q" persona — I (the OpenClaw agent) am the dialog interface
- Multi-turn dialog maintained by `qa_history.json`, not mixed into my personal memory
- User says exit/reset QA session → clear `qa_history.json`

## Architecture Overview

```
User query
    │
    ▼
┌──────────────────────┐
│   safety.py          │  ← SQL injection + shell command detection
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│   nlu.py             │  ← LLM intent extraction (pre-digest)
└──────┬───────────────┘
       │
       ├── No entity ──► Prompt for clarification
       │
       └── Has entity ──► intent.py keyword classification (NLU fallback)
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
       db_engine    kb_engine   Orchestrator hybrid
       NL→SQL      BM25        DB+KB fusion
```

## Core Modules

| Module | Responsibility |
|--------|---------------|
| `safety.py` | Input security scanning |
| `nlu.py` | LLM intent + entity extraction, multi-turn support |
| `intent.py` | Keyword intent classification (NLU fallback) |
| `db_engine.py` | NL→SQL generation + execution |
| `kb_engine.py` | Pure Python BM25 retrieval |
| `orchestrator.py` | Three-stage orchestration, HYBRID dual-path decoupling |
| `config.py` | Configuration loading |

## Testing (no API required)

```bash
cd {baseDir}/scripts
python -m pytest tests/ -v
```
