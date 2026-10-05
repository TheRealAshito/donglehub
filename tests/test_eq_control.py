"""Tests for live EQ control over pw-cli / pw-dump (fake runner)."""
import json

from donglehub.eq import control
from donglehub.eq.model import EqSettings


class FakeRunner:
    def __init__(self, outputs=()):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        out = self.outputs.pop(0) if self.outputs else ""
        return out


PW_DUMP = json.dumps([
    {"id": 71, "type": "PipeWire:Interface:Node",
     "info": {"props": {"node.name": "donglehub.eq", "media.class": "Audio/Sink"}}},
    {"id": 99, "type": "PipeWire:Interface:Node",
     "info": {"props": {"node.name": "other"}}},
])


def test_find_node_id_by_name():
    runner = FakeRunner([PW_DUMP])
    ctl = control.EqController(run=runner)
    assert ctl.node_id("donglehub.eq") == 71
    assert runner.calls == [["pw-dump"]]


def test_find_node_id_missing_returns_none():
    ctl = control.EqController(run=FakeRunner([PW_DUMP]))
    assert ctl.node_id("nope") is None


def test_set_band_issues_pw_cli_set_param():
    runner = FakeRunner()
    ctl = control.EqController(run=runner, node=71)
    ctl.set_band(2, 2.5, EqSettings())
    payload = json.dumps({"params": ["band3:Gain", 2.5]})
    assert runner.calls == [["pw-cli", "s", "71", "Props", payload]]


def test_set_band_surround_updates_both_channels():
    runner = FakeRunner()
    ctl = control.EqController(run=runner, node=71)
    ctl.set_band(0, -1.5, EqSettings(mode="surround", hrir="/x/h.wav"))
    keys = [json.loads(c[-1])["params"][0] for c in runner.calls]
    assert keys == ["band1L:Gain", "band1R:Gain"]


def test_set_preamp_uses_preamp_key():
    runner = FakeRunner()
    ctl = control.EqController(run=runner, node=71)
    ctl.set_preamp(3.0, EqSettings())
    payload = json.dumps({"params": ["preamp:Gain", 3.0]})
    assert runner.calls == [["pw-cli", "s", "71", "Props", payload]]


def test_service_lifecycle_commands():
    runner = FakeRunner()
    ctl = control.EqController(run=runner, node=71)
    ctl.enable()
    ctl.disable()
    ctl.restart()
    assert runner.calls[0] == ["systemctl", "--user", "enable", "--now", "donglehub-eq.service"]
    assert runner.calls[1] == ["systemctl", "--user", "disable", "--now", "donglehub-eq.service"]
    assert runner.calls[2] == ["systemctl", "--user", "restart", "donglehub-eq.service"]


def test_apply_updates_changed_bands_only():
    runner = FakeRunner()
    ctl = control.EqController(run=runner, node=71)
    current = {f"band{i}:Gain": 0.0 for i in range(1, 11)}
    current["preamp:Gain"] = 0.0
    s = EqSettings(gains=[3.0] + [0.0] * 9, preamp=1.0)
    ctl.apply(s, current)
    keys = [json.loads(c[-1])["params"][0] for c in runner.calls]
    assert keys == ["band1:Gain", "preamp:Gain"]
