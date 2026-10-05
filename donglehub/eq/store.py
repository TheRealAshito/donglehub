"""EQ settings persistence: active state + named presets."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .model import EqSettings


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "donglehub"


def _path() -> Path:
    return _config_dir() / "eq.json"


def _load() -> dict:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    _config_dir().mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, indent=2) + "\n")


def load_active() -> EqSettings:
    return EqSettings.from_dict(_load().get("active", {}))


def save_active(settings: EqSettings) -> None:
    data = _load()
    data["active"] = settings.to_dict()
    _write(data)


def list_presets() -> List[str]:
    return sorted(_load().get("presets", {}))


def save_preset(name: str, settings: EqSettings) -> None:
    data = _load()
    data.setdefault("presets", {})[name] = settings.to_dict()
    _write(data)


def load_preset(name: str) -> EqSettings:
    presets = _load().get("presets", {})
    if name not in presets:
        raise KeyError(name)
    return EqSettings.from_dict(presets[name])


def delete_preset(name: str) -> None:
    data = _load()
    data.get("presets", {}).pop(name, None)
    _write(data)
