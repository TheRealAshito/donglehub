"""Caelestia Shell (Quickshell) dotfiles integration installer.

On the full Caelestia dotfiles setup the shell QML ships with the
`caelestia-shell` package system-wide (e.g. /usr/share/quickshell/caelestia),
while user settings live in ~/.config/caelestia (shell.json, hypr-user.lua,
...). There is no per-file QML overlay, so this module offers two ways to
install the DongleHub QML:

- overlay (default): mirror the system shell tree into
  $XDG_CONFIG_HOME/quickshell/caelestia (which Quickshell prefers over the
  system copy), then install + wire our files there. Nothing outside your
  home directory is touched; re-run after `caelestia update` to re-sync.
- system: patch the system tree in place (needs write access).

It also merges the status-icons entry into ~/.config/caelestia/shell.json.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple

DELEGATE_BLOCK = """\
                DelegateChoice {
                    roleValue: "donglehub"
                    delegate: EntryWrapper {
                        margin: Tokens.spacing.extraSmall / 2

                        DongleHubStatus {
                            colour: root.colour
                        }
                    }
                }"""

# Defaults from the shell's plugin/src/Caelestia/Config/barconfig.hpp.
DEFAULT_STATUS_ICONS = [
    {"id": "lockStatus", "enabled": True},
    {"id": "audio", "enabled": False},
    {"id": "microphone", "enabled": False},
    {"id": "kbLayout", "enabled": False},
    {"id": "network", "enabled": True},
    {"id": "bluetooth", "enabled": True},
    {"id": "battery", "enabled": True},
]

SHELL_ROOT_CANDIDATES = (
    "/usr/share/quickshell/caelestia",
    "/usr/local/share/quickshell/caelestia",
    "/usr/lib/quickshell/caelestia",
)


def assets_dir() -> Path:
    return Path(__file__).parent / "assets" / "caelestia"


def quickshell_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "quickshell"


def caelestia_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "caelestia"


def find_shell_root(explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if (p / "modules").is_dir() else None
    for candidate in SHELL_ROOT_CANDIDATES:
        p = Path(candidate)
        if (p / "modules").is_dir():
            return p
    return None


def patch_status_icons(text: str) -> Tuple[str, bool]:
    """Insert the donglehub DelegateChoice into StatusIcons.qml content."""
    if 'roleValue: "donglehub"' in text:
        return text, False

    insert_at = None
    anchor = text.find('roleValue: "battery"')
    if anchor != -1:
        start = text.rfind("DelegateChoice {", 0, anchor)
        if start != -1:
            depth = 0
            for k in range(text.index("{", start), len(text)):
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        insert_at = k + 1
                        break
    if insert_at is None:
        first = text.find("DelegateChoice {")
        if first == -1:
            return text, False
        insert_at = first

    out = text[:insert_at] + "\n" + DELEGATE_BLOCK + text[insert_at:]
    return out, True


def merge_shell_json() -> Path:
    """Add the donglehub status entry to ~/.config/caelestia/shell.json."""
    path = caelestia_config_dir() / "shell.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            data = {}
        shutil.copy(path, path.with_name("shell.json.bak"))

    bar = data.setdefault("bar", {})
    current = bar.get("statusIcons")
    if not isinstance(current, list) or not current:
        current = [dict(e) for e in DEFAULT_STATUS_ICONS]
    entries = [e for e in current if not (isinstance(e, dict) and e.get("id") == "donglehub")]
    entries.insert(0, {"id": "donglehub", "enabled": True})
    bar["statusIcons"] = entries

    caelestia_config_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4) + "\n")
    return path


def install(mode: str = "overlay", shell_root: Optional[Path] = None,
            dry_run: bool = False) -> dict:
    root = find_shell_root(shell_root)
    if root is None:
        raise FileNotFoundError(
            "could not find the Caelestia shell QML tree "
            "(looked in %s); pass --shell-root" % ", ".join(SHELL_ROOT_CANDIDATES)
        )

    if mode == "overlay":
        target = quickshell_config_dir() / "caelestia"
    elif mode == "system":
        target = root
    else:
        raise ValueError(f"mode must be 'overlay' or 'system', got {mode!r}")

    report = {"mode": mode, "root": str(root), "target": str(target), "actions": []}
    if dry_run:
        report["actions"].append("dry run: nothing written")
        return report

    if mode == "overlay":
        if not target.exists():
            shutil.copytree(root, target)
            report["actions"].append(f"mirrored shell tree {root} -> {target}")
        else:
            for src in root.rglob("*"):
                rel = src.relative_to(root)
                dst = target / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            report["actions"].append(f"synced shell tree {root} -> {target}")

    for name, rel in (
        ("DongleHub.qml", "services/DongleHub.qml"),
        ("DongleHubStatus.qml", "modules/bar/components/status/DongleHubStatus.qml"),
        ("DeviceBatteries.qml", "modules/sidebar/DeviceBatteries.qml"),
    ):
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets_dir() / name, dst)
        report["actions"].append(f"wrote {dst}")

    status_icons = target / "modules" / "bar" / "components" / "StatusIcons.qml"
    if status_icons.exists():
        new_text, changed = patch_status_icons(status_icons.read_text())
        if changed:
            status_icons.write_text(new_text)
            report["actions"].append(f"patched {status_icons}")
        else:
            report["actions"].append(f"already wired: {status_icons}")
    else:
        report["actions"].append(f"WARNING: {status_icons} not found; delegate not wired")

    cfg = merge_shell_json()
    report["actions"].append(f"updated {cfg}")
    return report


def status(shell_root: Optional[Path] = None) -> dict:
    root = find_shell_root(shell_root)
    overlay = quickshell_config_dir() / "caelestia"
    status_icons = overlay / "modules" / "bar" / "components" / "StatusIcons.qml"
    cfg_path = caelestia_config_dir() / "shell.json"
    in_config = False
    if cfg_path.exists():
        try:
            entries = json.loads(cfg_path.read_text()).get("bar", {}).get("statusIcons", [])
            in_config = any(isinstance(e, dict) and e.get("id") == "donglehub" for e in entries)
        except ValueError:
            pass
    return {
        "system_root": str(root) if root else None,
        "overlay": str(overlay) if overlay.exists() else None,
        "delegate_wired": status_icons.exists()
        and 'roleValue: "donglehub"' in status_icons.read_text(),
        "shell_json_entry": in_config,
    }
