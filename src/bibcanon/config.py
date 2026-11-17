"""Configuration loading and persistence (~/.bibcanon/config.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from bibcanon.models import AppConfig


def get_bibcanon_home() -> Path:
    """Return the bibcanon data directory, honoring BIBCANON_HOME if set."""
    env_override = os.environ.get("BIBCANON_HOME")
    if env_override:
        home = Path(env_override).expanduser().resolve()
    else:
        home = Path.home() / ".bibcanon"
    home.mkdir(parents=True, exist_ok=True)
    return home


def get_config_path() -> Path:
    """Return the path to config.json."""
    return get_bibcanon_home() / "config.json"


def get_cache_db_path() -> Path:
    """Return the path to cache.sqlite3."""
    return get_bibcanon_home() / "cache.sqlite3"


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load AppConfig from disk using UTF-8 encoding, falling back to defaults."""
    target = config_path or get_config_path()
    if not target.exists():
        return AppConfig()
    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
        return AppConfig.model_validate(data)
    except Exception:
        return AppConfig()


def save_config(config: AppConfig, config_path: Path | None = None) -> AppConfig:
    """Persist AppConfig to disk using UTF-8 encoding."""
    target = config_path or get_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.model_dump(), indent=2, ensure_ascii=False)
    target.write_text(payload + "\n", encoding="utf-8")
    return config
