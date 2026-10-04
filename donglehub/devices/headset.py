"""MCHOSE V9 PRO headset device driver (2.4G dongle)."""
from __future__ import annotations

import time
from typing import Callable, Optional

from ..backends import hidapi
from ..errors import DeviceUnavailable
from ..models import DeviceStatus, PowerState, PowerTracker
from ..protocols import mchose

REPORT_LEN = 64
IO_TIMEOUT_MS = 500


class MchoseV9Pro:
    NAME = "MCHOSE V9 PRO"

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
        tracker: Optional[PowerTracker] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._factory = session_factory or (
            lambda: hidapi.open_session(mchose.VID, mchose.PID)
        )
        self.tracker = tracker or PowerTracker()
        self._sleep = sleep
        self._fw: tuple = ("", "")

    def poll(self) -> DeviceStatus:
        try:
            sess = self._factory()
        except DeviceUnavailable:
            return DeviceStatus(
                device_id="headset", name=self.NAME, connected=False,
                connection=None, power=PowerState.UNKNOWN,
            )
        battery = status_raw = eq = None
        try:
            sess.write(mchose.cmd_status())
            parsed = mchose.parse_status_reply(
                sess.read_timeout(REPORT_LEN, IO_TIMEOUT_MS) or b""
            )
            if parsed is not None:
                battery, status_raw = parsed
            sess.write(mchose.cmd_eq_query())
            eq = mchose.parse_eq_reply(
                sess.read_timeout(REPORT_LEN, IO_TIMEOUT_MS) or b""
            )
        finally:
            sess.close()

        power = self.tracker.update(battery, status_raw)
        return DeviceStatus(
            device_id="headset",
            name=self.NAME,
            connected=True,
            connection="2.4ghz",
            battery_pct=battery,
            power=power,
            status_raw=status_raw,
            details={
                "eq_mode": eq,
                "eq_name": mchose.EQ_MODES.get(eq) if eq is not None else None,
                "firmware": self._fw if self._fw != ("", "") else None,
            },
        )

    def set_eq(self, mode: int) -> int:
        sess = self._factory()
        try:
            sess.write(mchose.cmd_eq_set(mode))
            self._sleep(0.05)
            sess.write(mchose.cmd_eq_query())
            new_mode = mchose.parse_eq_reply(
                sess.read_timeout(REPORT_LEN, IO_TIMEOUT_MS) or b""
            )
            return new_mode if new_mode is not None else mode
        finally:
            sess.close()

    def firmware(self) -> tuple:
        try:
            sess = self._factory()
        except DeviceUnavailable:
            return "", ""
        try:
            sess.send_feature(mchose.cmd_firmware())
            for delay in (0.3, 0.5, 0.9):
                self._sleep(delay)
                data = sess.get_feature(0xAA, REPORT_LEN) or b""
                parsed = mchose.parse_firmware_reply(data)
                if parsed is not None:
                    self._fw = parsed
                    return parsed
            return "", ""
        finally:
            sess.close()
