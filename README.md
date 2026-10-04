# DongleHub

One app for both wireless peripherals: **MCHOSE V9 PRO** headset (2.4G dongle)
and **AttackShark X11** mouse. Shows battery level and charging state for each,
keeps every feature the two upstream apps have (headset EQ profiles, firmware,
volume/mic sync; mouse polling rate, LED modes, angle snap, ripple, key
response, sleep timers), and — the point of the project — feeds the data to a
**Caelestia Shell (Quickshell) sidebar widget** so the batteries are always on
screen.

Unofficial and community-made. No vendor code involved; the USB/HID protocols
were reverse-engineered from public projects:

- MCHOSE V9 PRO protocol: [JoaoKSS/MCHOSE_v9_PRO_Controller](https://github.com/JoaoKSS/MCHOSE_v9_PRO_Controller)
- AttackShark X11 protocol: [iago-fragnan/attack-shark-x11-linux](https://github.com/iago-fragnan/attack-shark-x11-linux),
  further RE by [HarukaYamamoto0/attack-shark-x11-driver](https://github.com/HarukaYamamoto0/attack-shark-x11-driver)

## Features

Device monitoring (GUI, CLI, and the sidebar widget):
- battery % for headset and mouse
- charging / charged / on-battery state ("Charging" when the mouse sits on its
  dock or runs over USB, headset via status byte + charge-trend heuristic)
- connection mode (2.4G dongle / USB cable)
- system tray icon with both batteries as tooltip

Headset controls (from MCHOSE_v9_PRO_Controller):
- hardware EQ profiles: Game 1 / Game 2 / Music (2.4G only)
- firmware versions (dongle + headset)
- volume / mute / microphone sliders synced with the system mixer (PipeWire)

Mouse controls (from attack-shark-x11-linux):
- LED modes: Disabled / Breathing / Neon / Color Breathing
- polling rate: 125 / 250 / 500 / 1000 Hz
- angle snap, ripple control, key response, sleep + deep sleep timers

Shell integration:
- `donglehub watch --json` streams JSON snapshots (one line per poll)
- ready-made QML service + sidebar card for Caelestia Shell — see
  [shell/caelestia/README.md](shell/caelestia/README.md)

## Install (CachyOS / Arch, also Debian-based)

    ./install.sh

It installs the pacman packages (python, python-pyqt6, python-pyusb, hidapi,
libusb, wireplumber), the udev rules, and `donglehub` / `donglehub-gui` into
`~/.local/bin` via a small venv that reuses the distro's PyQt6/pyusb.

Manual equivalent on CachyOS/Arch:

    sudo pacman -S --needed python python-pyqt6 python-pyusb hidapi libusb wireplumber
    sudo cp udev/90-donglehub.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger
    python3 -m venv --system-site-packages ~/donglehub-venv
    ~/donglehub-venv/bin/pip install .
    ln -s ~/donglehub-venv/bin/donglehub ~/.local/bin/donglehub

Prefer real packages? `packaging/arch/PKGBUILD` builds one with makepkg
(see the comment inside), and `packaging/donglehub.desktop` adds a menu entry.

The udev rules matter: without them both devices are root-only and the hub
(and the sidebar widget) will report "disconnected".

## Usage

    donglehub status            # both devices, one line each
    donglehub status --json     # machine-readable snapshot
    donglehub watch --json      # stream snapshots (used by the shell widget)
    donglehub gui               # desktop app (or: donglehub-gui, or just
                                # `donglehub` on a desktop session)

    donglehub set-eq music      # headset EQ: game1 | game2 | music
    donglehub set-mouse --color 1 --polling 1000 --angle-snap on \
                        --ripple off --key-resp 8 --sleep 5 --deep-sleep 10

    donglehub probe headset     # raw protocol probe (see below)
    donglehub probe mouse

`status` output looks like:

    Headset  MCHOSE V9 PRO       87%  charging     [2.4G]  eq: Music
    Mouse    AttackShark X11     42%  on battery   [2.4G]

## Charging-state semantics (please read)

- Mouse: solid. Wireless + no battery packet = on the charging dock; a
  `0x1d57:0xfa55` USB connection = charging over cable; battery packets carry
  the exact percentage. "Charged" at 100%.
- Headset: the reply carries a battery byte and a vendor status byte whose
  meaning is not publicly documented. DongleHub therefore derives the state
  from (1) a user-calibrated status map, (2) 100% = charged, (3) charge trend
  (percentage rising = charging). Calibrate once with real hardware:

      donglehub probe headset        # watch status_byte while charging
      donglehub probe headset        # ...and while discharging

  then map the observed values in `~/.config/donglehub/config.json`:

      {"headset_status_map": {"1": "charging", "2": "full"}}

  (only needed if the trend heuristic isn't accurate enough for you).

## Development

    python3 -m pytest tests/ -q     # 70 tests, GUI smoke tests run offscreen

Layout: `donglehub/protocols/` are pure packet encoders/decoders,
`backends/` wrap libhidapi (ctypes) and libusb (pyusb), `devices/` drive the
two peripherals, `hub.py` polls behind a cross-process lock, `cli.py` and
`gui.py` are the front ends. See `tests/` for the packet examples.

## Known limits

- The headset's status byte is interpreted heuristically (see above).
- Mouse key-response / sleep / deep-sleep values are validated and stored in
  the reports exactly like upstream does; upstream v2.0.1 doesn't actually
  encode them into the packets (its `buildColorReport` ignores them) — kept
  identical here until someone RE's the real layout.
- EQ profile switching works over 2.4G only (the firmware ignores it over
  Bluetooth). Bluetooth battery reading is not implemented (file an issue if
  you need it; BlueZ exposes it over `org.bluez.Battery1`).
