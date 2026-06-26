"""Configuration loader — reads YAML config and validates it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Config


def load_config(path: str | Path) -> Config:
    """Load and validate webhook router configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping")

    return Config.model_validate(data)


def load_config_dict(data: dict[str, Any]) -> Config:
    """Validate configuration from a Python dict."""
    return Config.model_validate(data)
