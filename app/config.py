"""Small local config persistence (last-used output folder).

Stored as a gitignored JSON file next to the project root so the app can
remember where the user last saved certificates, without any external
dependency or database.
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"


def load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        # Persisting the last-used folder is a convenience, not critical --
        # never fail certificate generation because of it.
        pass


def get_last_output_folder() -> str:
    return load_config().get("last_output_folder", "")


def set_last_output_folder(path: str) -> None:
    config = load_config()
    config["last_output_folder"] = path
    save_config(config)
