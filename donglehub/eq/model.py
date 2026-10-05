"""EQ settings model: bands, gains, modes, validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

MIN_GAIN, MAX_GAIN = -12.0, 12.0
MIN_PREAMP, MAX_PREAMP = -20.0, 20.0
MODES = ("eq", "surround")


@dataclass(frozen=True)
class Band:
    label: str
    kind: str  # bq_lowshelf | bq_peaking | bq_highshelf
    freq: float


BANDS = (
    Band("31 Hz", "bq_lowshelf", 31.0),
    Band("62 Hz", "bq_peaking", 62.0),
    Band("125 Hz", "bq_peaking", 125.0),
    Band("250 Hz", "bq_peaking", 250.0),
    Band("500 Hz", "bq_peaking", 500.0),
    Band("1 kHz", "bq_peaking", 1000.0),
    Band("2 kHz", "bq_peaking", 2000.0),
    Band("4 kHz", "bq_peaking", 4000.0),
    Band("8 kHz", "bq_peaking", 8000.0),
    Band("16 kHz", "bq_highshelf", 16000.0),
)


@dataclass
class EqSettings:
    gains: List[float] = field(default_factory=lambda: [0.0] * len(BANDS))
    preamp: float = 0.0
    mode: str = "eq"
    hrir: Optional[str] = None

    def __post_init__(self):
        self.gains = [float(g) for g in self.gains]
        self.preamp = float(self.preamp)
        if len(self.gains) != len(BANDS):
            raise ValueError(f"expected {len(BANDS)} gains, got {len(self.gains)}")
        for g in self.gains:
            if not MIN_GAIN <= g <= MAX_GAIN:
                raise ValueError(f"gain {g} outside {MIN_GAIN}..{MAX_GAIN} dB")
        if not MIN_PREAMP <= self.preamp <= MAX_PREAMP:
            raise ValueError(f"preamp {self.preamp} outside {MIN_PREAMP}..{MAX_PREAMP} dB")
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if self.mode == "surround" and not self.hrir:
            raise ValueError("surround mode requires an HRIR file (see `donglehub eq hrir`)")

    def to_dict(self) -> dict:
        return {
            "gains": list(self.gains),
            "preamp": self.preamp,
            "mode": self.mode,
            "hrir": self.hrir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EqSettings":
        return cls(
            gains=d.get("gains", [0.0] * len(BANDS)),
            preamp=d.get("preamp", 0.0),
            mode=d.get("mode", "eq"),
            hrir=d.get("hrir"),
        )
