# 企业智能问答助手

企业内部问答系统，支持通过自然语言查询员工信息、项目记录、考勤数据、绩效考核，以及公司制度文档、会议纪要等知识内容。

---

## 功能概述

系统安装后，用户可在对话框中以 `@qa` 开头输入问题，AI 助手将自动判断需要查询的数据源（数据库或知识库），生成准确回答并标注来源。

### 支持的问题类型

| 类别 | 示例 |
|------|------|
| 员工信息 | `@qa 王五是谁？` |
| 组织关系 | `@qa 张三的上级是谁？` |
| 绩效考核 | `@qa 王五去年绩效怎么样？` |
| 考勤数据 | `@qa 李四这个月迟到几次？` |
| 公司制度 | `@qa 年假怎么算？` |
| | `@qa 病假需要什么材料？` |
| 报销规则 | `@qa 差旅报销标准是多少？` |
| 混合查询 | `@qa 王五符合晋升条件吗？` |
| 会议纪要 | `@qa 上次技术同步会说了什么？` |

---

## 使用方法

### 提问

在对话框中输入 `@qa` + 问题，AI 将返回答案并标注来源：

```
你：@qa 王五的部门是什么？
AI：王五的部门是产品部。

> 来源：employees 表


你：@qa 今年年假有几天？
AI：根据《人事制度》，年假计算规则为：
- 入职满 1 年享 5 天
- 每增 1 年 +1 天
- 上限 15 天

> 来源：hr_policies.md §请假类型
```

注意：`@qa` 必须放在消息开头。支持连续追问，系统会自动维护上下文。

### 重置对话

```
你：@qa 清空对话
```

---

## HR 使用指南

### 日常使用

在 AI 对话框中输入 `@qa` 后跟问题，系统会自动查询并回复。无需学习特殊命令。

### 更新公司制度文档

所有政策文件位于 `scripts/knowledge/` 目录，使用任意文本编辑器修改即可：

| 文件 | 内容 |
|------|------|
| `hr_policies.md` | 考勤、请假、加班制度 |
| `promotion_rules.md` | 晋升标准 |
| `finance_rules.md` | 报销、财务制度 |
| `faq.md` | 常见问题解答 |
| `meeting_notes/` | 会议纪要 |

修改步骤：
1. 在 `scripts/knowledge/` 下找到对应 `.md` 文件
2. 用记事本或 VS Code 打开编辑
3. 保存即可生效，无需重启

### 更新员工数据

员工信息、考勤和绩效等数据存储在数据库中，需要由 IT 部门操作：

- **员工入职/离职/调岗** → 通知 IT 更新数据库
- **月考勤数据** → 考勤系统导出后导入
- **季度绩效** → 绩效系统录入或批量导入

---

## 安装部署（面向技术人员）

### 1. 获取代码

```bash
git clone https://github.com/Zoe2zz/enterprise-qa.git
```

### 2. 安装到 OpenClaw

> **关于 Skill 存放路径的说明**
>
> 本题要求将 OpenClaw Skill 放在 `extensions/` 目录。实际环境下，OpenClaw 会从多个位置加载 skill。以下提供两种方式，择一即可：
>
> **方式一（考题要求）**：将 `enterprise-qa` 文件夹放入 `extensions/` 目录：
> ```
> extensions/enterprise-qa.skill/
> ```
>
> **方式二（标准 OpenClaw 环境）**：将文件夹放入全局 skills 目录：
>
> | 操作系统 | 目标路径 |
> |---------|---------|
> | Windows | `%USERPROFILE%\.openclaw\skills\enterprise-qa.skill\` |
> | macOS | `~/.openclaw/skills/enterprise-qa.skill/` |
> | Linux | `~/.openclaw/skills/enterprise-qa.skill/` |

### 3. 安装 Python 依赖

```bash
cd enterprise-qa/scripts
pip install -r requirements.txt
```

需要 Python 3.10 及以上版本（[python.org](https://python.org)）。

### 4. 验证

启动 OpenClaw 后，输入 `@qa 王五是谁？`，应返回正常结果。

---

## 配置说明

编辑 `scripts/config.yaml` 可修改数据源路径：

```yaml
database:
  path: ./enterprise.db

knowledge_base:
  root_path: ./knowledge
```

默认路径相对于 `scripts/` 目录。如需移动到其他位置，请使用绝对路径。

---

## 知识库结构

```
scripts/knowledge/
├── hr_policies.md                    # 人事制度（考勤、请假、加班）
├── promotion_rules.md                # 晋升标准
├── finance_rules.md                  # 财务报销制度
├── faq.md                            # 常见问题
├── tech_docs.md                      # 技术规范文档
└── meeting_notes/
    ├── 2026-03-01-allhands.md        # 全员大会纪要
    └── 2026-03-15-tech-sync.md       # 技术同步会纪要
```

新增文档直接在 `knowledge/` 下创建 `.md` 文件即可，系统会自动纳入检索。

---

## 系统架构

```
用户提问 (@qa ...)
    │
    ▼
┌─────────────────┐
│ 安全检测         │  SQL 注入防护、终端命令拦截
└────────┬────────┘
         │
┌────────▼────────┐
│ 意图理解         │  LLM 提取查询实体和意图
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│ 数据库  │ │ 知识库  │
│ NL→SQL │ │ BM25   │
└───┬────┘ └───┬────┘
    └────┬─────┘
         ▼
┌─────────────────┐
│ 结果融合 → 回答  │
│（含来源标注）    │
└─────────────────┘
```

- **数据库查询**：自然语言转 SQL，查询员工、考勤、绩效等精确数据
- **知识库检索**：BM25 算法从 Markdown 文档中匹配相关内容
- **混合查询**：同时查询数据库和知识库，合并结果，例如"王五符合晋升条件吗"

---

## 测试

```bash
cd scripts
python -m pytest tests/ -v
```

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 面向 AI 助手的操作说明书 |
| `README.md` | 本文档（面向人类用户） |
| `scripts/qa_ask.py` | 问答调用脚本 |
| `scripts/config.yaml` | 数据源配置文件 |
| `scripts/enterprise.db` | SQLite 数据库文件 |
| `scripts/knowledge/` | 知识文档目录 |
| `scripts/qa_history.json` | 对话历史记录（最近 10 轮） |
| `scripts/enterprise_qa/` | 问答引擎 Python 代码 |
| `scripts/requirements.txt` | Python 依赖清单 |
| `references/architecture.md` | 架构设计文档 |
| `references/test-cases.md` | 测试用例说明 |
