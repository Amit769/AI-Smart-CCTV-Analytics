import json
import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Loads configuration from JSON file. Falls back to default if not found."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config_data: Dict[str, Any], config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Saves updated configuration to JSON file."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


def get_project_root() -> Path:
    """Returns absolute path of the project root directory."""
    return Path(__file__).resolve().parent
