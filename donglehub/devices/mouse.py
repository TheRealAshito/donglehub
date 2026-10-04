"""AttackShark X11 mouse device driver."""
from __future__ import annotations

import time
from typing import Callable, Optional

from ..backends.usb import X11UsbBackend
from ..errors import DeviceUnavailable
from ..models import DeviceStatus, PowerState, PowerTracker
from ..protocols import x11

BATTERY_READ_ATTEMPTS = 5
BATTERY_TIMEOUT_MS = 500
REPORT_DELAY_S = 0.3


class AttackSharkX11:
    NAME = "AttackShark X11"

    def __init__(
        self,
        backend: Optional[X11UsbBackend] = None,
        tracker: Optional[PowerTracker] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._backend = backend or X11UsbBackend()
        self.tracker = tracker or PowerTracker()
        self._sleep = sleep

    def poll(self) -> DeviceStatus:
        try:
            wireless, wired = self._backend.presence()
        except DeviceUnavailable as e:
            return DeviceStatus(
                device_id="mouse", name=self.NAME, connected=False,
                connection=None, power=PowerState.UNKNOWN,
                details={"error": str(e)},
            )
        if not wireless and not wired:
            return DeviceStatus(
                device_id="mouse", name=self.NAME, connected=False,
                connection=None, power=PowerState.UNKNOWN,
            )

        connection = "2.4ghz" if wireless else "wired"
        battery = None
        hint = None

        if wireless:
            for _ in range(BATTERY_READ_ATTEMPTS):
                try:
                    pkt = self._backend.read_battery_packet(
                        retries=1, timeout_ms=BATTERY_TIMEOUT_MS
                    )
                except DeviceUnavailable:
                    pkt = None
                pct = x11.parse_battery_packet(pkt) if pkt else None
                if pct is not None:
                    battery = pct
                    break
            if battery is None:
                # Interface up but no wireless battery data: the mouse is on
                # the charging dock (same semantics as upstream's getBatteryInfo).
                hint = PowerState.CHARGING
        else:
            # Enumerating over USB cable means it is charging.
            hint = PowerState.CHARGING

        power = self.tracker.update(battery, None, hint=hint)
        return DeviceStatus(
            device_id="mouse",
            name=self.NAME,
            connected=True,
            connection=connection,
            battery_pct=battery,
            power=power,
            details={"wireless": wireless, "wired": wired},
        )

    def apply_settings(self, settings: x11.MouseSettings) -> None:
        reports = x11.settings_reports(settings)  # validates ranges
        for i, (report_id, data) in enumerate(reports):
            if not self._backend.send_report(report_id, data):
                raise IOError(f"report {report_id:#06x} was not accepted by the mouse")
            if i < len(reports) - 1:
                self._sleep(REPORT_DELAY_S)
