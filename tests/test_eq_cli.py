"""CLI tests for `donglehub eq ...` (controller faked)."""
import json

from donglehub import cli
from donglehub.eq.model import EqSettings

from fakes import FakeHub, sample_status


class FakeEqController:
    def __init__(self):
        self.bands = {}
        self.preamps = {}
        self.actions = []
        self.node = 71

    def node_id(self, name):
        return self.node

    def set_band(self, index, gain, settings):
        self.bands[index] = gain

    def set_preamp(self, gain, settings):
        self.preamps["preamp"] = gain

    def apply(self, settings, current=None):
        self.actions.append(("apply", settings))

    def enable(self):
        self.actions.append(("enable",))

    def disable(self):
        self.actions.append(("disable",))

    def restart(self):
        self.actions.append(("restart",))


def make_hub():
    return FakeHub(sample_status("headset"), sample_status("mouse"))


def run_eq(args, controller, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return cli.main(["eq"] + args, hub=make_hub(), eq_controller=controller)


def test_eq_set_band_persists_and_pushes_live(monkeypatch, tmp_path, capsys):
    ctl = FakeEqController()
    rc = run_eq(["set", "3", "2.5"], ctl, monkeypatch, tmp_path)
    assert rc == 0
    assert ctl.bands[2] == 2.5
    out = capsys.readouterr().out
    assert "2.5" in out


def test_eq_set_rejects_bad_band(monkeypatch, tmp_path):
    ctl = FakeEqController()
    assert run_eq(["set", "11", "1.0"], ctl, monkeypatch, tmp_path) != 0
    assert run_eq(["set", "preamp", "x"], ctl, monkeypatch, tmp_path) != 0


def test_eq_preamp_command(monkeypatch, tmp_path):
    ctl = FakeEqController()
    assert run_eq(["preamp", "-3"], ctl, monkeypatch, tmp_path) == 0
    assert ctl.preamps["preamp"] == -3.0


def test_eq_preset_save_and_load(monkeypatch, tmp_path, capsys):
    ctl = FakeEqController()
    run_eq(["set", "1", "4"], ctl, monkeypatch, tmp_path)
    assert run_eq(["save", "bass"], ctl, monkeypatch, tmp_path) == 0
    assert run_eq(["preset", "bass"], ctl, monkeypatch, tmp_path) == 0
    assert run_eq(["preset"], ctl, monkeypatch, tmp_path) == 0
    out = capsys.readouterr().out
    assert "bass" in out


def test_eq_status_json(monkeypatch, tmp_path, capsys):
    ctl = FakeEqController()
    run_eq(["set", "1", "4"], ctl, monkeypatch, tmp_path)
    capsys.readouterr()  # clear output from the setup call
    assert run_eq(["status", "--json"], ctl, monkeypatch, tmp_path) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["gains"][0] == 4.0
    assert data["mode"] == "eq"


def test_eq_surround_and_hrir(monkeypatch, tmp_path, capsys):
    ctl = FakeEqController()
    assert run_eq(["surround", "on"], ctl, monkeypatch, tmp_path) != 0  # no hrir yet
    assert run_eq(["hrir", "/x/hesuvi.wav"], ctl, monkeypatch, tmp_path) == 0
    assert run_eq(["surround", "on"], ctl, monkeypatch, tmp_path) == 0
    data_out = capsys.readouterr().out
    assert "surround" in data_out.lower()


def test_eq_on_off(monkeypatch, tmp_path):
    ctl = FakeEqController()
    assert run_eq(["on"], ctl, monkeypatch, tmp_path) == 0
    assert run_eq(["off"], ctl, monkeypatch, tmp_path) == 0
    assert ("enable",) in ctl.actions and ("disable",) in ctl.actions
