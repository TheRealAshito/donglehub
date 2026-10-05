# Caelestia Shell integration (Hyprland / Quickshell)

Battery + charging status for the MCHOSE V9 PRO headset and AttackShark X11
mouse, shown as status icons in the Caelestia bar (the vertical pill on the
side of your screen):

    [headphones] 87%
    [mouse]      42%          <- hover: "AttackShark X11: 42% (charging)"

Three files, all following Caelestia's own conventions (`qs.components`,
`qs.services`, `Tokens`, `Colours`):

- `DongleHub.qml`       — service singleton; runs `donglehub watch --json` and
                          exposes `headsetBattery/headsetCharging/headsetConnected`
                          and the `mouse*` equivalents (battery is 0-100, or -1
                          when unknown).
- `DongleHubStatus.qml` — the bar status entry (two device rows + tooltips).
- `DeviceBatteries.qml` — optional sidebar card if you prefer the dashboard.

## How the dots actually work

Caelestia's "dotfiles" for the bar are **Quickshell QML**, not Hyprland config —
Hyprland (`~/.config/hypr/`) is only the compositor; the bar, sidebar and
dashboard are QML in the shell checkout. There are two layers:

1. **QML source** — the shell itself. To customise it you need a checkout you
   own at `$XDG_CONFIG_HOME/quickshell/caelestia` (Caelestia's "manual
   installation" section; the `INSTALL_QSCONFDIR` cmake flag installs the shell
   there "for easy local changes"). Do **not** edit files owned by the
   `caelestia-shell` AUR package — updates will overwrite them. With the
   home-manager module, this is all declarative in your nix dots instead.
2. **Typed settings** — `~/.config/caelestia/shell.json` (created manually,
   partial OK, omitted options use defaults). This is where bar entries are
   ordered/enabled, including the status-icons list.

So implementing this = drop two QML files into the shell checkout, add one
`DelegateChoice` in `StatusIcons.qml`, and add one entry in `shell.json`.

## Install

### 1. Copy the files into your shell checkout

    cp DongleHub.qml       ~/.config/quickshell/caelestia/services/
    cp DongleHubStatus.qml ~/.config/quickshell/caelestia/modules/bar/components/status/

No `qmldir` registration is needed — Quickshell exports directory modules
automatically (same as the other services/status components).

### 2. Wire the delegate in `StatusIcons.qml`

Edit `~/.config/quickshell/caelestia/modules/bar/components/StatusIcons.qml`
and add this `DelegateChoice` inside the `DelegateChooser` (e.g. right after
the `roleValue: "battery"` one):

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

(The file already imports `qs.modules.bar.components.status`, so no new import
is needed.)

### 3. Enable the entry in `~/.config/caelestia/shell.json`

The status icon list is `bar.statusIcons`: an array of `{id, enabled}` in
display order. **The list replaces the default**, so include everything you
want visible — this is the default list plus our entry at the top:

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

(Defaults you may also want: `audio`, `microphone`, `kbLayout` — all disabled
by default.) Afterwards the Nexus dashboard's *Status icons* settings page
lists "Donglehub" like any other entry, so you can reorder or toggle it from
the GUI without touching JSON again.

### 4. Reload

Reload Quickshell (your Caelestia reload keybind, or restart the shell).
`shell.json` changes hot-reload; the QML files need the reload.

## Troubleshooting

- `DongleHub: bad snapshot` warnings or permanent "—": Quickshell may not see
  `~/.local/bin` on PATH. Set the absolute path in the `command:` lines of
  `DongleHub.qml`, e.g.
  `["/home/<you>/.local/bin/donglehub", "watch", "--interval", "30", "--json"]`.
- Icons stuck at "—": run `donglehub status --json` in a terminal to check the
  CLI side, and make sure the udev rules are installed (top-level README) so
  device access works without root.
- Data refreshes every 30 s (`--interval` in `DongleHub.qml`).
- After `caelestia update` / `git pull` of the shell, re-apply step 2 if
  `StatusIcons.qml` was overwritten.

## Alternative: sidebar / dashboard card

Prefer a bigger card over compact status icons? `DeviceBatteries.qml` is a
standalone widget using the same service. Copy it with:

    cp DeviceBatteries.qml ~/.config/quickshell/caelestia/modules/sidebar/

and add to `modules/sidebar/Content.qml` (inside the `ColumnLayout`, before
the `NotifDock` block):

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
