"""Hub: polls both devices behind a cross-process lock and emits snapshots."""
from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from . import config as config_mod
from .devices.headset import MchoseV9Pro
from .devices.mouse import AttackSharkX11
from .models import PowerTracker, hub_snapshot


def _lock_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(runtime) / "donglehub.lock"


@contextlib.contextmanager
def device_lock(path: Optional[Path] = None):
    """Serialise device access across GUI / CLI / shell-widget processes."""
    p = path or _lock_path()
    with open(p, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class Hub:
    def __init__(self, headset=None, mouse=None, use_lock: bool = True):
        cfg = config_mod.load_config()
        self.headset = headset or MchoseV9Pro(
            tracker=PowerTracker(cfg["headset_status_map"])
        )
        self.mouse = mouse or AttackSharkX11()
        self._use_lock = use_lock

    def poll_devices(self):
        lock = device_lock() if self._use_lock else contextlib.nullcontext()
        with lock:
            hs = self.headset.poll()
            ms = self.mouse.poll()
        return hs, ms

    def poll(self) -> dict:
        return hub_snapshot(*self.poll_devices())


def watch_loop(
    hub: Hub,
    interval: float,
    emit: Callable[[dict], Optional[bool]],
    max_polls: Optional[int] = None,
) -> int:
    """Poll forever (or max_polls times); emit(snapshot) per poll.

    emit may return False to stop. Used by `donglehub watch` and the GUI.
    """
    count = 0
    while max_polls is None or count < max_polls:
        snap = hub.poll()
        if emit(snap) is False:
            return 0
        count += 1
        if interval:
            time.sleep(interval)
    return 0
