"""Live control of the filter-chain node via pw-cli, lifecycle via systemd.

Control keys are `<node_name>:<control>` (e.g. `band3:Gain`), set with
`pw-cli s <node-id> Props '{"params": ["key", value]}'` — the same mechanism
used by other PipeWire EQ frontends.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import render
from .model import EqSettings

SERVICE = "donglehub-eq.service"
UNIT_TEXT = """\
[Unit]
Description=DongleHub EQ (PipeWire filter-chain)
After=pipewire.service

[Service]
Type=simple
ExecStart=/usr/bin/pipewire -c filter-chain.conf
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""


def _default_run(cmd, **kw) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw).stdout
    except OSError:
        return ""


class EqController:
    def __init__(self, run: Optional[Callable] = None, node: Optional[int] = None):
        self._run = run or _default_run
        self.node = node

    # ── node lookup / params ──────────────────────────────────────────

    def node_id(self, name: str = "donglehub.eq") -> Optional[int]:
        try:
            data = json.loads(self._run(["pw-dump"]) or "[]")
        except ValueError:
            return None
        for obj in data:
            props = (obj.get("info") or {}).get("props") or {}
            if props.get("node.name") == name and isinstance(obj.get("id"), int):
                return obj["id"]
        return None

    def _resolve(self, settings: EqSettings) -> Optional[int]:
        if self.node is not None:
            return self.node
        name = "donglehub.surround" if settings.mode == "surround" else "donglehub.eq"
        self.node = self.node_id(name)
        return self.node

    def _set(self, key: str, value: float) -> None:
        payload = json.dumps({"params": [key, float(value)]})
        self._run(["pw-cli", "s", str(self.node), "Props", payload])

    def read_props(self, settings: EqSettings) -> Dict[str, float]:
        node = self._resolve(settings)
        if node is None:
            return {}
        try:
            data = json.loads(self._run(["pw-dump", str(node)]) or "[]")
        except ValueError:
            return {}
        out = {}
        for obj in data:
            params = ((obj.get("info") or {}).get("params") or {}).get("Props") or []
            for entry in params:
                flat = entry.get("params") or []
                for i in range(0, len(flat) - 1, 2):
                    try:
                        out[flat[i]] = float(flat[i + 1])
                    except (TypeError, ValueError):
                        continue
        return out

    # ── live control ──────────────────────────────────────────────────

    def set_band(self, index: int, gain: float, settings: EqSettings) -> bool:
        if self._resolve(settings) is None:
            return False
        for key in render.control_keys(settings, index):
            self._set(key, gain)
        return True

    def set_preamp(self, gain: float, settings: EqSettings) -> bool:
        if self._resolve(settings) is None:
            return False
        for key in render.preamp_keys(settings):
            self._set(key, gain)
        return True

    def apply(self, settings: EqSettings, current: Optional[Dict[str, float]] = None) -> List[str]:
        """Push settings to the running chain; only changed controls."""
        if self._resolve(settings) is None:
            return []
        current = current or {}
        sent = []
        for i, gain in enumerate(settings.gains):
            for key in render.control_keys(settings, i):
                if current.get(key) != float(gain):
                    self._set(key, gain)
                    sent.append(key)
        for key in render.preamp_keys(settings):
            if current.get(key) != float(settings.preamp):
                self._set(key, settings.preamp)
                sent.append(key)
        return sent

    # ── lifecycle ─────────────────────────────────────────────────────

    def enable(self) -> None:
        self._run(["systemctl", "--user", "enable", "--now", SERVICE])

    def disable(self) -> None:
        self._run(["systemctl", "--user", "disable", "--now", SERVICE])

    def restart(self) -> None:
        self._run(["systemctl", "--user", "restart", SERVICE])

    # ── install ───────────────────────────────────────────────────────

    def install(self, settings: EqSettings) -> str:
        """Write the chain config + user service and enable it."""
        home = Path.home()
        conf_dir = home / ".config" / "pipewire" / "filter-chain.conf.d"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "donglehub-eq.conf").write_text(render.render_conf(settings))

        unit_dir = home / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / SERVICE).write_text(UNIT_TEXT)

        self._run(["systemctl", "--user", "daemon-reload"])
        self.enable()
        return (
            f"wrote {conf_dir / 'donglehub-eq.conf'} and "
            f"{unit_dir / SERVICE}; service enabled"
        )
