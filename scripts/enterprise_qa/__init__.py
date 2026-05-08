from .config import load_config
from .orchestrator import QAEngine


def create_qa_engine(config_path: str | None = None) -> QAEngine:
    config = load_config(config_path)
    return QAEngine(config)


__all__ = ["create_qa_engine", "load_config"]
