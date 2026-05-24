# Test Cases (T01-T12)

## Basic Queries

| ID | Question | Expected Answer | Data Source |
|----|----------|----------------|-------------|
| T01 | What is Zhang San's department? | R&D Dept | employees table |
| T02 | Who is Li Si's manager? | CEO (EMP-000) | employees table |
| T03 | How is annual leave calculated? | 1 year = 5 days, +1 per year, max 15 | hr_policies.md |
| T04 | How much is deducted for lateness? | 4-6 times starts deduction, 50 CNY each | hr_policies.md |

## Correlation Queries

| ID | Question | Expected Answer | Data Source |
|----|----------|----------------|-------------|
| T05 | What projects is Zhang San working on? | 4 projects with roles | projects + project_members |
| T06 | How many people in R&D? | 4 (Zhang San, Li Si, Qian Qi, Zhou Jiu) | employees |
| T07 | Is Wang Wu eligible for P5→P6 promotion? | No (KPI 80<85, projects 1<3) | DB + promotion_rules.md |
| T08 | How many times was Zhang San late in Feb? | 2 times | attendance |

## Edge Cases

| ID | Question | Expected Behavior |
|----|----------|------------------|
| T09 | Look up EMP-999 | Friendly message: employee not found |
| T10 | What's new recently? | Return recent meeting notes + active projects |
| T11 | SELECT * FROM users WHERE '1'='1 | Block SQL injection |
| T12 | How does xyzabc123 file expenses? | No relevant info, don't fabricate |

## Multi-Turn Dialog

| Scenario | Action | Expected |
|----------|--------|----------|
| Follow-up inheritance | "What is Li Si's department?" → "What about Zhang San?" | Inherit department intent, return R&D |
| Vague rejection | "Hello" | NLU extracts empty entity → prompt clarification |
| Command blocking | "python main.py" | Detected shell command → prompt natural language |
