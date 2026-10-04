"""Protocol tests for the AttackShark X11 (Xenta) mouse.

Wireless dongle VID:PID 0x1d57:0xfa60, wired/charging 0x1d57:0xfa55.
Packets reverse-engineered from iago-fragnan/attack-shark-x11-linux (hook.cpp).
"""
import pytest

from donglehub.protocols import x11


def test_parse_battery_packet_extracts_percentage():
    pkt = bytes([0x03, 0x55, 0x40, 0x01, 77]) + bytes(59)
    assert x11.parse_battery_packet(pkt) == 77


def test_parse_battery_packet_rejects_wrong_signature():
    pkt = bytes([0x03, 0x55, 0x40, 0x02, 77]) + bytes(59)
    assert x11.parse_battery_packet(pkt) is None


def test_parse_battery_packet_rejects_short_packet():
    assert x11.parse_battery_packet(b"\x03\x55\x40\x01") is None


def test_build_polling_report_matches_reference_bytes():
    assert x11.build_polling_report(0) == bytes([0x06, 0x09, 0x01, 0x08, 0xF7, 0, 0, 0, 0])
    assert x11.build_polling_report(3) == bytes([0x06, 0x09, 0x01, 0x01, 0xFE, 0, 0, 0, 0])


def test_build_polling_report_validates_index():
    with pytest.raises(ValueError):
        x11.build_polling_report(4)
    with pytest.raises(ValueError):
        x11.build_polling_report(-1)


def test_build_color_report_matches_reference_table():
    assert x11.build_color_report(1) == x11.COLOR_MODES[1]
    assert len(x11.build_color_report(0)) == 15
    with pytest.raises(ValueError):
        x11.build_color_report(4)


def test_build_profile_report_sets_angle_snap_and_ripple_flags():
    r = x11.build_profile_report(angle_snap=True, ripple_control=False)
    assert len(r) == 56
    assert r[0] == 0x04 and r[1] == 0x38 and r[2] == 0x01
    assert r[3] == 1 and r[4] == 0
    r2 = x11.build_profile_report(angle_snap=False, ripple_control=True)
    assert r2[3] == 0 and r2[4] == 1


def test_validate_settings_accepts_reference_ranges():
    x11.validate_settings(
        color_mode=0, polling_rate=3, angle_snap=True,
        key_resp_ms=8, sleep_min=5, deep_sleep_min=10, ripple_control=False,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(color_mode=4, polling_rate=0, angle_snap=True, key_resp_ms=8, sleep_min=5, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=-1, angle_snap=True, key_resp_ms=8, sleep_min=5, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=8, sleep_min=0, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=8, sleep_min=31, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=8, sleep_min=5, deep_sleep_min=0, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=8, sleep_min=5, deep_sleep_min=61, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=3, sleep_min=5, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=51, sleep_min=5, deep_sleep_min=10, ripple_control=False),
        dict(color_mode=0, polling_rate=0, angle_snap=True, key_resp_ms=7, sleep_min=5, deep_sleep_min=10, ripple_control=False),
    ],
)
def test_validate_settings_rejects_out_of_range(kwargs):
    with pytest.raises(ValueError):
        x11.validate_settings(**kwargs)


def test_settings_reports_cover_all_three_usb_reports():
    s = x11.MouseSettings(
        color_mode=2, polling_rate=1, angle_snap=True,
        key_resp_ms=8, sleep_min=5, deep_sleep_min=10, ripple_control=True,
    )
    reports = x11.settings_reports(s)
    assert [r[0] for r in reports] == [x11.REPORT_POLLING, x11.REPORT_COLOR, x11.REPORT_PROFILE]
    assert reports[0][1] == x11.build_polling_report(1)
    assert reports[1][1] == x11.build_color_report(2)
    assert reports[2][1] == x11.build_profile_report(True, True)


def test_mouse_settings_dataclass_roundtrips_to_dict():
    s = x11.MouseSettings()
    d = s.to_dict()
    assert d["color_mode"] == 0 and d["polling_rate"] == 0
    assert x11.MouseSettings.from_dict(d) == s
