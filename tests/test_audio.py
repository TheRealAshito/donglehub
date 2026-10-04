"""Tests for PipeWire/ALSA volume + mic integration (wpctl/amixer)."""
from donglehub.audio import AudioService


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        return self.outputs.pop(0) if self.outputs else ""


def test_parse_volume_plain():
    svc = AudioService(run=FakeRunner(["Volume: 0.45\n", "Volume: 0.30\n"]))
    vol, muted, mic = svc.get()
    assert vol == 45 and muted is False and mic == 30


def test_parse_volume_muted():
    svc = AudioService(run=FakeRunner(["Volume: 0.45 [MUTED]\n", "Volume: 0.30\n"]))
    vol, muted, _ = svc.get()
    assert vol == 45 and muted is True


def test_get_falls_back_to_zero_on_garbage():
    svc = AudioService(run=FakeRunner(["", "nonsense"]))
    assert svc.get() == (0, False, 0)


def test_set_volume_uses_wpctl_percent():
    runner = FakeRunner([])
    svc = AudioService(run=runner)
    svc.set_volume(45)
    assert runner.calls == [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "45%"]]


def test_toggle_mute_and_set_mic_volume():
    runner = FakeRunner([])
    svc = AudioService(run=runner)
    svc.toggle_mute()
    svc.set_mic_volume(30)
    assert runner.calls[0] == ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
    assert runner.calls[1] == ["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", "30%"]
