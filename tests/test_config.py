"""Config loading tests (headset status-byte calibration map)."""
import json

from donglehub import config


def test_load_config_reads_headset_status_map(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "donglehub"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({"headset_status_map": {"1": "charging", "2": "full"}})
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.load_config()
    assert cfg["headset_status_map"] == {1: "charging", 2: "full"}


def test_load_config_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.load_config()
    assert cfg["headset_status_map"] == {}
