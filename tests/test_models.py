"""Tests for shared status models and power-state interpretation."""
from donglehub.models import DeviceStatus, PowerState, PowerTracker, hub_snapshot


def make_status(**kw):
    base = dict(
        device_id="headset", name="MCHOSE V9 PRO", connected=True,
        connection="2.4ghz", battery_pct=80, power=PowerState.ON_BATTERY,
        status_raw=0,
    )
    base.update(kw)
    return DeviceStatus(**base)


def test_device_status_to_dict_has_expected_shape():
    d = make_status().to_dict()
    assert d["device"] == "headset"
    assert d["name"] == "MCHOSE V9 PRO"
    assert d["connected"] is True
    assert d["connection"] == "2.4ghz"
    assert d["battery"] == 80
    assert d["power"] == "on_battery"
    assert d["charging"] is False
    assert d["charged"] is False
    assert d["status_raw"] == 0


def test_charging_flags_reflect_power_state():
    assert make_status(power=PowerState.CHARGING).to_dict()["charging"] is True
    assert make_status(power=PowerState.FULL).to_dict()["charged"] is True


def test_disconnected_device_reports_null_battery():
    d = make_status(connected=False, connection=None, battery_pct=None,
                    power=PowerState.UNKNOWN).to_dict()
    assert d["battery"] is None
    assert d["power"] == "unknown"


def test_summary_text_covers_states():
    assert make_status(power=PowerState.CHARGING).summary() == "80% (charging)"
    assert make_status(power=PowerState.FULL, battery_pct=100).summary() == "100% (charged)"
    assert make_status(power=PowerState.ON_BATTERY).summary() == "80%"
    assert make_status(connected=False, battery_pct=None).summary() == "disconnected"


def test_tracker_first_reading_without_signals_is_unknown():
    t = PowerTracker()
    assert t.update(50, None) == PowerState.UNKNOWN


def test_tracker_uses_trend_to_detect_charging_and_discharging():
    t = PowerTracker()
    t.update(50, None)
    assert t.update(55, None) == PowerState.CHARGING
    assert t.update(51, None) == PowerState.ON_BATTERY


def test_tracker_reports_full_at_100_percent():
    t = PowerTracker()
    t.update(98, None)
    assert t.update(100, None) == PowerState.FULL
    # stays full while still plugged at 100 with no other signal
    assert t.update(100, None) == PowerState.FULL


def test_tracker_hint_wins_over_trend_but_full_wins_at_100():
    t = PowerTracker()
    assert t.update(50, None, hint=PowerState.CHARGING) == PowerState.CHARGING
    assert t.update(100, None, hint=PowerState.CHARGING) == PowerState.FULL


def test_tracker_status_map_override_beats_everything():
    t = PowerTracker(status_map={0x07: "charging"})
    assert t.update(50, 0x07) == PowerState.CHARGING


def test_tracker_keeps_previous_state_when_flat():
    t = PowerTracker()
    t.update(50, None, hint=PowerState.CHARGING)
    assert t.update(50, None) == PowerState.CHARGING


def test_hub_snapshot_groups_devices_with_schema():
    snap = hub_snapshot(make_status(), make_status(device_id="mouse", name="AttackShark X11"))
    assert snap["schema"] == 1
    assert "updated" in snap
    assert set(snap["devices"]) == {"headset", "mouse"}
    assert snap["devices"]["mouse"]["name"] == "AttackShark X11"
