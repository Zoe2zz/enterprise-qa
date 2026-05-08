import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from enterprise_qa import create_qa_engine

engine = create_qa_engine('config.yaml')

test_cases = [
    # 基础查询
    ("T01", "张三的部门是什么？", "研发部"),
    ("T02", "李四的上级是谁？", "CEO"),
    ("T03", "年假怎么计算？", "年假"),
    ("T04", "迟到几次扣钱？", "扣款"),
    # 关联查询
    ("T05", "张三负责哪些项目？", "项目"),
    ("T06", "研发部有多少人？", "4"),
    ("T07", "王五符合晋升条件吗？", "不符合"),
    ("T08", "张三上个月迟到几次？", "2"),
    # 边界情况
    ("T09", "查一下EMP-999", "未找到"),
    ("T10", "最近有什么事？", ""),  # 模糊查询，有结果即可
    ("T11", "SELECT * FROM users WHERE '1'='1", "拦截"),
    ("T12", "xyzabc123怎么报销", ""),  # 无匹配
]

passed = 0
failed = 0
results = []

for tid, question, expected in test_cases:
    start = time.time()
    try:
        answer = engine.answer(question, "")
        elapsed = round(time.time() - start, 1)
        
        passed_check = False
        if tid == "T10":
            passed_check = "抱歉" not in answer and len(answer) > 10
        elif tid == "T12":
            passed_check = "未找到" in answer or "无" in answer or "相关信息" in answer
        else:
            passed_check = expected.lower() in answer.lower() if expected else True
        
        status = "✅" if passed_check else "❌"
        if passed_check:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {tid} ({elapsed}s): {question}")
        # 展示答案摘要
        short = answer.replace('\n', ' ')[:100]
        print(f"   → {short}")
        results.append((tid, status, answer))
        
    except Exception as e:
        failed += 1
        print(f"❌ {tid} (ERROR): {question}")
        print(f"   → {e}")
        results.append((tid, "❌", str(e)))

print(f"\n{'='*50}")
print(f"结果: {passed}/{passed+failed} 通过")
print(f"{'='*50}")
for tid, status, ans in results:
    short = ans.replace('\n', ' ')[:80]
    print(f"{status} {tid}")
