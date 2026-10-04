"""System volume / microphone sync via wpctl (PipeWire / WirePlumber).

Same integration the MCHOSE Windows hub has: the headset is the default
audio device, so its volume/mic sliders follow the system mixer.
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable, Tuple

SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"

_VOL_RE = re.compile(r"Volume:\s*([0-9.]+)")


def _default_run(cmd) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_volume(text: str) -> Tuple[int, bool]:
    """Parse `wpctl get-volume` output -> (percent, muted)."""
    m = _VOL_RE.search(text or "")
    if not m:
        return 0, False
    return round(float(m.group(1)) * 100), "[MUTED]" in (text or "")


class AudioService:
    def __init__(self, run: Callable = None):
        self._run = run or _default_run

    def get(self) -> Tuple[int, bool, int]:
        """Return (volume_pct, muted, mic_pct)."""
        vol, muted = parse_volume(self._run(["wpctl", "get-volume", SINK]))
        mic, _ = parse_volume(self._run(["wpctl", "get-volume", SOURCE]))
        return vol, muted, mic

    def set_volume(self, pct: int) -> None:
        self._run(["wpctl", "set-volume", SINK, f"{int(pct)}%"])

    def set_mic_volume(self, pct: int) -> None:
        self._run(["wpctl", "set-volume", SOURCE, f"{int(pct)}%"])

    def toggle_mute(self) -> None:
        self._run(["wpctl", "set-mute", SINK, "toggle"])
