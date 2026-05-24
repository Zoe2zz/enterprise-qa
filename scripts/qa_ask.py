"""QA query tool — callable by OpenClaw agents.
Supports dialog history management, no persona.
"""
import sys, os, json

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enterprise_qa import create_qa_engine

HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_history.json")
MAX_HISTORY = 10

def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)

def format_history(history):
    lines = []
    for item in history:
        lines.append(f"User: {item['q']}")
        lines.append(f"Assistant: {item['a']}")
    return "\n".join(lines)

def ask(question, engine):
    history = load_history()
    history_text = format_history(history)
    answer = engine.answer(question, history_text)
    history.append({"q": question, "a": answer})
    save_history(history)
    return answer

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python qa_ask.py 'your question'")
        sys.exit(1)

    engine = create_qa_engine(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
    result = ask(" ".join(sys.argv[1:]), engine)
    print(result)
