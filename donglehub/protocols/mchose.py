"""MCHOSE V9 PRO protocol (2.4G dongle, VID 0x291D / PID 0x385D).

Pure encode/parse helpers over 64-byte HID reports. Byte layout was
reverse-engineered from JoaoKSS/MCHOSE_v9_PRO_Controller and is confirmed
against real hardware by `donglehub probe headset`.
"""
from __future__ import annotations

from typing import Optional, Tuple

VID = 0x291D
PID = 0x385D

REPORT_LEN = 64

EQ_MODES = {0: "Game 1", 1: "Game 2", 2: "Music"}


def _pad(header: list) -> bytes:
    return bytes(header + [0] * (REPORT_LEN - len(header)))


def cmd_status() -> bytes:
    """Request battery % (byte 2 of reply) and status byte (byte 3)."""
    return _pad([0x55, 0x65, 0x01])


def parse_status_reply(data: bytes) -> Optional[Tuple[int, int]]:
    """Return (battery_pct, status_raw) or None on mismatched/short reply."""
    if len(data) < 4 or data[0] != 0x55 or data[1] != 0x65:
        return None
    return data[2], data[3]


def cmd_eq_query() -> bytes:
    return _pad([0x55, 0x11])


def parse_eq_reply(data: bytes) -> Optional[int]:
    """Return current EQ mode byte or None."""
    if len(data) < 3 or data[0] != 0x55 or data[1] != 0x11:
        return None
    return data[2]


def cmd_eq_set(mode: int) -> bytes:
    if mode not in EQ_MODES:
        raise ValueError(f"EQ mode must be one of {sorted(EQ_MODES)}, got {mode}")
    return _pad([0x55, 0x21, 0x01, mode])


def cmd_firmware() -> bytes:
    """Feature report requesting dongle + headset firmware versions."""
    return _pad([0xAA, 0x01, 0x00])


def parse_firmware_reply(data: bytes) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """Return (fw_dongle, fw_headset) decimal pairs; parts are None if absent."""
    if len(data) < 1 or data[0] != 0xAA:
        return None
    fw_dongle = f"{data[8]:02d}{data[9]:02d}" if len(data) >= 10 else None
    fw_headset = f"{data[10]:02d}{data[11]:02d}" if len(data) >= 12 else None
    return fw_dongle, fw_headset
