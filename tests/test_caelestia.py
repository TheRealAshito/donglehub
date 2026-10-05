"""Tests for the Caelestia dotfiles installer (QML placement + config merge)."""
import json

from donglehub import caelestia

STATUS_ICONS_QML = """\
        Repeater {
            model: ScriptModel {
                values: root.Config.bar.statusIcons.values.filter(e => e.enabled)
            }

            DelegateChooser {
                role: "id"

                DelegateChoice {
                    roleValue: "network"
                    delegate: EntryWrapper {
                        MaterialIcon { text: "wifi" }
                    }
                }
                DelegateChoice {
                    roleValue: "battery"
                    delegate: EntryWrapper {
                        BatteryStatus {
                            colour: root.colour
                        }
                    }
                }
            }
        }
"""


def test_patch_inserts_delegate_after_battery():
    out, changed = caelestia.patch_status_icons(STATUS_ICONS_QML)
    assert changed is True
    assert 'roleValue: "donglehub"' in out
    assert out.index('roleValue: "battery"') < out.index('roleValue: "donglehub"')
    assert out.count("DelegateChoice {") == STATUS_ICONS_QML.count("DelegateChoice {") + 1
    # battery block is preserved untouched
    assert "BatteryStatus" in out


def test_patch_is_idempotent():
    once, _ = caelestia.patch_status_icons(STATUS_ICONS_QML)
    twice, changed = caelestia.patch_status_icons(once)
    assert changed is False
    assert twice == once
    assert twice.count('roleValue: "donglehub"') == 1


def test_patch_inserts_block_with_correct_shape():
    out, _ = caelestia.patch_status_icons(STATUS_ICONS_QML)
    assert "DongleHubStatus {" in out
    assert "colour: root.colour" in out


def test_patch_without_battery_anchor_inserts_first():
    text = """\
            DelegateChooser {
                role: "id"

                DelegateChoice {
                    roleValue: "network"
                    delegate: EntryWrapper {
                        MaterialIcon { text: "wifi" }
                    }
                }
            }
"""
    out, changed = caelestia.patch_status_icons(text)
    assert changed is True
    assert out.index('roleValue: "donglehub"') < out.index('roleValue: "network"')


def test_merge_shell_json_creates_defaults_with_entry_first(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = caelestia.merge_shell_json()
    data = json.loads(path.read_text())
    icons = data["bar"]["statusIcons"]
    assert icons[0] == {"id": "donglehub", "enabled": True}
    ids = [e["id"] for e in icons]
    assert "battery" in ids and "network" in ids and "lockStatus" in ids


def test_merge_shell_json_prepends_to_existing_list_without_dupes(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "caelestia"
    cfg.mkdir()
    (cfg / "shell.json").write_text(json.dumps({
        "bar": {"statusIcons": [
            {"id": "battery", "enabled": True},
            {"id": "donglehub", "enabled": False},
        ]}
    }))
    path = caelestia.merge_shell_json()
    data = json.loads(path.read_text())
    icons = data["bar"]["statusIcons"]
    ids = [e["id"] for e in icons]
    assert ids.count("donglehub") == 1
    assert ids[0] == "donglehub"
    assert data["bar"]["statusIcons"][0]["enabled"] is True
    assert "battery" in ids


def test_merge_shell_json_preserves_other_options(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "caelestia"
    cfg.mkdir()
    (cfg / "shell.json").write_text(json.dumps({"bar": {"persistent": False}}))
    path = caelestia.merge_shell_json()
    data = json.loads(path.read_text())
    assert data["bar"]["persistent"] is False


def make_fake_shell_root(tmp_path):
    root = tmp_path / "system" / "quickshell" / "caelestia"
    (root / "services").mkdir(parents=True)
    (root / "modules" / "bar" / "components" / "status").mkdir(parents=True)
    (root / "modules" / "bar" / "components" / "StatusIcons.qml").write_text(STATUS_ICONS_QML)
    (root / "services" / "Colours.qml").write_text("// colours")
    return root


def test_install_overlay_copies_tree_and_patches(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    root = make_fake_shell_root(tmp_path)
    report = caelestia.install(mode="overlay", shell_root=root)
    overlay = tmp_path / "config" / "quickshell" / "caelestia"
    assert (overlay / "services" / "DongleHub.qml").exists()
    assert (overlay / "services" / "Colours.qml").exists()  # full tree mirrored
    assert (overlay / "modules" / "bar" / "components" / "status" / "DongleHubStatus.qml").exists()
    patched = (overlay / "modules" / "bar" / "components" / "StatusIcons.qml").read_text()
    assert 'roleValue: "donglehub"' in patched
    assert report["target"] == str(overlay)


def test_install_system_mode_patches_in_place(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = make_fake_shell_root(tmp_path)
    report = caelestia.install(mode="system", shell_root=root)
    patched = (root / "modules" / "bar" / "components" / "StatusIcons.qml").read_text()
    assert 'roleValue: "donglehub"' in patched
    assert (root / "services" / "DongleHub.qml").exists()
    assert report["target"] == str(root)


def test_install_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    root = make_fake_shell_root(tmp_path)
    caelestia.install(mode="overlay", shell_root=root)
    caelestia.install(mode="overlay", shell_root=root)
    overlay = tmp_path / "config" / "quickshell" / "caelestia"
    patched = (overlay / "modules" / "bar" / "components" / "StatusIcons.qml").read_text()
    assert patched.count('roleValue: "donglehub"') == 1


def test_install_dry_run_touches_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    root = make_fake_shell_root(tmp_path)
    caelestia.install(mode="overlay", shell_root=root, dry_run=True)
    overlay = tmp_path / "config" / "quickshell" / "caelestia"
    assert not overlay.exists()
    assert "donglehub" not in (root / "modules" / "bar" / "components" / "StatusIcons.qml").read_text()
