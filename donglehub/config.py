"""User configuration (~/.config/donglehub/config.json).

Only one knob for now: `headset_status_map`, which calibrates the
vendor-unknown status byte of the MCHOSE V9 PRO to a power state.
Use `donglehub probe headset` while charging/discharging to learn the values,
then map them here, e.g.:

    {"headset_status_map": {"1": "charging", "2": "full"}}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "headset_status_map": {},
}


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "donglehub" / "config.json"


def load_config() -> dict:
    try:
        raw = json.loads(config_path().read_text())
    except (OSError, ValueError):
        raw = {}
    cfg = dict(DEFAULTS)
    status_map = {}
    for k, v in dict(raw.get("headset_status_map", {})).items():
        try:
            status_map[int(k, 0)] = v
        except (TypeError, ValueError):
            continue
    cfg["headset_status_map"] = status_map
    return cfg
