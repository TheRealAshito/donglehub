"""DongleHub desktop app (PyQt6): both devices, battery + charging state,
plus the headset EQ/volume and mouse settings panels from the two upstream apps."""
from __future__ import annotations

import sys
import time

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QProgressBar,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioService
from .eq import store
from .eq.control import EqController
from .eq.model import BANDS, EqSettings
from .hub import device_lock
from .models import DeviceStatus, PowerState
from .protocols import mchose, x11

POLL_INTERVAL_S = 3.0


def power_text(power: PowerState) -> str:
    return {
        PowerState.CHARGING: "Charging \u26a1",
        PowerState.FULL: "Charged",
        PowerState.ON_BATTERY: "On battery",
        PowerState.UNKNOWN: "",
    }[power]


class Poller(QThread):
    updated = pyqtSignal(object, object, object)  # headset, mouse, audio

    def __init__(self, hub, audio, interval=POLL_INTERVAL_S, parent=None):
        super().__init__(parent)
        self._hub = hub
        self._audio = audio
        self._interval = interval
        self._running = True

    def run(self):
        while self._running:
            try:
                hs, ms = self._hub.poll_devices()
            except Exception:
                hs = DeviceStatus("headset", "MCHOSE V9 PRO", False, None,
                                  power=PowerState.UNKNOWN)
                ms = DeviceStatus("mouse", "AttackShark X11", False, None,
                                  power=PowerState.UNKNOWN)
            try:
                audio = self._audio.get()
            except Exception:
                audio = None
            self.updated.emit(hs, ms, audio)
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(4000)


class DeviceCard(QFrame):
    def __init__(self, kind: str, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.kind = kind

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.conn_label = QLabel("-")
        self.pct_label = QLabel("--")
        self.pct_label.setStyleSheet("font-size: 34px; font-weight: bold;")
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(0)
        self.battery_bar.setTextVisible(False)
        self.battery_bar.setFixedHeight(10)
        self.power_label = QLabel("")
        self.status_label = QLabel("")

        self.body = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(self.title_label)
        head.addStretch(1)
        head.addWidget(self.conn_label)
        self.body.addLayout(head)

        pct_row = QHBoxLayout()
        pct_row.addWidget(self.pct_label)
        pct_row.addStretch(1)
        pct_row.addWidget(self.power_label)
        self.body.addLayout(pct_row)
        self.body.addWidget(self.battery_bar)
        self.body.addWidget(self.status_label)

        self.extras = QVBoxLayout()
        self.body.addLayout(self.extras)
        self.setLayout(self.body)

    def update_from(self, st: DeviceStatus) -> None:
        if not st.connected:
            self.pct_label.setText("--")
            self.power_label.setText("Disconnected")
            self.battery_bar.setValue(0)
            self.conn_label.setText("-")
            self.status_label.setText("")
            return
        conn = {"2.4ghz": "2.4G dongle", "bluetooth": "Bluetooth",
                "wired": "USB cable"}.get(st.connection or "", st.connection or "-")
        self.conn_label.setText(conn)
        self.pct_label.setText(f"{st.battery_pct}%" if st.battery_pct is not None else "--")
        self.battery_bar.setValue(st.battery_pct or 0)
        self.power_label.setText(power_text(st.power))
        self._update_status(st)

    def _update_status(self, st: DeviceStatus) -> None:
        self.status_label.setText("")


class HeadsetCard(DeviceCard):
    def __init__(self, set_eq_fn=None, parent=None):
        super().__init__("headset", "MCHOSE V9 PRO", parent)
        self._set_eq_fn = set_eq_fn

        eq_box = QGroupBox("EQ profile (hardware)")
        eq_row = QHBoxLayout()
        self.eq_buttons = []
        for mode, name in sorted(mchose.EQ_MODES.items()):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, m=mode: self._pick_eq(m))
            eq_row.addWidget(btn)
            self.eq_buttons.append(btn)
        eq_box.setLayout(eq_row)

        audio_box = QGroupBox("Audio (system)")
        grid = QGridLayout()
        self.vol_slider = self._slider()
        self.mic_slider = self._slider()
        self.mute_btn = QPushButton("Mute")
        self.vol_label = QLabel("--")
        self.mic_label = QLabel("--")
        self.vol_slider.valueChanged.connect(self._vol_changed)
        self.mic_slider.valueChanged.connect(self._mic_changed)
        self.mute_btn.clicked.connect(self._mute)
        grid.addWidget(QLabel("Volume"), 0, 0)
        grid.addWidget(self.vol_slider, 0, 1)
        grid.addWidget(self.vol_label, 0, 2)
        grid.addWidget(self.mute_btn, 0, 3)
        grid.addWidget(QLabel("Microphone"), 1, 0)
        grid.addWidget(self.mic_slider, 1, 1)
        grid.addWidget(self.mic_label, 1, 2)
        audio_box.setLayout(grid)

        self.fw_label = QLabel("")
        self.extras.addWidget(eq_box)
        self.extras.addWidget(audio_box)
        self.extras.addWidget(self.fw_label)

        self.audio = AudioService()
        self._audio_suspended = False

    @staticmethod
    def _slider():
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        return s

    def attach_poller(self, poller: Poller):
        poller.updated.connect(self._on_audio)

    def _on_audio(self, _hs, _ms, audio):
        if not audio:
            return
        vol, muted, mic = audio
        self._audio_suspended = True
        self.vol_slider.setValue(vol)
        self.mic_slider.setValue(mic)
        self.vol_label.setText(f"{vol}%" + (" (muted)" if muted else ""))
        self.mic_label.setText(f"{mic}%")
        self.mute_btn.setText("Unmute" if muted else "Mute")
        self._audio_suspended = False

    def _vol_changed(self, v):
        if not self._audio_suspended:
            self.audio.set_volume(v)

    def _mic_changed(self, v):
        if not self._audio_suspended:
            self.audio.set_mic_volume(v)

    def _mute(self):
        self.audio.toggle_mute()

    def _pick_eq(self, mode):
        if self._set_eq_fn:
            self._set_eq_fn(mode)

    def _update_status(self, st: DeviceStatus) -> None:
        eq_mode = st.details.get("eq_mode")
        for btn in self.eq_buttons:
            btn.setChecked(btn.text() == st.details.get("eq_name"))
            btn.setEnabled(st.connected and st.connection == "2.4ghz")
        if st.details.get("firmware"):
            fd, fh = st.details["firmware"]
            self.fw_label.setText(f"FW dongle {fd or '?'} / headset {fh or '?'}")
        self.status_label.setText(
            f"EQ: {st.details.get('eq_name') or ('mode ' + str(eq_mode) if eq_mode is not None else '-')}"
        )


class MouseCard(DeviceCard):
    def __init__(self, apply_fn=None, parent=None):
        super().__init__("mouse", "AttackShark X11", parent)
        self._apply_fn = apply_fn

        box = QGroupBox("Mouse settings")
        grid = QGridLayout()
        self.color_box = QComboBox()
        self.color_box.addItems(x11.COLOR_MODE_LABELS)
        self.poll_box = QComboBox()
        self.poll_box.addItems(x11.POLLING_RATE_LABELS)
        self.angle_check = QCheckBox("Angle snap")
        self.ripple_check = QCheckBox("Ripple control")
        self.key_spin = self._spin(4, 50, 8)
        self.sleep_spin = self._spin(1, 30, 5)
        self.deep_spin = self._spin(1, 60, 10)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply)

        grid.addWidget(QLabel("LED mode"), 0, 0)
        grid.addWidget(self.color_box, 0, 1)
        grid.addWidget(QLabel("Polling rate"), 1, 0)
        grid.addWidget(self.poll_box, 1, 1)
        grid.addWidget(QLabel("Key response (ms)"), 2, 0)
        grid.addWidget(self.key_spin, 2, 1)
        grid.addWidget(QLabel("Sleep (min)"), 3, 0)
        grid.addWidget(self.sleep_spin, 3, 1)
        grid.addWidget(QLabel("Deep sleep (min)"), 4, 0)
        grid.addWidget(self.deep_spin, 4, 1)
        grid.addWidget(self.angle_check, 5, 0)
        grid.addWidget(self.ripple_check, 5, 1)
        grid.addWidget(self.apply_btn, 6, 0, 1, 2)
        box.setLayout(grid)
        self.extras.addWidget(box)
        self.apply_label = QLabel("")
        self.extras.addWidget(self.apply_label)

    @staticmethod
    def _spin(lo, hi, val):
        from PyQt6.QtWidgets import QSpinBox

        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _apply(self):
        settings = x11.MouseSettings(
            color_mode=self.color_box.currentIndex(),
            polling_rate=self.poll_box.currentIndex(),
            angle_snap=self.angle_check.isChecked(),
            key_resp_ms=self.key_spin.value(),
            sleep_min=self.sleep_spin.value(),
            deep_sleep_min=self.deep_spin.value(),
            ripple_control=self.ripple_check.isChecked(),
        )
        try:
            if self._apply_fn:
                self._apply_fn(settings)
            self.apply_label.setText("Applied")
        except (ValueError, IOError) as e:
            self.apply_label.setText(f"Failed: {e}")


class EqCard(QFrame):
    """System-wide EQ: 10 bands + preamp + HeSuVi virtual surround."""

    MAX_GAIN = 12.0
    MAX_PREAMP = 20.0

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller or EqController()
        self.settings = store.load_active()
        self._syncing = False

        root = QVBoxLayout()

        head = QHBoxLayout()
        self.enable_check = QCheckBox("Enable EQ sink")
        self.enable_check.toggled.connect(self._toggle_enable)
        self.preset_box = QComboBox()
        self._reload_presets()
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_preset)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_preset)
        self.status_label = QLabel("")
        head.addWidget(self.enable_check)
        head.addStretch(1)
        head.addWidget(self.preset_box)
        head.addWidget(load_btn)
        head.addWidget(save_btn)
        root.addLayout(head)

        sliders = QHBoxLayout()
        self.preamp_slider = self._make_slider(self.MAX_PREAMP)
        self.preamp_slider.valueChanged.connect(self._preamp_changed)
        pre_col = QVBoxLayout()
        pre_col.addWidget(QLabel("Pre"), alignment=Qt.AlignmentFlag.AlignCenter)
        pre_col.addWidget(self.preamp_slider)
        sliders.addLayout(pre_col)
        self.band_sliders = []
        for i, band in enumerate(BANDS):
            s = self._make_slider(self.MAX_GAIN)
            s.valueChanged.connect(lambda v, idx=i: self._band_changed(idx, v))
            col = QVBoxLayout()
            col.addWidget(QLabel(band.label), alignment=Qt.AlignmentFlag.AlignCenter)
            col.addWidget(s)
            sliders.addLayout(col)
            self.band_sliders.append(s)
        root.addLayout(sliders)

        surround_row = QHBoxLayout()
        self.surround_check = QCheckBox("7.1 virtual surround (HeSuVi HRIR)")
        self.surround_check.toggled.connect(self._toggle_surround)
        self.hrir_edit = QLineEdit(self.settings.hrir or "")
        self.hrir_edit.setPlaceholderText("/path/to/hesuvi.wav")
        self.hrir_edit.editingFinished.connect(self._hrir_changed)
        surround_row.addWidget(self.surround_check)
        surround_row.addWidget(self.hrir_edit, 1)
        root.addLayout(surround_row)
        root.addWidget(self.status_label)
        self.setLayout(root)

        self._sync_from_settings()

    @staticmethod
    def _make_slider(limit):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(int(-limit * 10), int(limit * 10))
        s.setValue(0)
        s.setTickPosition(QSlider.TickPosition.TicksBelow)
        return s

    def _sync_from_settings(self):
        self._syncing = True
        for s, g in zip(self.band_sliders, self.settings.gains):
            s.setValue(int(round(g * 10)))
        self.preamp_slider.setValue(int(round(self.settings.preamp * 10)))
        self.surround_check.setChecked(self.settings.mode == "surround")
        self._syncing = False

    def _reload_presets(self):
        self.preset_box.clear()
        self.preset_box.addItems(store.list_presets())

    def set_band_value(self, index, value):
        try:
            self.settings.gains[index] = float(value)
            EqSettings(**{**self.settings.to_dict()})
        except ValueError as e:
            self.status_label.setText(str(e))
            self.settings.gains[index] = 0.0
            return
        store.save_active(self.settings)
        self.controller.set_band(index, float(value), self.settings)
        self.status_label.setText(f"band {index + 1} ({BANDS[index].label}): {float(value):+.1f} dB")

    def set_preamp_value(self, value):
        try:
            self.settings.preamp = float(value)
            EqSettings(**{**self.settings.to_dict()})
        except ValueError as e:
            self.status_label.setText(str(e))
            self.settings.preamp = 0.0
            return
        store.save_active(self.settings)
        self.controller.set_preamp(float(value), self.settings)
        self.status_label.setText(f"preamp: {float(value):+.1f} dB")

    def _band_changed(self, index, slider_value):
        if not self._syncing:
            self.set_band_value(index, slider_value / 10.0)

    def _preamp_changed(self, slider_value):
        if not self._syncing:
            self.set_preamp_value(slider_value / 10.0)

    def _toggle_enable(self, checked):
        if checked:
            msg = self.controller.install(self.settings)
            self.status_label.setText(msg)
        else:
            self.controller.disable()
            self.status_label.setText("EQ disabled")

    def _toggle_surround(self, checked):
        if self._syncing:
            return
        if checked and not self.settings.hrir:
            self.status_label.setText("Set the HeSuVi HRIR wav path first")
            self._syncing = True
            self.surround_check.setChecked(False)
            self._syncing = False
            return
        self.settings.mode = "surround" if checked else "eq"
        store.save_active(self.settings)
        self.controller.restart()
        self.status_label.setText(
            "virtual surround enabled" if checked else "virtual surround disabled"
        )

    def _hrir_changed(self):
        path = self.hrir_edit.text().strip()
        if path and path != self.settings.hrir:
            self.settings.hrir = path
            store.save_active(self.settings)
            self.status_label.setText(f"hrir: {path}")

    def _load_preset(self):
        name = self.preset_box.currentText()
        if not name:
            return
        try:
            self.settings = store.load_preset(name)
        except KeyError:
            return
        store.save_active(self.settings)
        self._sync_from_settings()
        self.controller.apply(self.settings, None)
        self.controller.restart()
        self.status_label.setText(f"loaded preset {name!r}")

    def _save_preset(self):
        name = self.preset_box.currentText().strip() or "custom"
        store.save_preset(name, self.settings)
        self._reload_presets()
        self.preset_box.setCurrentText(name)
        self.status_label.setText(f"saved preset {name!r}")


class MainWindow(QMainWindow):
    def __init__(self, headset=None, mouse=None, hub=None, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.headset_dev = headset
        self.mouse_dev = mouse
        self.setWindowTitle("DongleHub")
        self.resize(780, 560)

        self.headset_card = HeadsetCard(set_eq_fn=self._set_eq)
        self.mouse_card = MouseCard(apply_fn=self._apply_mouse)
        self.eq_card = EqCard()

        devices = QWidget()
        row = QHBoxLayout()
        row.addWidget(self.headset_card, 1)
        row.addWidget(self.mouse_card, 1)
        devices.setLayout(row)

        tabs = QTabWidget()
        tabs.addTab(devices, "Devices")
        tabs.addTab(self.eq_card, "EQ")
        self.setCentralWidget(tabs)

        self.poller = None
        self.tray = None
        if hub is not None:
            self._setup_tray()
            self.poller = Poller(hub, self.headset_card.audio, parent=self)
            self.poller.updated.connect(self._on_poll)
            self.headset_card.attach_poller(self.poller)
            self.poller.start()

    def _setup_tray(self):
        try:
            self.tray = QSystemTrayIcon(QIcon.fromTheme("battery"), self)
            menu = QMenu(self)
            show = QAction("Show", self)
            show.triggered.connect(self.show)
            quit_a = QAction("Quit", self)
            quit_a.triggered.connect(self.close)
            menu.addAction(show)
            menu.addAction(quit_a)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip("DongleHub")
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show()
        except Exception:
            # The tray is optional chrome; never let it kill the app.
            self.tray = None

    def update_devices(self, hs: DeviceStatus, ms: DeviceStatus) -> None:
        self.headset_card.update_from(hs)
        self.mouse_card.update_from(ms)
        if self.tray is not None:
            self.tray.setToolTip(
                f"Headset {hs.summary()} | Mouse {ms.summary()}"
            )

    def _on_poll(self, hs, ms, _audio):
        self.update_devices(hs, ms)

    def _set_eq(self, mode):
        if not self.headset_dev:
            return
        with device_lock():
            self.headset_dev.set_eq(mode)

    def _apply_mouse(self, settings):
        if not self.mouse_dev:
            return
        with device_lock():
            self.mouse_dev.apply_settings(settings)

    def closeEvent(self, event):
        if self.poller is not None:
            self.poller.stop()
        super().closeEvent(event)


def run() -> int:
    from .hub import Hub

    app = QApplication(sys.argv)
    app.setApplicationName("DongleHub")
    hub = Hub()
    win = MainWindow(headset=hub.headset, mouse=hub.mouse, hub=hub)
    win.show()
    return app.exec()
