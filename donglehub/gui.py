"""DongleHub desktop app (PyQt6): both devices, battery + charging state,
plus the headset EQ/volume and mouse settings panels from the two upstream apps,
and the system-wide EQ tab.

Visual language: dark Material-style theme with custom-painted widgets
(battery bar, toggle switches, device icons).
"""
from __future__ import annotations

import sys
import time

from PyQt6.QtCore import Qt, QThread, QRectF, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QProgressBar,
    QSizePolicy,
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

# ── palette ─────────────────────────────────────────────────────────────

BG = "#14121A"
CARD = "#1C1922"
CARD_STROKE = "#2A2533"
SURFACE = "#241F2E"
TEXT = "#E9E2F0"
MUTED = "#A79BB8"
ACCENT = "#B79CFF"
ACCENT_DARK = "#1B1226"
GOOD = "#8CE6B8"
WARN = "#FFCE7A"
BAD = "#FF9C9C"

THEME_QSS = f"""
* {{ font-family: 'Inter', 'SF Pro Display', 'Segoe UI', 'Noto Sans', sans-serif; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 10.5pt; }}
QFrame#card {{ background: {CARD}; border: 1px solid {CARD_STROKE}; border-radius: 18px; }}
QFrame#divider {{ background: {CARD_STROKE}; border: none; max-height: 1px; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 700; color: #F4EEFA; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; color: #F4EEFA; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#small {{ font-size: 9pt; color: {MUTED}; }}
QLabel#pct {{ font-size: 30pt; font-weight: 700; color: #F4EEFA; }}
QLabel#section {{ font-size: 9pt; font-weight: 700; color: #CBB4FF; letter-spacing: 1.2px; }}
QLabel#chip {{ background: {SURFACE}; border-radius: 11px; padding: 4px 12px; color: #CFC4DE; font-size: 9pt; font-weight: 600; }}
QLabel#chip[accent="true"] {{ background: rgba(183, 156, 255, 0.16); color: {ACCENT}; }}
QLabel#chip[good="true"] {{ background: rgba(140, 230, 184, 0.13); color: {GOOD}; }}
QLabel#chip[warn="true"] {{ background: rgba(255, 206, 122, 0.13); color: {WARN}; }}
QLabel#chip[bad="true"]  {{ background: rgba(255, 156, 156, 0.13); color: {BAD}; }}
QPushButton#pill {{ background: {ACCENT}; color: {ACCENT_DARK}; border: none; border-radius: 16px; padding: 9px 18px; font-weight: 700; }}
QPushButton#pill:hover {{ background: #C7B1FF; }}
QPushButton#pill:pressed {{ background: #A288F0; }}
QPushButton#ghost {{ background: transparent; border: 1px solid #3A3347; border-radius: 14px; padding: 8px 16px; color: #DDD3EC; font-weight: 600; }}
QPushButton#ghost:hover {{ background: #241F2E; }}
QPushButton#ghost:checked {{ background: {ACCENT}; color: {ACCENT_DARK}; border-color: {ACCENT}; }}
QPushButton#ghost:disabled {{ color: #5C5470; border-color: #2A2533; }}
QComboBox, QLineEdit, QSpinBox {{
    background: {SURFACE}; border: 1px solid #332C41; border-radius: 10px;
    padding: 6px 12px; color: {TEXT}; selection-background-color: {ACCENT};
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: #4A405C; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid #332C41; border-radius: 10px;
    selection-background-color: #3A2F55; selection-color: {TEXT}; padding: 4px;
}}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 10px 22px;
    font-weight: 700; border-radius: 14px; margin-right: 6px;
}}
QTabBar::tab:selected {{ background: #2A2238; color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QSlider::groove:horizontal {{ height: 6px; background: #2A2533; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 18px; margin: -7px 0; border-radius: 9px; background: {ACCENT}; }}
QSlider::sub-page:horizontal {{ background: #6E58A8; border-radius: 3px; }}
QSlider#fader::groove:vertical {{ width: 6px; background: #2A2533; border-radius: 3px; }}
QSlider#fader::handle:vertical {{ height: 16px; margin: 0 -5px; border-radius: 8px; background: {ACCENT}; }}
QSlider#fader::sub-page:vertical {{ background: #6E58A8; border-radius: 3px; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid #332C41; border-radius: 8px; padding: 6px; }}
"""


# ── custom widgets ──────────────────────────────────────────────────────


def repaint_style(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class Chip(QLabel):
    """Small rounded status label with a tone. Collapses when empty."""

    TONES = ("accent", "good", "warn", "bad")

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.setVisible(bool(text))

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))

    def set_tone(self, tone):
        for t in self.TONES:
            self.setProperty(t, t == tone)
        repaint_style(self)


class ToggleSwitch(QCheckBox):
    """Pill-style on/off switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        enabled = self.isEnabled()
        track = QColor(ACCENT) if on else QColor("#3A3347")
        if not enabled:
            track.setAlpha(90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 2, 50, 24), 12, 12)
        knob = QColor(ACCENT_DARK) if on else QColor("#8A7FA0")
        if not enabled:
            knob.setAlpha(120)
        p.setBrush(knob)
        p.drawEllipse(QRectF(28 if on else 4, 5, 18, 18))


class BatteryBar(QProgressBar):
    """Rounded battery fill with state-aware colouring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(10)
        self._power = PowerState.UNKNOWN

    def set_power(self, power: PowerState):
        self._power = power
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), 8
        track = QRectF(0, 2, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2A2533"))
        p.drawRoundedRect(track, h / 2, h / 2)
        frac = max(0.0, min(1.0, self.value() / 100.0))
        if frac <= 0:
            return
        if self._power == PowerState.CHARGING:
            color = QColor(WARN)
        elif self._power == PowerState.FULL:
            color = QColor(GOOD)
        elif self.value() <= 20:
            color = QColor(BAD)
        else:
            color = QColor(ACCENT)
        fill = QRectF(0, 2, max(h, w * frac), h)
        p.setBrush(color)
        p.drawRoundedRect(fill, h / 2, h / 2)
        gloss = QRectF(fill.x() + 3, fill.y() + 1.5, max(0.0, fill.width() - 6), 2)
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawRoundedRect(gloss, 1, 1)


def draw_device_icon(painter: QPainter, rect: QRectF, kind: str, color: QColor):
    painter.save()
    painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

    if kind in ("headphones", "headset"):
        painter.drawArc(QRectF(x + w * 0.14, y + h * 0.16, w * 0.72, h * 0.72), 0, 180 * 16)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x + w * 0.06, y + h * 0.5, w * 0.17, h * 0.36), 5, 5)
        painter.drawRoundedRect(QRectF(x + w * 0.77, y + h * 0.5, w * 0.17, h * 0.36), 5, 5)
    elif kind == "mouse":
        body = QPainterPath()
        body.addRoundedRect(QRectF(x + w * 0.24, y + h * 0.14, w * 0.52, h * 0.72),
                            w * 0.26, w * 0.26)
        painter.drawPath(body)
        painter.drawLine(int(x + w * 0.5), int(y + h * 0.16),
                         int(x + w * 0.5), int(y + h * 0.42))
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x + w * 0.46, y + h * 0.22, w * 0.08, h * 0.14), 3, 3)
    elif kind == "bolt":
        path = QPainterPath()
        path.moveTo(x + w * 0.56, y + h * 0.08)
        path.lineTo(x + w * 0.22, y + h * 0.56)
        path.lineTo(x + w * 0.46, y + h * 0.56)
        path.lineTo(x + w * 0.42, y + h * 0.92)
        path.lineTo(x + w * 0.78, y + h * 0.42)
        path.lineTo(x + w * 0.54, y + h * 0.42)
        path.closeSubpath()
        painter.setBrush(color)
        painter.drawPath(path)
    elif kind == "eq":
        painter.setBrush(color)
        for i, frac in enumerate((0.25, 0.65, 0.4)):
            cx = x + w * (0.22 + i * 0.28)
            painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(int(cx), int(y + h * 0.12), int(cx), int(y + h * 0.88))
            knob_y = y + h * (0.12 + (1 - frac) * 0.62)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - 5, knob_y, 10, 10))
    painter.restore()


class IconTile(QFrame):
    """Rounded tile with a painted line icon."""

    def __init__(self, kind: str, size: int = 52, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        p.setOpacity(0.12)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 15, 15)
        p.setOpacity(1.0)
        draw_device_icon(
            p,
            QRectF(self.width() * 0.18, self.height() * 0.18,
                   self.width() * 0.64, self.height() * 0.64),
            self.kind,
            QColor("#D9CCFF"),
        )


def app_icon_pixmap(size: int = 64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.25, size * 0.25)
    draw_device_icon(p, QRectF(size * 0.15, size * 0.15, size * 0.7, size * 0.7),
                     "bolt", QColor(ACCENT_DARK))
    p.end()
    return pm


def power_text(power: PowerState) -> str:
    return {
        PowerState.CHARGING: "Charging \u26a1",
        PowerState.FULL: "Charged",
        PowerState.ON_BATTERY: "On battery",
        PowerState.UNKNOWN: "",
    }[power]


def power_tone(power: PowerState) -> str:
    return {
        PowerState.CHARGING: "warn",
        PowerState.FULL: "good",
        PowerState.ON_BATTERY: "accent",
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


def section_label(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    return line


class Fader(QSlider):
    """Vertical EQ fader with a subtle 0 dB tick."""

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#4A405C"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cy = int(self.height() / 2)
        cx = int(self.width() / 2)
        p.drawLine(cx - 10, cy, cx + 10, cy)


class DeviceCard(QFrame):
    def __init__(self, kind: str, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.kind = kind

        self.title_label = QLabel(title)
        self.title_label.setObjectName("h2")
        self.conn_label = Chip("-")
        self.pct_label = QLabel("--")
        self.pct_label.setObjectName("pct")
        self.battery_bar = BatteryBar()
        self.power_label = Chip("")
        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)

        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(IconTile(kind))
        titles = QVBoxLayout()
        titles.setSpacing(6)
        titles.addWidget(self.title_label)
        titles.addWidget(self.conn_label, alignment=Qt.AlignmentFlag.AlignLeft)
        head.addLayout(titles)
        head.addStretch(1)
        readout = QVBoxLayout()
        readout.setSpacing(6)
        readout.addWidget(self.pct_label, alignment=Qt.AlignmentFlag.AlignRight)
        readout.addWidget(self.power_label, alignment=Qt.AlignmentFlag.AlignRight)
        head.addLayout(readout)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(22, 20, 22, 22)
        self.body.setSpacing(14)
        self.body.addLayout(head)
        self.body.addWidget(self.battery_bar)
        self.body.addWidget(self.status_label)

        self.extras = QVBoxLayout()
        self.extras.setSpacing(12)
        self.body.addLayout(self.extras)
        self.body.addStretch(1)
        self.setLayout(self.body)

    def update_from(self, st: DeviceStatus) -> None:
        if not st.connected:
            self.pct_label.setText("--")
            self.power_label.setText("Disconnected")
            self.power_label.set_tone("bad")
            self.battery_bar.setValue(0)
            self.battery_bar.set_power(PowerState.UNKNOWN)
            self.conn_label.setText("-")
            self.conn_label.set_tone("")
            self.status_label.setText("")
            self._update_status(st)
            return
        conn = {"2.4ghz": "2.4G dongle", "bluetooth": "Bluetooth",
                "wired": "USB cable"}.get(st.connection or "", st.connection or "-")
        self.conn_label.setText(conn)
        self.conn_label.set_tone("accent")
        self.pct_label.setText(f"{st.battery_pct}%" if st.battery_pct is not None else "--")
        self.battery_bar.setValue(st.battery_pct or 0)
        self.battery_bar.set_power(st.power)
        self.power_label.setText(power_text(st.power))
        self.power_label.set_tone(power_tone(st.power))
        self._update_status(st)

    def _update_status(self, st: DeviceStatus) -> None:
        self.status_label.setText("")


class HeadsetCard(DeviceCard):
    def __init__(self, set_eq_fn=None, parent=None):
        super().__init__("headset", "MCHOSE V9 PRO", parent)
        self._set_eq_fn = set_eq_fn

        self.extras.addWidget(divider())
        self.extras.addWidget(section_label("Hardware EQ"))
        eq_row = QHBoxLayout()
        eq_row.setSpacing(8)
        self.eq_buttons = []
        for mode, name in sorted(mchose.EQ_MODES.items()):
            btn = QPushButton(name)
            btn.setObjectName("ghost")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mode: self._pick_eq(m))
            eq_row.addWidget(btn)
            self.eq_buttons.append(btn)
        eq_row.addStretch(1)
        self.extras.addLayout(eq_row)

        self.extras.addWidget(section_label("Audio (system)"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.vol_slider = self._slider()
        self.mic_slider = self._slider()
        self.mute_btn = QPushButton("Mute")
        self.mute_btn.setObjectName("ghost")
        self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_label = Chip("--")
        self.mic_label = Chip("--")
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
        self.extras.addLayout(grid)

        self.fw_label = QLabel("")
        self.fw_label.setObjectName("small")
        self.extras.addWidget(self.fw_label)

        self.audio = AudioService()
        self._audio_suspended = False

    @staticmethod
    def _slider():
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.vol_label.set_tone("bad" if muted else "")
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
            self.fw_label.setText(f"FW dongle {fd or '?'}  /  headset {fh or '?'}")
        self.status_label.setText(
            f"EQ: {st.details.get('eq_name') or ('mode ' + str(eq_mode) if eq_mode is not None else '-')}"
        )


class MouseCard(DeviceCard):
    def __init__(self, apply_fn=None, parent=None):
        super().__init__("mouse", "AttackShark X11", parent)
        self._apply_fn = apply_fn

        self.extras.addWidget(divider())
        self.extras.addWidget(section_label("Mouse settings"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.color_box = QComboBox()
        self.color_box.addItems(x11.COLOR_MODE_LABELS)
        self.poll_box = QComboBox()
        self.poll_box.addItems(x11.POLLING_RATE_LABELS)
        self.angle_check = ToggleSwitch()
        self.ripple_check = ToggleSwitch()
        self.key_spin = self._spin(4, 50, 8)
        self.sleep_spin = self._spin(1, 30, 5)
        self.deep_spin = self._spin(1, 60, 10)
        self.apply_btn = QPushButton("Apply settings")
        self.apply_btn.setObjectName("pill")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        switches = QHBoxLayout()
        switches.setSpacing(18)
        for label, widget in (("Angle snap", self.angle_check),
                              ("Ripple control", self.ripple_check)):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(widget)
            row.addWidget(QLabel(label))
            row.addStretch(1)
            switches.addLayout(row)
        grid.addLayout(switches, 5, 0, 1, 2)
        self.extras.addLayout(grid)

        foot = QHBoxLayout()
        foot.addWidget(self.apply_btn)
        self.apply_label = Chip("")
        foot.addWidget(self.apply_label)
        foot.addStretch(1)
        self.extras.addLayout(foot)

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
            self.apply_label.set_tone("good")
        except (ValueError, IOError) as e:
            self.apply_label.setText(f"Failed: {e}")
            self.apply_label.set_tone("bad")


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
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(18)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.enable_check = ToggleSwitch()
        self.enable_check.toggled.connect(self._toggle_enable)
        head.addWidget(self.enable_check)
        head.addWidget(QLabel("System EQ"))
        head.addStretch(1)
        self.preset_box = QComboBox()
        self.preset_box.setMinimumWidth(160)
        self.preset_box.setPlaceholderText("Presets\u2026")
        self._reload_presets()
        load_btn = QPushButton("Load")
        load_btn.setObjectName("ghost")
        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_btn.clicked.connect(self._load_preset)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("ghost")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_preset)
        flat_btn = QPushButton("Flat")
        flat_btn.setObjectName("ghost")
        flat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        flat_btn.clicked.connect(self._flat)
        head.addWidget(self.preset_box)
        head.addWidget(load_btn)
        head.addWidget(save_btn)
        head.addWidget(flat_btn)
        root.addLayout(head)

        bank = QHBoxLayout()
        bank.setSpacing(12)
        pre_col, self.preamp_slider = self._fader_column("Pre", self.MAX_PREAMP,
                                                        is_preamp=True)
        bank.addLayout(pre_col)
        sep = QFrame()
        sep.setObjectName("divider")
        sep.setFixedWidth(1)
        bank.addWidget(sep)
        self.band_sliders = []
        for i, band in enumerate(BANDS):
            col, slider = self._fader_column(band.label, self.MAX_GAIN, index=i)
            bank.addLayout(col)
            self.band_sliders.append(slider)
        bank.addStretch(1)
        root.addLayout(bank)

        surround_row = QHBoxLayout()
        surround_row.setSpacing(12)
        self.surround_check = ToggleSwitch()
        self.surround_check.toggled.connect(self._toggle_surround)
        surround_row.addWidget(self.surround_check)
        surround_row.addWidget(QLabel("Virtual surround (7.1)"))
        self.hrir_edit = QLineEdit(self.settings.hrir or "")
        self.hrir_edit.setPlaceholderText("HeSuVi HRIR wav path\u2026")
        self.hrir_edit.editingFinished.connect(self._hrir_changed)
        surround_row.addWidget(self.hrir_edit, 1)
        root.addLayout(surround_row)

        self.status_label = Chip("")
        root.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignLeft)
        self.setLayout(root)

        self._sync_from_settings()

    def _fader_column(self, label, limit, index=None, is_preamp=False):
        col = QVBoxLayout()
        col.setSpacing(8)
        value = Chip("+0.0")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.set_tone("accent")
        value.setFixedWidth(54)
        slider = Fader(Qt.Orientation.Vertical)
        slider.setObjectName("fader")
        slider.setRange(int(-limit * 10), int(limit * 10))
        slider.setValue(0)
        slider.setFixedSize(46, 220)
        slider.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_preamp:
            self.preamp_value = value
            slider.valueChanged.connect(self._preamp_changed)
        else:
            slider.valueChanged.connect(lambda v, idx=index: self._band_changed(idx, v))
            slider._value_chip = value
        name = QLabel(label)
        name.setObjectName("small")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFixedWidth(58)
        col.addWidget(value, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addWidget(slider, alignment=Qt.AlignmentFlag.AlignCenter)
        col.addWidget(name, alignment=Qt.AlignmentFlag.AlignCenter)
        return col, slider

    def _set_chip(self, chip, value):
        chip.setText(f"{value:+.1f}")
        chip.set_tone("accent" if value != 0 else "")

    def _sync_from_settings(self):
        self._syncing = True
        for s, g in zip(self.band_sliders, self.settings.gains):
            s.setValue(int(round(g * 10)))
            self._set_chip(s._value_chip, g)
        self.preamp_slider.setValue(int(round(self.settings.preamp * 10)))
        self._set_chip(self.preamp_value, self.settings.preamp)
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
            self.status_label.set_tone("bad")
            self.settings.gains[index] = 0.0
            return
        store.save_active(self.settings)
        self.controller.set_band(index, float(value), self.settings)
        self._set_chip(self.band_sliders[index]._value_chip, float(value))
        self.status_label.setText(
            f"band {index + 1} ({BANDS[index].label}): {float(value):+.1f} dB")
        self.status_label.set_tone("accent")

    def set_preamp_value(self, value):
        try:
            self.settings.preamp = float(value)
            EqSettings(**{**self.settings.to_dict()})
        except ValueError as e:
            self.status_label.setText(str(e))
            self.status_label.set_tone("bad")
            self.settings.preamp = 0.0
            return
        store.save_active(self.settings)
        self.controller.set_preamp(float(value), self.settings)
        self._set_chip(self.preamp_value, float(value))
        self.status_label.setText(f"preamp: {float(value):+.1f} dB")
        self.status_label.set_tone("accent")

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
            self.status_label.set_tone("good")
        else:
            self.controller.disable()
            self.status_label.setText("EQ disabled")
            self.status_label.set_tone("")

    def _toggle_surround(self, checked):
        if self._syncing:
            return
        if checked and not self.settings.hrir:
            self.status_label.setText("Set the HeSuVi HRIR wav path first")
            self.status_label.set_tone("warn")
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
        self.status_label.set_tone("good" if checked else "")

    def _hrir_changed(self):
        path = self.hrir_edit.text().strip()
        if path and path != self.settings.hrir:
            self.settings.hrir = path
            store.save_active(self.settings)
            self.status_label.setText(f"hrir: {path}")
            self.status_label.set_tone("accent")

    def _flat(self):
        self.settings.gains = [0.0] * len(BANDS)
        self.settings.preamp = 0.0
        store.save_active(self.settings)
        self._sync_from_settings()
        self.controller.apply(self.settings, None)
        self.status_label.setText("flat (0 dB)")
        self.status_label.set_tone("")

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
        self.status_label.set_tone("good")

    def _save_preset(self):
        name = self.preset_box.currentText().strip() or "custom"
        store.save_preset(name, self.settings)
        self._reload_presets()
        self.preset_box.setCurrentText(name)
        self.status_label.setText(f"saved preset {name!r}")
        self.status_label.set_tone("good")


class MainWindow(QMainWindow):
    def __init__(self, headset=None, mouse=None, hub=None, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.headset_dev = headset
        self.mouse_dev = mouse
        self.setWindowTitle("DongleHub")
        self.setWindowIcon(QIcon(app_icon_pixmap()))
        self.resize(860, 620)

        self.headset_card = HeadsetCard(set_eq_fn=self._set_eq)
        self.mouse_card = MouseCard(apply_fn=self._apply_mouse)
        self.eq_card = EqCard()

        devices = QWidget()
        row = QHBoxLayout()
        row.setContentsMargins(18, 18, 18, 18)
        row.setSpacing(18)
        row.addWidget(self.headset_card, 1)
        row.addWidget(self.mouse_card, 1)
        row.setAlignment(Qt.AlignmentFlag.AlignTop)
        devices.setLayout(row)

        tabs = QTabWidget()
        tabs.addTab(devices, "Devices")
        tabs.addTab(self.eq_card, "EQ")

        header = QHBoxLayout()
        header.setContentsMargins(26, 20, 26, 8)
        header.setSpacing(12)
        title = QLabel("DongleHub")
        title.setObjectName("h1")
        header.addWidget(title)
        try:
            from . import __version__

            ver = QLabel(f"v{__version__}")
            ver.setObjectName("small")
            header.addWidget(ver)
        except Exception:
            pass
        header.addStretch(1)

        central = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(tabs, 1)
        central.setLayout(layout)
        self.setCentralWidget(central)

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
            self.tray = QSystemTrayIcon(QIcon(app_icon_pixmap()), self)
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
    app.setStyleSheet(THEME_QSS)
    hub = Hub()
    win = MainWindow(headset=hub.headset, mouse=hub.mouse, hub=hub)
    win.show()
    return app.exec()
