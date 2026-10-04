"""Shared status models: device state, power interpretation, hub snapshots."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PowerState(str, Enum):
    CHARGING = "charging"
    FULL = "full"
    ON_BATTERY = "on_battery"
    UNKNOWN = "unknown"


_POWER_ALIASES = {
    "charging": PowerState.CHARGING,
    "full": PowerState.FULL,
    "charged": PowerState.FULL,
    "on_battery": PowerState.ON_BATTERY,
    "discharging": PowerState.ON_BATTERY,
    "unknown": PowerState.UNKNOWN,
}


@dataclass
class DeviceStatus:
    device_id: str
    name: str
    connected: bool
    connection: Optional[str]  # "2.4ghz" | "bluetooth" | "wired" | None
    battery_pct: Optional[int] = None
    power: PowerState = PowerState.UNKNOWN
    status_raw: Optional[int] = None
    details: dict = field(default_factory=dict)

    @property
    def charging(self) -> bool:
        return self.power == PowerState.CHARGING

    @property
    def charged(self) -> bool:
        return self.power == PowerState.FULL

    def to_dict(self) -> dict:
        return {
            "device": self.device_id,
            "name": self.name,
            "connected": self.connected,
            "connection": self.connection,
            "battery": self.battery_pct,
            "power": self.power.value,
            "charging": self.charging,
            "charged": self.charged,
            "status_raw": self.status_raw,
            "details": dict(self.details),
        }

    def summary(self) -> str:
        if not self.connected:
            return "disconnected"
        if self.battery_pct is None:
            return self.power.value.replace("_", " ")
        if self.charging:
            return f"{self.battery_pct}% (charging)"
        if self.charged:
            return f"{self.battery_pct}% (charged)"
        return f"{self.battery_pct}%"


class PowerTracker:
    """Derives a PowerState from raw readings.

    Signal order (first match wins):
      1. explicit status_map on the raw device status byte (user-calibratable,
         protocol semantics are vendor-unknown)
      2. battery at 100% -> FULL ("charged")
      3. caller hint (e.g. mouse is wired/docked = definitely charging)
      4. trend vs previous reading (rising = charging, falling = on battery)
      5. previous state, else UNKNOWN
    """

    def __init__(self, status_map: Optional[dict] = None):
        self.status_map = dict(status_map or {})
        self.prev_pct: Optional[int] = None
        self.state = PowerState.UNKNOWN

    def update(
        self,
        battery_pct: Optional[int],
        status_raw: Optional[int] = None,
        hint: Optional[PowerState] = None,
    ) -> PowerState:
        state: Optional[PowerState] = None

        if status_raw is not None and status_raw in self.status_map:
            state = _POWER_ALIASES.get(str(self.status_map[status_raw]).lower())
        if state is None and battery_pct == 100:
            state = PowerState.FULL
        if state is None and hint is not None:
            state = hint
        if state is None and battery_pct is not None and self.prev_pct is not None:
            if battery_pct > self.prev_pct:
                state = PowerState.CHARGING
            elif battery_pct < self.prev_pct:
                state = PowerState.ON_BATTERY
        if state is None:
            state = self.state

        if battery_pct is not None:
            self.prev_pct = battery_pct
        self.state = state
        return state


def hub_snapshot(headset: DeviceStatus, mouse: DeviceStatus) -> dict:
    return {
        "schema": 1,
        "updated": time.time(),
        "devices": {
            "headset": headset.to_dict(),
            "mouse": mouse.to_dict(),
        },
    }
