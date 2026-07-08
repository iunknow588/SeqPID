from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def load_runtime_config(config_path: str | Path) -> dict[str, Any]:
    return load_yaml(config_path)


def load_label_dict(config_path: str | Path) -> dict[str, Any]:
    return load_yaml(config_path)
