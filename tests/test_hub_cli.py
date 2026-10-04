"""Hub and CLI tests (device layer faked)."""
import json

from donglehub import cli
from donglehub.models import PowerState

from fakes import FakeHub, sample_status


def make_hub(headset_kw=None, mouse_kw=None):
    hs = sample_status("headset", name="MCHOSE V9 PRO", **(headset_kw or {}))
    ms = sample_status("mouse", name="AttackShark X11", **(mouse_kw or {}))
    return FakeHub(hs, ms)


def test_status_json_prints_snapshot(capsys):
    rc = cli.main(["status", "--json"], hub=make_hub())
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["schema"] == 1
    assert set(out["devices"]) == {"headset", "mouse"}
    assert out["devices"]["headset"]["name"] == "MCHOSE V9 PRO"
    assert out["devices"]["mouse"]["battery"] == 42


def test_status_human_lists_both_devices(capsys):
    rc = cli.main(["status"], hub=make_hub(headset_kw={"power": PowerState.CHARGING}))
    out = capsys.readouterr().out
    assert rc == 0
    assert "MCHOSE V9 PRO" in out
    assert "AttackShark X11" in out
    assert "charging" in out


def test_status_human_shows_disconnected_devices(capsys):
    hub = make_hub(
        headset_kw={"connected": False, "connection": None, "battery_pct": None,
                    "power": PowerState.UNKNOWN},
    )
    cli.main(["status"], hub=hub)
    out = capsys.readouterr().out
    assert "disconnected" in out


def test_set_eq_accepts_numeric_and_named_modes(capsys):
    hub = make_hub()
    assert cli.main(["set-eq", "1"], hub=hub) == 0
    assert cli.main(["set-eq", "music"], hub=hub) == 0
    assert hub.eq_sets == [1, 2]


def test_set_eq_rejects_unknown_mode(capsys):
    hub = make_hub()
    assert cli.main(["set-eq", "banana"], hub=hub) != 0


def test_set_mouse_applies_settings(capsys):
    hub = make_hub()
    rc = cli.main(
        ["set-mouse", "--color", "2", "--polling", "1000", "--angle-snap", "on",
         "--ripple", "off", "--key-resp", "8", "--sleep", "5", "--deep-sleep", "10"],
        hub=hub,
    )
    assert rc == 0
    s = hub.mouse_settings[0]
    assert s.color_mode == 2
    assert s.polling_rate == 3  # 1000 Hz is index 3
    assert s.angle_snap is True and s.ripple_control is False


def test_set_mouse_rejects_bad_polling(capsys):
    hub = make_hub()
    assert cli.main(["set-mouse", "--polling", "333"], hub=hub) != 0


def test_bare_command_launches_gui_when_display_available(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    calls = []
    monkeypatch.setattr(cli, "cmd_gui", lambda: calls.append(True) or 0)
    assert cli.main([]) == 0
    assert calls == [True]


def test_bare_command_prints_help_on_headless(capsys, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "gui" in out


def test_watch_emits_snapshot_and_stops():
    hub = make_hub()
    snaps = []

    def emit(snap):
        snaps.append(snap)
        return len(snaps) < 3  # stop after 3 emissions

    rc = cli.watch_loop(hub, interval=0.0, emit=emit, max_polls=10)
    assert rc == 0
    assert len(snaps) == 3
    assert snaps[0]["schema"] == 1
