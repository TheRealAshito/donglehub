"""Tests for the EQ settings store and presets (~/.config/donglehub/eq.json)."""
from donglehub.eq import store
from donglehub.eq.model import EqSettings


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    s = EqSettings(gains=[1.5, -3.0] + [0.0] * 8, preamp=2.0)
    store.save_active(s)
    loaded = store.load_active()
    assert loaded == s


def test_missing_file_returns_flat_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert store.load_active() == EqSettings()
    assert store.list_presets() == []


def test_preset_save_list_load_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    s = EqSettings(gains=[4.0] + [0.0] * 9)
    store.save_preset("bass", s)
    assert store.list_presets() == ["bass"]
    assert store.load_preset("bass") == s
    store.delete_preset("bass")
    assert store.list_presets() == []


def test_load_unknown_preset_raises_keyerror(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    try:
        store.load_preset("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
