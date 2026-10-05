"""DongleHub command line interface."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .hub import Hub, watch_loop
from .models import PowerState
from .protocols import mchose, x11

EQ_INPUTS = {"0": 0, "1": 1, "2": 2, "game1": 0, "game2": 1, "music": 2}
POLLING_INPUTS = {"125": 0, "250": 1, "500": 2, "1000": 3}
POLLING_LABELS = {v: k + " Hz" for k, v in POLLING_INPUTS.items()}


def build_hub() -> Hub:
    return Hub()


def _on_off(value: str) -> bool:
    v = value.strip().lower()
    if v in ("on", "true", "1", "yes"):
        return True
    if v in ("off", "false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected on/off, got {value!r}")


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="donglehub",
        description="Battery and settings hub for the MCHOSE V9 PRO headset "
                    "and AttackShark X11 mouse.",
    )
    sub = p.add_subparsers(dest="cmd")

    from .eq import cli as eqcli
    eqcli.add_parser(sub)

    st = sub.add_parser("status", help="show both devices once")
    st.add_argument("--json", action="store_true")

    w = sub.add_parser("watch", help="stream status snapshots (for shell widgets)")
    w.add_argument("--json", action="store_true")
    w.add_argument("--interval", type=float, default=30.0)
    w.add_argument("--max-polls", type=int, default=None)

    pr = sub.add_parser("probe", help="raw protocol probe for debugging")
    pr.add_argument("device", choices=["headset", "mouse"])

    se = sub.add_parser("set-eq", help="switch headset EQ profile")
    se.add_argument("mode", help="0|1|2 or game1|game2|music")

    sm = sub.add_parser("set-mouse", help="apply mouse settings")
    sm.add_argument("--color", type=int, default=0, help="0=Disabled 1=Breathing 2=Neon 3=Color Breathing")
    sm.add_argument("--polling", default="125", help="125|250|500|1000 (Hz)")
    sm.add_argument("--angle-snap", type=_on_off, default="off", metavar="ON|OFF")
    sm.add_argument("--ripple", type=_on_off, default="off", metavar="ON|OFF")
    sm.add_argument("--key-resp", type=int, default=8, help="key response ms (4-50, even)")
    sm.add_argument("--sleep", type=int, default=5, help="sleep time min (1-30)")
    sm.add_argument("--deep-sleep", type=int, default=10, help="deep sleep min (1-60)")

    sub.add_parser("gui", help="open the desktop app")

    return p, p.parse_args(argv)


def cmd_status(hub, as_json: bool) -> int:
    snap = hub.poll()
    if as_json:
        print(json.dumps(snap))
        return 0
    for device_id, label in (("headset", "Headset"), ("mouse", "Mouse")):
        d = snap["devices"][device_id]
        state = d["power"].replace("_", " ")
        conn = (d["connection"] or "-").upper().replace("2.4GHZ", "2.4G")
        extra = ""
        if device_id == "headset" and d["details"].get("eq_name"):
            extra = f"  eq: {d['details']['eq_name']}"
        if d["connected"]:
            line = f"{label:<8} {d['name']:<18} {d['battery'] if d['battery'] is not None else '-':>3}%  {state:<12} [{conn}]{extra}"
        else:
            line = f"{label:<8} {d['name']:<18}   -  disconnected"
        print(line)
    return 0


def cmd_set_eq(hub, mode_str: str) -> int:
    mode = EQ_INPUTS.get(mode_str.strip().lower())
    if mode is None:
        print(f"unknown EQ mode {mode_str!r}; use one of {sorted(EQ_INPUTS)}", file=sys.stderr)
        return 2
    applied = hub.headset.set_eq(mode)
    print(f"headset EQ profile: {mchose.EQ_MODES.get(applied, applied)}")
    return 0


def cmd_set_mouse(hub, args) -> int:
    rate = POLLING_INPUTS.get(args.polling.strip().lower().rstrip("hz").rstrip(" hz"))
    if rate is None:
        print(f"unknown polling rate {args.polling!r}; use 125|250|500|1000", file=sys.stderr)
        return 2
    try:
        settings = x11.MouseSettings(
            color_mode=args.color,
            polling_rate=rate,
            angle_snap=args.angle_snap,
            key_resp_ms=args.key_resp,
            sleep_min=args.sleep,
            deep_sleep_min=args.deep_sleep,
            ripple_control=args.ripple,
        )
        hub.mouse.apply_settings(settings)
    except (ValueError, IOError) as e:
        print(f"failed to apply mouse settings: {e}", file=sys.stderr)
        return 2
    print(
        f"mouse: color={x11.COLOR_MODE_LABELS[settings.color_mode]} "
        f"polling={POLLING_LABELS[rate]} angle_snap={settings.angle_snap} "
        f"ripple={settings.ripple_control} key_resp={settings.key_resp_ms}ms "
        f"sleep={settings.sleep_min}min deep_sleep={settings.deep_sleep_min}min"
    )
    return 0


def cmd_probe(hub, device: str) -> int:
    if device == "headset":
        st = hub.headset.poll()
        print(f"connected: {st.connected}  connection: {st.connection}")
        print(f"battery: {st.battery_pct}  status_byte: {st.status_raw}  power: {st.power.value}")
        print(f"eq: {st.details.get('eq_mode')} ({st.details.get('eq_name')})")
        fw = hub.headset.firmware()
        print(f"firmware: dongle={fw[0] or '?'} headset={fw[1] or '?'}")
        print("note: status_byte semantics are vendor-unknown; watch it with")
        print("      `donglehub probe headset` while charging to calibrate")
        print("      ~/.config/donglehub/config.json headset_status_map.")
    else:
        wireless, wired = hub.mouse._backend.presence()
        print(f"wireless dongle (1d57:fa60): {wireless}")
        print(f"wired/cable (1d57:fa55):     {wired}")
        for i in range(3):
            pkt = hub.mouse._backend.read_battery_packet(retries=1, timeout_ms=500)
            pct = x11.parse_battery_packet(pkt) if pkt else None
            hexdump = " ".join(f"{b:02x}" for b in (pkt or b"")[:16])
            print(f"packet[{i}]: battery={pct}  raw: {hexdump or '(none)'}")
        print("note: no packets while wireless = mouse is on the charging dock.")
    return 0


def cmd_gui() -> int:
    try:
        from .gui import run
    except ImportError as e:
        print(f"GUI unavailable (install PyQt6): {e}", file=sys.stderr)
        return 2
    return run()


def main(argv=None, hub=None, eq_controller=None) -> int:
    parser, args = parse_args(argv)
    if args.cmd is None:
        # Bare `donglehub`: open the app on a desktop session, show help
        # everywhere else.
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return cmd_gui()
        parser.print_help()
        return 0
    if args.cmd == "eq":
        from .eq import cli as eqcli

        return eqcli.dispatch(args, eq_controller)
    if args.cmd == "gui":
        return cmd_gui()
    hub = hub or build_hub()
    if args.cmd == "status":
        return cmd_status(hub, args.json)
    if args.cmd == "watch":

        def emit(snap):
            print(json.dumps(snap), flush=True)

        return watch_loop(hub, args.interval, emit, max_polls=args.max_polls)
    if args.cmd == "set-eq":
        return cmd_set_eq(hub, args.mode)
    if args.cmd == "set-mouse":
        return cmd_set_mouse(hub, args)
    if args.cmd == "probe":
        return cmd_probe(hub, args.device)
    return 2


if __name__ == "__main__":
    sys.exit(main())
