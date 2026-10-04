"""Device-layer tests: MCHOSE V9 PRO headset and AttackShark X11 mouse."""
import pytest

from donglehub.devices.headset import MchoseV9Pro
from donglehub.devices.mouse import AttackSharkX11
from donglehub.errors import DeviceUnavailable
from donglehub.models import PowerState
from donglehub.protocols import mchose, x11

from fakes import FakeX11Backend, RaisingSessionFactory, ScriptedHid


def status_reply(battery, status=0x00):
    r = bytearray(64)
    r[0], r[1] = 0x55, 0x65
    r[2], r[3] = battery, status
    return bytes(r)


def eq_reply(mode):
    r = bytearray(64)
    r[0], r[1], r[2] = 0x55, 0x11, mode
    return bytes(r)


# ── headset ──────────────────────────────────────────────────────────────


def test_headset_poll_reports_battery_and_connection():
    hid = ScriptedHid(replies=[status_reply(87), eq_reply(1)])
    hs = MchoseV9Pro(session_factory=lambda: hid)
    st = hs.poll()
    assert st.connected is True
    assert st.connection == "2.4ghz"
    assert st.battery_pct == 87
    assert st.status_raw == 0
    assert st.details["eq_mode"] == 1
    assert hid.writes[0][:3] == bytes([0x55, 0x65, 0x01])
    assert hid.writes[1][:2] == bytes([0x55, 0x11])
    assert hid.closed is True


def test_headset_poll_without_dongle_is_disconnected():
    hs = MchoseV9Pro(session_factory=RaisingSessionFactory())
    st = hs.poll()
    assert st.connected is False
    assert st.battery_pct is None
    assert st.power is PowerState.UNKNOWN


def test_headset_poll_garbage_reply_is_connected_with_unknown_battery():
    hid = ScriptedHid(replies=[b"\x00" * 64, b"\x00" * 64])
    hs = MchoseV9Pro(session_factory=lambda: hid)
    st = hs.poll()
    assert st.connected is True
    assert st.battery_pct is None


def test_headset_set_eq_writes_command_and_verifies_mode():
    hid = ScriptedHid(replies=[eq_reply(2)])
    hs = MchoseV9Pro(session_factory=lambda: hid)
    assert hs.set_eq(1) == 2
    assert hid.writes[0] == mchose.cmd_eq_set(1)
    assert hid.writes[1][:2] == bytes([0x55, 0x11])


def test_headset_firmware_uses_feature_report():
    fw = bytearray(64)
    fw[0] = 0xAA
    fw[8], fw[9], fw[10], fw[11] = 1, 2, 3, 4
    hid = ScriptedHid(replies=[bytes(fw)])
    hs = MchoseV9Pro(session_factory=lambda: hid)
    assert hs.firmware() == ("0102", "0304")
    assert hid.features_sent[0][:3] == bytes([0xAA, 0x01, 0x00])


# ── mouse ────────────────────────────────────────────────────────────────


def test_mouse_poll_reads_battery_over_24g():
    pkt = bytes([0x03, 0x55, 0x40, 0x01, 55]) + bytes(59)
    backend = FakeX11Backend(wireless=True, battery_packets=[pkt])
    mouse = AttackSharkX11(backend=backend)
    st = mouse.poll()
    assert st.connected is True
    assert st.connection == "2.4ghz"
    assert st.battery_pct == 55
    assert st.power is PowerState.UNKNOWN  # first reading, no trend yet


def test_mouse_poll_without_wireless_packets_means_charging():
    backend = FakeX11Backend(wireless=True, battery_packets=[])
    mouse = AttackSharkX11(backend=backend)
    st = mouse.poll()
    assert st.connected is True
    assert st.battery_pct is None
    assert st.power is PowerState.CHARGING
    assert st.charging is True


def test_mouse_poll_wired_connection_is_charging():
    backend = FakeX11Backend(wireless=False, wired=True, battery_packets=[])
    mouse = AttackSharkX11(backend=backend)
    st = mouse.poll()
    assert st.connection == "wired"
    assert st.power is PowerState.CHARGING


def test_mouse_poll_absent_is_disconnected():
    backend = FakeX11Backend(wireless=False, wired=False)
    mouse = AttackSharkX11(backend=backend)
    st = mouse.poll()
    assert st.connected is False
    assert st.battery_pct is None


def test_mouse_poll_without_usb_stack_is_disconnected():
    from fakes import RaisingX11Backend

    mouse = AttackSharkX11(backend=RaisingX11Backend())
    st = mouse.poll()
    assert st.connected is False
    assert st.battery_pct is None


def test_mouse_apply_settings_sends_three_reports_with_delay():
    backend = FakeX11Backend()
    sleeps = []
    mouse = AttackSharkX11(backend=backend, sleep=sleeps.append)
    mouse.apply_settings(
        x11.MouseSettings(color_mode=1, polling_rate=2, angle_snap=True,
                          key_resp_ms=8, sleep_min=5, deep_sleep_min=10,
                          ripple_control=True)
    )
    assert [r for r, _ in backend.sent] == [0x0306, 0x0305, 0x0304]
    assert backend.sent[0][1] == x11.build_polling_report(2)
    assert backend.sent[1][1] == x11.build_color_report(1)
    assert backend.sent[2][1] == x11.build_profile_report(True, True)
    assert sleeps and all(s == 0.3 for s in sleeps)


def test_mouse_apply_settings_rejects_invalid_ranges():
    mouse = AttackSharkX11(backend=FakeX11Backend())
    with pytest.raises(ValueError):
        mouse.apply_settings(x11.MouseSettings(color_mode=9))
