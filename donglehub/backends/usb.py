"""pyusb transport for the AttackShark X11 mouse (Xenta 0x1d57).

Battery: interrupt IN packets on interface 2 / endpoint 0x83.
Settings: SET_REPORT control transfers on interface 2.
Requires the `pyusb` package and system libusb-1.0.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ..errors import DeviceUnavailable
from ..protocols import x11

SET_REPORT_TYPE = 0x21
SET_REPORT_REQUEST = 0x09
CTRL_TIMEOUT_MS = 200


def _usb():
    try:
        import usb.core
        import usb.util

        # Force the libusb backend to load now so failures surface here.
        _ = list(usb.core.find(find_all=True) or [])
        return usb.core, usb.util
    except ImportError as e:  # pragma: no cover - depends on host packages
        raise DeviceUnavailable(f"pyusb not available: {e}")
    except Exception as e:  # pragma: no cover - depends on host packages
        raise DeviceUnavailable(f"libusb backend not usable: {e}")


class X11UsbBackend:
    """Battery reads and settings writes for the X11."""

    def presence(self) -> Tuple[bool, bool]:
        usb_core, _ = _usb()
        wireless = usb_core.find(idVendor=x11.VID, idProduct=x11.PID_WIRELESS) is not None
        wired = usb_core.find(idVendor=x11.VID, idProduct=x11.PID_WIRED) is not None
        return wireless, wired

    def read_battery_packet(
        self, retries: int = 1, timeout_ms: int = 500
    ) -> Optional[bytes]:
        """Return one raw 64-byte packet from the battery endpoint, or None."""
        usb_core, usb_util = _usb()
        dev = usb_core.find(idVendor=x11.VID, idProduct=x11.PID_WIRELESS)
        if dev is None:
            return None

        iface = x11.BATTERY_IFACE
        reattach = False
        if dev.is_kernel_driver_active(iface):
            dev.detach_kernel_driver(iface)
            reattach = True
        try:
            usb_util.claim_interface(dev, iface)
            try:
                for _ in range(max(1, retries)):
                    try:
                        data = dev.read(
                            x11.BATTERY_ENDPOINT, 64, timeout=timeout_ms
                        )
                        return bytes(data)
                    except usb_core.USBError:
                        continue
                return None
            finally:
                usb_util.release_interface(dev, iface)
        finally:
            if reattach:
                try:
                    dev.attach_kernel_driver(iface)
                except Exception:
                    pass

    def send_report(self, report_id: int, data: bytes) -> bool:
        usb_core, usb_util = _usb()
        dev = usb_core.find(idVendor=x11.VID, idProduct=x11.PID_WIRELESS)
        if dev is None:
            return False
        iface = x11.CONFIG_IFACE
        reattach = False
        if dev.is_kernel_driver_active(iface):
            dev.detach_kernel_driver(iface)
            reattach = True
        try:
            rc = dev.ctrl_transfer(
                SET_REPORT_TYPE,
                SET_REPORT_REQUEST,
                report_id,
                iface,
                bytes(data),
                timeout=CTRL_TIMEOUT_MS,
            )
            return rc == len(data)
        except usb_core.USBError:
            return False
        finally:
            if reattach:
                try:
                    dev.attach_kernel_driver(iface)
                except Exception:
                    pass
