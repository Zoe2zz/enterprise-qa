# 架构参考

## 三阶段处理流程

```
Stage 1: NLU 提取 ── LLM 解析用户意图 + 提取关键实体（只取字面内容，不猜测）
Stage 2: 实体检查 ── 无实体 → 追问"请问您具体想查询哪位员工或哪个项目？"
Stage 3: 精准查询 ── 有实体 → 带实体参数路由到数据源执行查询
```

## 意图路由

| 路由 | 条件 | 处理方式 |
|------|------|---------|
| DB_ONLY | 有数据关键词 + 有实体 | db_engine NL→SQL |
| KB_ONLY | 有知识库关键词 | kb_engine BM25 → LLM 格式化 |
| HYBRID | 员工名 + 制度关键词 | 双路解耦：参数化查询 + KB 剥离姓名检索 |
| AMBIGUOUS | 模糊问题 + "最近"等关键词 | 返回会议纪要 + 活跃项目 |

## 安全机制（三层护栏）

```
输入层: safety.py
  ├── SQL注入: SELECT/DROP/OR 1=1/-- 等 15+ 模式
  └── 终端命令: python/pip/git/cd 等 20+ 前缀

SQL层: db_engine._is_safe_sql()
  └── 仅允许 SELECT，拦截 DROP/DELETE/INSERT/UPDATE/ALTER/CREATE/EXEC

Prompt层: 所有 LLM prompt 嵌入护栏
  └── 不泄露 manager_id/employee_id 等内部 ID
  └── 用户问什么就答什么，不 dump 额外字段
```

## 混合查询（HYBRID）安全架构

- **DB 路径**：严格走 `WHERE name=?` 参数化查询，禁止 LLM 拼接 SQL
- **KB 路径**：检索前将员工姓名从 query 中剥离，避免会议纪要等污染结果
- **文档过滤**：晋升类问题仅保留 `promotion_rules.md`

## 模块职责

| 模块 | 职责 | 关键设计 |
|------|------|---------|
| config.py | 配置加载 | YAML + 环境变量覆盖 |
| safety.py | 安全检测 | 正则匹配 15+ SQL 模式 + 20+ 命令前缀 |
| nlu.py | 意图+实体提取 | LLM 前置消化，只取字面实体 |
| intent.py | 关键词分类 | 5 条路由规则，预设名单+百家姓正则 |
| db_engine.py | 数据库查询 | Schema-Aware SQL 生成，安全校验 |
| kb_engine.py | 知识库检索 | 纯 Python BM25，jieba 分词 |
| orchestrator.py | 编排器 | 三阶段流程，HYBRID 双路解耦 |

## 设计原则

- **单一职责**：7 个模块各司其职
- **安全第一**：输入层 + SQL 层 + Prompt 层三重防护
- **消除幻觉**：LLM 只取字面实体；实体为空不猜，直接追问
- **配置驱动**：所有路径通过 config.yaml 或环境变量配置
