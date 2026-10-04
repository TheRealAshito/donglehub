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


def test_power_label_covers_all_states(qapp):
    from donglehub.gui import power_text

    assert power_text(PowerState.CHARGING) == "Charging \u26a1"
    assert power_text(PowerState.FULL) == "Charged"
    assert power_text(PowerState.ON_BATTERY) == "On battery"
    assert power_text(PowerState.UNKNOWN) == ""
