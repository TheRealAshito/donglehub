"""Thin ctypes binding to libhidapi (hidraw backend) for the MCHOSE dongle.

Kept dependency-free: no python `hid` package required, only the system
libhidapi-hidraw shared library.
"""
from __future__ import annotations

import ctypes
import os
from typing import Optional

from ..errors import DeviceUnavailable

_LIB_CANDIDATES = (
    "libhidapi-hidraw.so.0",
    "libhidapi-hidraw.so",
    "libhidapi.so.0",
    "libhidapi.so",
    "libhidapi.dylib",
    "hidapi.dll",
)

REPORT_LEN = 64


def _load_lib() -> ctypes.CDLL:
    errors = []
    for name in _LIB_CANDIDATES:
        try:
            return ctypes.CDLL(name)
        except OSError as e:  # pragma: no cover - depends on host libs
            errors.append(f"{name}: {e}")
    raise DeviceUnavailable(
        "libhidapi not found (install libhidapi-hidraw0 / hidapi). Tried: "
        + "; ".join(errors)
    )


class HidSession:
    def __init__(self, lib: ctypes.CDLL, handle):
        self._lib = lib
        self._handle = handle

    def write(self, data: bytes) -> int:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        return self._lib.hid_write(self._handle, buf, len(data))

    def read_timeout(self, length: int = REPORT_LEN, timeout_ms: int = 500) -> bytes:
        buf = ctypes.create_string_buffer(length)
        n = self._lib.hid_read_timeout(self._handle, buf, length, timeout_ms)
        return buf.raw[: max(n, 0)] if n > 0 else b""

    def send_feature(self, data: bytes) -> int:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        return self._lib.hid_send_feature_report(self._handle, buf, len(data))

    def get_feature(self, report_id: int, length: int = REPORT_LEN) -> bytes:
        buf = ctypes.create_string_buffer(length)
        buf.raw = bytes([report_id]) + bytes(length - 1)
        n = self._lib.hid_get_feature_report(self._handle, buf, length)
        return buf.raw[: max(n, 0)] if n > 0 else b""

    def close(self) -> None:
        if self._handle:
            self._lib.hid_close(self._handle)
            self._handle = None


def open_session(vid: int, pid: int) -> HidSession:
    lib = _load_lib()
    lib.hid_init()
    lib.hid_open.argtypes = [ctypes.c_ushort, ctypes.c_ushort, ctypes.c_void_p]
    lib.hid_open.restype = ctypes.c_void_p
    lib.hid_write.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    lib.hid_write.restype = ctypes.c_int
    lib.hid_read_timeout.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int,
    ]
    lib.hid_read_timeout.restype = ctypes.c_int
    lib.hid_send_feature_report.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.hid_send_feature_report.restype = ctypes.c_int
    lib.hid_get_feature_report.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.hid_get_feature_report.restype = ctypes.c_int
    lib.hid_close.argtypes = [ctypes.c_void_p]
    lib.hid_close.restype = None

    handle = lib.hid_open(vid, pid, None)
    if not handle:
        raise DeviceUnavailable(f"no hidraw device for {vid:#06x}:{pid:#06x}")
    return HidSession(lib, handle)


def find_serial() -> Optional[str]:  # pragma: no cover - convenience
    return None
