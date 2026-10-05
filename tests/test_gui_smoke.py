"""Offscreen GUI smoke test (skipped when PyQt6 is unavailable)."""
import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from donglehub.models import DeviceStatus, PowerState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_status(device_id, **kw):
    base = dict(
        device_id=device_id, name="MCHOSE V9 PRO" if device_id == "headset" else "AttackShark X11",
        connected=True, connection="2.4ghz", battery_pct=77,
        power=PowerState.CHARGING, status_raw=1,
        details={"eq_name": "Music"} if device_id == "headset" else {},
    )
    base.update(kw)
    return DeviceStatus(**base)


def test_main_window_shows_both_devices(qapp):
    from donglehub.gui import MainWindow

    win = MainWindow(headset=None, mouse=None)
    win.update_devices(make_status("headset"), make_status("mouse"))
    assert "MCHOSE V9 PRO" in win.headset_card.title_label.text()
    assert "AttackShark X11" in win.mouse_card.title_label.text()
    assert "77" in win.headset_card.pct_label.text()
    assert "charging" in win.headset_card.power_label.text().lower()
    win.close()


def test_card_updates_for_disconnected_device(qapp):
    from donglehub.gui import DeviceCard

    card = DeviceCard("Mouse", "AttackShark X11")
    card.update_from(
        make_status("mouse", connected=False, connection=None, battery_pct=None,
                    power=PowerState.UNKNOWN)
    )
    assert "disconnected" in card.power_label.text().lower()
    assert card.battery_bar.value() == 0


def test_tray_setup_constructs_tray_icon(qapp, monkeypatch):
    from PyQt6.QtWidgets import QSystemTrayIcon

    from donglehub import gui

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    win = gui.MainWindow(headset=None, mouse=None)
    win._setup_tray()
    assert isinstance(win.tray, QSystemTrayIcon)
    win.close()


def test_eq_card_drives_controller_and_store(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from donglehub.eq import store
    from donglehub.gui import EqCard

    class Ctl:
        def __init__(self):
            self.bands = {}
            self.preamps = {}
            self.actions = []

        def set_band(self, i, g, s):
            self.bands[i] = g

        def set_preamp(self, g, s):
            self.preamps["preamp"] = g

        def apply(self, s, c=None):
            self.actions.append("apply")

        def restart(self):
            self.actions.append("restart")

        def enable(self):
            self.actions.append("enable")

        def disable(self):
            self.actions.append("disable")

    ctl = Ctl()
    card = EqCard(controller=ctl)
    card.set_band_value(2, 3.0)
    assert ctl.bands[2] == 3.0
    assert store.load_active().gains[2] == 3.0
    card.set_preamp_value(-4.0)
    assert ctl.preamps["preamp"] == -4.0
    # surround requires an HRIR first
    card.surround_check.setChecked(True)
    assert "HRIR" in card.status_label.text()
    card.hrir_edit.setText("/x/hesuvi.wav")
    card._hrir_changed()
    card.surround_check.setChecked(True)
    assert store.load_active().mode == "surround"
    assert "restart" in ctl.actions


def test_main_window_has_eq_tab(qapp):
    from donglehub.gui import EqCard, MainWindow

    win = MainWindow(headset=None, mouse=None)
    assert isinstance(win.eq_card, EqCard)
    assert win.eq_card.band_sliders and len(win.eq_card.band_sliders) == 10
    win.close()


def test_power_label_covers_all_states(qapp):
    from donglehub.gui import power_text

    assert power_text(PowerState.CHARGING) == "Charging \u26a1"
    assert power_text(PowerState.FULL) == "Charged"
    assert power_text(PowerState.ON_BATTERY) == "On battery"
    assert power_text(PowerState.UNKNOWN) == ""
