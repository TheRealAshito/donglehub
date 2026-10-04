# Caelestia Shell (Quickshell) integration

Adds a sidebar card with live battery + charging state for both devices:

    headphones  87%  [bolt] [battery icon]
    mouse       42%         [battery icon]

Two files, both following Caelestia's own conventions (`qs.components`,
`qs.services`, `Tokens`, `Colours`, `Icons.getBatteryIcon`):

- `DongleHub.qml`      — service singleton; runs `donglehub watch --json` and
                         exposes `headsetBattery/headsetCharging/headsetConnected`
                         and the `mouse*` equivalents (battery is 0-100, or -1
                         when unknown).
- `DeviceBatteries.qml` — the card widget.

## Install

Caelestia is meant to be customised from a checkout at
`$XDG_CONFIG_HOME/quickshell/caelestia` (see Caelestia's "manual installation"
section — do not edit files owned by the AUR package). Copy the files in:

    cp DongleHub.qml      ~/.config/quickshell/caelestia/services/
    cp DeviceBatteries.qml ~/.config/quickshell/caelestia/modules/sidebar/

No `qmldir` registration is needed — Quickshell exports directory modules
automatically (same as the other services).

Then wire the card into `modules/sidebar/Content.qml`. Add this block to the
`ColumnLayout` (before the existing `StyledRect` that hosts `NotifDock`):

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

Reload Quickshell and the sidebar shows both batteries.

## Where else it can go

`DeviceBatteries` is layout-agnostic — drop it in `modules/dashboard/dash/`
next to `SmallWeather.qml`, or in a bar popout, wherever you prefer. If you
put it outside `modules/sidebar/`, import it relative to your module dir.

## Troubleshooting

- `DongleHub: bad snapshot` warnings or permanent "Disconnected": Quickshell
  may not see `~/.local/bin` on PATH. Set the absolute path in the
  `command:` lines of `DongleHub.qml`, e.g.
  `["/home/<you>/.local/bin/donglehub", "watch", "--interval", "30", "--json"]`.
- Everything says `—`/unknown: run `donglehub status --json` in a terminal to
  check the CLI side, and make sure the udev rules are installed (see the top
  level README) so device access works without root.
- The status updates every 30 s (`--interval` in `DongleHub.qml`).
