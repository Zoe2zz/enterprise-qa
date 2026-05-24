# Architecture Reference

## Three-Stage Processing Pipeline

```
Stage 1: NLU Extraction ── LLM parses user intent + extracts key entities (literal only, no guessing)
Stage 2: Entity Check ── No entity → prompt "Which employee or project would you like to query?"
Stage 3: Precise Query ── Entity found → route with entity parameters to data source
```

## Intent Routing

| Route | Condition | Handling |
|-------|-----------|----------|
| DB_ONLY | data keywords + entity present | db_engine NL→SQL |
| KB_ONLY | knowledge base keywords | kb_engine BM25 → LLM formatting |
| HYBRID | employee name + policy keywords | Dual-path: parameterized query + KB name-stripped retrieval |
| AMBIGUOUS | vague question + "recent" etc. | Return meeting notes + active projects |

## Security (Three-Layer Guard)

```
Input layer: safety.py
  ├── SQL injection: SELECT/DROP/OR 1=1/-- etc. 15+ patterns
  └── Shell commands: python/pip/git/cd etc. 20+ prefixes

SQL layer: db_engine._is_safe_sql()
  └── SELECT only, blocks DROP/DELETE/INSERT/UPDATE/ALTER/CREATE/EXEC

Prompt layer: all LLM prompts embed guardrails
  └── Never leak manager_id/employee_id etc.
  └── Answer only what is asked, no extra field dump
```

## Hybrid Query Security Architecture

- **DB path**: strictly uses `WHERE name=?` parameterized queries, no LLM-generated SQL
- **KB path**: strip employee names from query before retrieval to avoid meeting note contamination
- **Doc filtering**: promotion queries limited to `promotion_rules.md` only

## Module Responsibilities

| Module | Responsibility | Key Design |
|--------|---------------|------------|
| config.py | Configuration loading | YAML + env var override |
| safety.py | Security scanning | Regex matching 15+ SQL patterns + 20+ command prefixes |
| nlu.py | Intent + entity extraction | LLM pre-digestion, literal entity only |
| intent.py | Keyword classification | 5 routing rules, predefined names + surname regex |
| db_engine.py | Database querying | Schema-aware SQL generation, security validation |
| kb_engine.py | Knowledge base retrieval | Pure Python BM25, jieba tokenization |
| orchestrator.py | Orchestrator | Three-stage pipeline, HYBRID dual-path decoupling |

## Design Principles

- **Single responsibility**: 7 modules, each with one job
- **Security first**: Input layer + SQL layer + Prompt layer triple protection
- **Hallucination elimination**: LLM extracts literal entities only; no guessing when empty
- **Configuration driven**: All paths configured via config.yaml or env vars
