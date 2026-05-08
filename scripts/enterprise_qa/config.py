import os
import yaml

DEFAULT_CONFIG_PATH = "config.yaml"


def load_config(config_path=None):
    if config_path is None:
        config_path = os.getenv("ENTERPRISE_QA_CONFIG", DEFAULT_CONFIG_PATH)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db_path = os.getenv("ENTERPRISE_QA_DB_PATH")
    if db_path:
        config.setdefault("database", {})["path"] = db_path

    kb_path = os.getenv("ENTERPRISE_QA_KB_PATH")
    if kb_path:
        config.setdefault("knowledge_base", {})["root_path"] = kb_path

    return config
