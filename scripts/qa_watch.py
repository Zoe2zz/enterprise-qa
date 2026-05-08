"""常驻 QA 引擎 — 监控 qa_in.txt，输出到 qa_out.txt"""
import sys, os, json, time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enterprise_qa import create_qa_engine

BASE = os.path.dirname(os.path.abspath(__file__))
IN_FILE = os.path.join(BASE, "qa_in.txt")
OUT_FILE = os.path.join(BASE, "qa_out.txt")
HISTORY_PATH = os.path.join(BASE, "qa_history.json")
MAX_HISTORY = 10

engine = create_qa_engine(os.path.join(BASE, "config.yaml"))

def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)

def fmt_history(history):
    return "\n".join(f"用户：{h['q']}\n助手：{h['a']}" for h in history)

print("READY", flush=True)

# 清空旧文件
for f in [IN_FILE, OUT_FILE]:
    if os.path.exists(f):
        os.remove(f)

while True:
    if os.path.exists(IN_FILE):
        with open(IN_FILE, "r", encoding="utf-8") as f:
            question = f.read().strip()
        os.remove(IN_FILE)
        
        if question == "__EXIT__":
            break
        if question == "__CLEAR__":
            if os.path.exists(HISTORY_PATH):
                os.remove(HISTORY_PATH)
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                f.write("__CLEARED__")
            continue
        
        history = load_history()
        answer = engine.answer(question, fmt_history(history))
        history.append({"q": question, "a": answer})
        save_history(history)
        
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(answer)
    time.sleep(0.3)
