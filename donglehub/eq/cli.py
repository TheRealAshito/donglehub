"""`donglehub eq` subcommand: system-wide PipeWire EQ + HeSuVi virtual surround."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import render, store
from .control import EqController
from .model import BANDS, EqSettings


def add_parser(sub) -> argparse.ArgumentParser:
    p = sub.add_parser(
        "eq",
        help="system-wide EQ and virtual surround (PipeWire filter-chain)",
    )
    es = p.add_subparsers(dest="eq_cmd", required=True)

    st = es.add_parser("status", help="show current EQ state")
    st.add_argument("--json", action="store_true")

    es.add_parser("install", help="write config + user service and enable it")
    es.add_parser("on", help="enable the EQ sink")
    es.add_parser("off", help="disable the EQ sink")
    es.add_parser("restart", help="restart the EQ sink (after config changes)")

    s = es.add_parser("set", help="set a band gain: `set 3 2.5` (band 1-10) or `set preamp -3`")
    s.add_argument("target")
    s.add_argument("value")

    s = es.add_parser("preamp", help="set preamp gain in dB")
    s.add_argument("value")

    pr = es.add_parser("preset", help="list presets, or load one")
    pr.add_argument("name", nargs="?")

    sv = es.add_parser("save", help="save current settings as a preset")
    sv.add_argument("name")

    dl = es.add_parser("delete", help="delete a preset")
    dl.add_argument("name")

    es.add_parser("flat", help="reset all bands to 0 dB")

    su = es.add_parser("surround", help="toggle 7.1 HeSuVi virtual surround")
    su.add_argument("state", choices=["on", "off"])

    hr = es.add_parser("hrir", help="set the HeSuVi HRIR wav path")
    hr.add_argument("path")

    return p


def default_controller() -> EqController:
    return EqController()


def dispatch(args, controller: Optional[EqController] = None) -> int:
    ctl = controller or default_controller()
    settings = store.load_active()
    cmd = args.eq_cmd

    if cmd == "status":
        payload = {
            "gains": settings.gains,
            "preamp": settings.preamp,
            "mode": settings.mode,
            "hrir": settings.hrir,
            "presets": store.list_presets(),
            "bands": [b.label for b in BANDS],
        }
        if args.json:
            print(json.dumps(payload))
        else:
            state = "surround" if settings.mode == "surround" else "EQ"
            print(f"mode:    {state}" + (f"  hrir: {settings.hrir}" if settings.hrir else ""))
            print(f"preamp:  {settings.preamp:+.1f} dB")
            for band, gain in zip(BANDS, settings.gains):
                print(f"  {band.label:>7}  {gain:+.1f} dB")
            if payload["presets"]:
                print("presets: " + ", ".join(payload["presets"]))
        return 0

    if cmd == "install":
        print(ctl.install(settings))
        return 0

    if cmd in ("on", "off", "restart"):
        getattr(ctl, {"on": "enable", "off": "disable", "restart": "restart"}[cmd])()
        print(f"EQ {cmd == 'on' and 'enabled' or (cmd == 'off' and 'disabled') or 'restarted'}")
        return 0

    if cmd in ("set", "preamp"):
        target = "preamp" if cmd == "preamp" else args.target
        try:
            value = float(args.value)
        except ValueError:
            print(f"invalid dB value {args.value!r}", file=sys.stderr)
            return 2
        if target == "preamp":
            try:
                settings.preamp = value
                EqSettings(**{**settings.to_dict()})  # re-validate
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 2
            store.save_active(settings)
            ctl.set_preamp(value, settings)
            print(f"preamp: {value:+.1f} dB")
            return 0
        try:
            index = int(target) - 1
        except ValueError:
            print(f"target must be 1..{len(BANDS)} or 'preamp', got {target!r}", file=sys.stderr)
            return 2
        if not 0 <= index < len(BANDS):
            print(f"band must be 1..{len(BANDS)}", file=sys.stderr)
            return 2
        settings.gains[index] = value
        try:
            EqSettings(**{**settings.to_dict()})
        except ValueError as e:
            print(str(e), file=sys.stderr)
            settings.gains[index] = 0.0
            return 2
        store.save_active(settings)
        ctl.set_band(index, value, settings)
        print(f"band {index + 1} ({BANDS[index].label}): {value:+.1f} dB")
        return 0

    if cmd == "flat":
        settings.gains = [0.0] * len(BANDS)
        settings.preamp = 0.0
        store.save_active(settings)
        ctl.apply(settings, None)
        print("flat (0 dB)")
        return 0

    if cmd == "save":
        store.save_preset(args.name, settings)
        print(f"saved preset {args.name!r}")
        return 0

    if cmd == "delete":
        store.delete_preset(args.name)
        print(f"deleted preset {args.name!r}")
        return 0

    if cmd == "preset":
        if not args.name:
            for name in store.list_presets():
                print(name)
            return 0
        try:
            settings = store.load_preset(args.name)
        except KeyError:
            print(f"no such preset {args.name!r}", file=sys.stderr)
            return 2
        store.save_active(settings)
        ctl.apply(settings, None)
        ctl.restart()
        print(f"loaded preset {args.name!r}")
        return 0

    if cmd == "hrir":
        settings.hrir = args.path
        store.save_active(settings)
        print(f"hrir: {args.path}")
        return 0

    if cmd == "surround":
        if args.state == "on":
            if not settings.hrir:
                print(
                    "no HRIR file set — run `donglehub eq hrir /path/to/hesuvi.wav` first "
                    "(HeSuVi's 14-channel wav, or any HRIR pack)",
                    file=sys.stderr,
                )
                return 2
            settings.mode = "surround"
        else:
            settings.mode = "eq"
        store.save_active(settings)
        ctl.restart()
        print(f"virtual surround {'enabled' if args.state == 'on' else 'disabled'}")
        return 0

    return 2
