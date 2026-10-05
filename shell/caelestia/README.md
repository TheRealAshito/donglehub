# Caelestia Shell integration (Hyprland / Quickshell)

Battery + charging status for the MCHOSE V9 PRO headset and AttackShark X11
mouse as status icons in the Caelestia bar (the vertical pill on the side):

    [headphones] 87%
    [mouse]      42%          <- hover: "AttackShark X11: 42% (charging)"

## Quick start

    donglehub caelestia install     # no sudo; only touches your home dir
    # then reload Quickshell (your Caelestia reload keybind)

    donglehub caelestia status      # see what is installed where

After every `caelestia update`, run `donglehub caelestia install` again to
re-sync (it is idempotent and takes a second).

## How your Caelestia setup is laid out

With the full Caelestia dotfiles, the pieces live in different places:

- `~/.config/hypr/` — the generated Hyprland config (`hyprland.lua`, `scheme/`,
  `utils/`). **Never edit these**; updates overwrite them and you get
  conflicts. Personal Hyprland changes go in `~/.config/caelestia/hypr-user.lua`
  (or `hypr-user.conf`, `hypr-vars.lua`).
- `~/.config/caelestia/` — **your** files: `shell.json` (shell settings,
  including the bar/status-icon list), `monitors/` (per-monitor overrides),
  `hypr-user.*`, `user-config.fish`.
- `~/.config/uwsm/` — session environment for uwsm-launched Hyprland.
- The shell's **QML source is not in your config at all** — it ships with the
  `caelestia-shell` package system-wide (e.g. `/usr/share/quickshell/caelestia`).
  That is why there is no `~/.config/quickshell`: Quickshell loads the packaged
  tree directly.

So bar changes are two-layered: QML (rendering) + `shell.json` (which status
icons exist and in what order).

## What `donglehub caelestia install` does

1. **overlay mode (default)** — mirrors the installed shell tree into
   `~/.config/quickshell/caelestia` (Quickshell prefers this user copy over the
   system one), drops `DongleHub.qml` and `DongleHubStatus.qml` in, and wires
   the delegate in `StatusIcons.qml`. Nothing outside your home directory is
   touched and the packaged install stays pristine; the trade-off is re-running
   the command after `caelestia update` to pick up shell changes.
2. **`--mode system`** — patches the installed tree in place instead (needs
   write access, e.g. `sudo donglehub caelestia install --mode system`).
   Package updates overwrite the patch, so re-run after updates there too.
3. Either way it merges `{ "id": "donglehub", "enabled": true }` into
   `bar.statusIcons` in `~/.config/caelestia/shell.json` (a backup is written
   to `shell.json.bak`; your other options and entries are preserved).

`--dry-run` shows what would happen; `--shell-root PATH` overrides auto-detection.

## Manual steps (what the installer automates)

Files (shipped in `donglehub/assets/caelestia/`):

- `DongleHub.qml`       — service singleton; runs `donglehub watch --json` and
                          exposes `headsetBattery/headsetCharging/headsetConnected`
                          and the `mouse*` equivalents (battery 0-100, -1 unknown).
- `DongleHubStatus.qml` — the bar status entry (two device rows + tooltips).
- `DeviceBatteries.qml` — optional sidebar/dashboard card.

Place the first two at `services/DongleHub.qml` and
`modules/bar/components/status/DongleHubStatus.qml` in the active shell tree,
then add this `DelegateChoice` inside the `DelegateChooser` in
`modules/bar/components/StatusIcons.qml` (e.g. after `roleValue: "battery"`):

```qml
                DelegateChoice {
                    roleValue: "donglehub"
                    delegate: EntryWrapper {
                        margin: Tokens.spacing.extraSmall / 2

                        DongleHubStatus {
                            colour: root.colour
                        }
                    }
                }
```

Then enable the entry in `~/.config/caelestia/shell.json` — `bar.statusIcons`
is an array of `{id, enabled}` in display order that **replaces** the default
list, so include everything you want (this is the default list + ours first):

```json
{
    "bar": {
        "statusIcons": [
            { "id": "donglehub", "enabled": true },
            { "id": "lockStatus", "enabled": true },
            { "id": "network", "enabled": true },
            { "id": "bluetooth", "enabled": true },
            { "id": "battery", "enabled": true }
        ]
    }
}
```

(Other defaults you can add: `audio`, `microphone`, `kbLayout` — off by
default.) Afterwards the Nexus dashboard's *Status icons* settings page lists
"Donglehub" like a built-in entry, so you can reorder or toggle it from the
GUI without touching JSON again.

## Troubleshooting

- Icons missing after a reload: `donglehub caelestia status` should report
  `delegate_wired True` and `shell_json_entry True`; Quickshell logs any QML
  errors with file and line.
- Permanent "—"/unknown: run `donglehub status --json` to check the CLI side,
  and make sure the udev rules are installed (top-level README) so device
  access works without root.
- Data refreshes every 30 s (`--interval` in `DongleHub.qml`).
- Quickshell prefers the user tree over the packaged one — to go back to the
  pure packaged shell, delete `~/.config/quickshell/caelestia`.
- If `caelestia update` moves things and auto-detection misses the shell tree,
  pass `--shell-root` explicitly.

## Alternative: sidebar / dashboard card

Prefer a bigger card over compact status icons? The installer already places
`DeviceBatteries.qml` at `modules/sidebar/DeviceBatteries.qml`; add to
`modules/sidebar/Content.qml` (inside the `ColumnLayout`, before the
`NotifDock` block):

```qml
        StyledRect {
            Layout.fillWidth: true
            implicitHeight: batteries.implicitHeight + Tokens.padding.medium * 2

            radius: Tokens.rounding.large
            color: Colours.tPalette.m3surfaceContainerLow

            DeviceBatteries {
                id: batteries

                anchors.centerIn: parent
                width: parent.width - Tokens.padding.medium * 2
            }
        }
```

The widget is layout-agnostic — `modules/dashboard/dash/` works too.
