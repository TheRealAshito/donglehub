"""AttackShark X11 (Xenta) mouse protocol.

Pure packet parsers and report builders. Reverse-engineered from
iago-fragnan/attack-shark-x11-linux (hook.cpp) with further RE credits to
HarukaYamamoto0/attack-shark-x11-driver.

USB topology:
  0x1d57:0xfa60  wireless dongle
  0x1d57:0xfa55  mouse over cable (i.e. charging)
  Battery packets arrive as 64-byte interrupt IN transfers on interface 2,
  endpoint 0x83. Settings are SET_REPORT control transfers on interface 2.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple

VID = 0x1D57
PID_WIRELESS = 0xFA60
PID_WIRED = 0xFA55

CONFIG_IFACE = 2
BATTERY_IFACE = 2
BATTERY_ENDPOINT = 0x83
BATTERY_PACKET_SIG = (0x03, 0x55, 0x40, 0x01)

REPORT_POLLING = 0x0306
REPORT_COLOR = 0x0305
REPORT_PROFILE = 0x0304

POLLING_RATE_LABELS = ("125 Hz", "250 Hz", "500 Hz", "1000 Hz")
POLLING_RATES = ((0x08, 0xF7), (0x04, 0xFB), (0x02, 0xFD), (0x01, 0xFE))
COLOR_MODE_LABELS = ("Disabled", "Breathing", "Neon", "Color Breathing")

_COLOR_MODES = (
    (0x05, 0x0F, 0x01, 0x10, 0x01, 0xA8, 0x00, 0x00, 0x00, 0x01, 0x06, 0x00, 0xC0, 0x00, 0x00),
    (0x05, 0x0F, 0x01, 0x20, 0x01, 0xA8, 0x00, 0x00, 0xFF, 0x01, 0x06, 0x01, 0xCF, 0x00, 0x00),
    (0x05, 0x0F, 0x01, 0x30, 0x01, 0xA8, 0x00, 0x00, 0xFF, 0x01, 0x06, 0x01, 0xDF, 0x00, 0x00),
    (0x05, 0x0F, 0x01, 0x40, 0x01, 0xA8, 0x00, 0x00, 0xFF, 0x01, 0x06, 0x01, 0xEF, 0x00, 0x00),
)
COLOR_MODES = tuple(bytes(m) for m in _COLOR_MODES)


@dataclass
class MouseSettings:
    color_mode: int = 0
    polling_rate: int = 0
    angle_snap: bool = False
    key_resp_ms: int = 8
    sleep_min: int = 5
    deep_sleep_min: int = 10
    ripple_control: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MouseSettings":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def parse_battery_packet(data: bytes) -> Optional[int]:
    """Battery percentage from a 64-byte interrupt packet, or None."""
    if len(data) < 5 or tuple(data[:4]) != BATTERY_PACKET_SIG:
        return None
    return data[4]


def build_polling_report(rate_index: int) -> bytes:
    if not 0 <= rate_index < len(POLLING_RATES):
        raise ValueError(f"polling rate index must be 0..{len(POLLING_RATES) - 1}")
    a, b = POLLING_RATES[rate_index]
    return bytes((0x06, 0x09, 0x01, a, b, 0x00, 0x00, 0x00, 0x00))


def build_color_report(color_mode: int) -> bytes:
    if not 0 <= color_mode < len(COLOR_MODES):
        raise ValueError(f"color mode must be 0..{len(COLOR_MODES) - 1}")
    return COLOR_MODES[color_mode]


def build_profile_report(angle_snap: bool, ripple_control: bool) -> bytes:
    return bytes(
        (0x04, 0x38, 0x01,
         0x01 if angle_snap else 0x00,
         0x01 if ripple_control else 0x00,
         0x3F, 0x00, 0x00,
         0x01,
         0x25, 0x38, 0x4B, 0x75, 0x8D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
         0x01, 0x00, 0x00,
         0x02,
         0xFF, 0x00, 0x00, 0x00,
         0xFF, 0x00, 0x00, 0x00,
         0xFF, 0xFF, 0xFF, 0x00, 0x00,
         0xFF, 0xFF, 0xFF, 0x00,
         0xFF, 0xFF, 0x40, 0x00,
         0xFF, 0xFF, 0xFF,
         0x02, 0x0F,
         0x34,
         0x00, 0x00, 0x00, 0x00)
    )


def validate_settings(
    color_mode: int,
    polling_rate: int,
    angle_snap: bool,
    key_resp_ms: int,
    sleep_min: int,
    deep_sleep_min: int,
    ripple_control: bool,
) -> None:
    """Raise ValueError outside device-accepted ranges.

    Ranges mirror attack-shark-x11-linux's applySettingsFromUser.
    """
    if not 0 <= color_mode < len(COLOR_MODES):
        raise ValueError("color_mode must be 0..3")
    if not 0 <= polling_rate < len(POLLING_RATES):
        raise ValueError("polling_rate must be 0..3")
    if not 1 <= sleep_min <= 30:
        raise ValueError("sleep_min must be 1..30")
    if not 1 <= deep_sleep_min <= 60:
        raise ValueError("deep_sleep_min must be 1..60")
    if not 4 <= key_resp_ms <= 50 or key_resp_ms % 2 != 0:
        raise ValueError("key_resp_ms must be 4..50 and even")


def settings_reports(settings: MouseSettings) -> List[Tuple[int, bytes]]:
    validate_settings(
        color_mode=settings.color_mode,
        polling_rate=settings.polling_rate,
        angle_snap=settings.angle_snap,
        key_resp_ms=settings.key_resp_ms,
        sleep_min=settings.sleep_min,
        deep_sleep_min=settings.deep_sleep_min,
        ripple_control=settings.ripple_control,
    )
    return [
        (REPORT_POLLING, build_polling_report(settings.polling_rate)),
        (REPORT_COLOR, build_color_report(settings.color_mode)),
        (REPORT_PROFILE, build_profile_report(settings.angle_snap, settings.ripple_control)),
    ]
