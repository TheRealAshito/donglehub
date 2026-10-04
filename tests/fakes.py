"""Fake transports for device/hub/CLI tests (no hardware needed)."""
from donglehub.models import DeviceStatus, PowerState


class ScriptedHid:
    """Stand-in for a hidapi session: replies are served from a queue."""

    def __init__(self, replies=()):
        self.replies = [bytes(r) for r in replies]
        self.writes = []
        self.features_sent = []
        self.closed = False

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def read_timeout(self, length, timeout_ms):
        return self.replies.pop(0) if self.replies else b""

    def send_feature(self, data):
        self.features_sent.append(bytes(data))
        return len(data)

    def get_feature(self, report_id, length):
        return self.replies.pop(0) if self.replies else bytes(length)

    def close(self):
        self.closed = True


class RaisingSessionFactory:
    """Simulates an absent dongle."""

    def __call__(self):
        from donglehub.errors import DeviceUnavailable

        raise DeviceUnavailable("no hid device")


class FakeX11Backend:
    def __init__(self, wireless=True, wired=False, battery_packets=()):
        self.wireless = wireless
        self.wired = wired
        self.battery_packets = [bytes(p) for p in battery_packets]
        self.sent = []
        self.read_attempts = 0

    def presence(self):
        return self.wireless, self.wired

    def read_battery_packet(self, retries=5, timeout_ms=500):
        self.read_attempts += 1
        return self.battery_packets.pop(0) if self.battery_packets else None

    def send_report(self, report_id, data):
        self.sent.append((report_id, bytes(data)))
        return True


class RaisingX11Backend:
    """Simulates a broken/missing libusb stack."""

    def presence(self):
        from donglehub.errors import DeviceUnavailable

        raise DeviceUnavailable("libusb not available")


class FakeHub:
    """Minimal Hub stand-in for CLI tests."""

    def __init__(self, headset_status, mouse_status):
        self.headset_status = headset_status
        self.mouse_status = mouse_status
        self.eq_sets = []
        self.mouse_settings = []

        class _Headset:
            def __init__(self, outer):
                self.outer = outer

            def set_eq(self, mode):
                self.outer.eq_sets.append(mode)
                return mode

        class _Mouse:
            def __init__(self, outer):
                self.outer = outer

            def apply_settings(self, settings):
                self.outer.mouse_settings.append(settings)

        self.headset = _Headset(self)
        self.mouse = _Mouse(self)

    def poll_devices(self):
        return self.headset_status, self.mouse_status

    def poll(self):
        from donglehub.models import hub_snapshot

        return hub_snapshot(*self.poll_devices())


def sample_status(device_id="headset", **kw):
    base = dict(
        device_id=device_id,
        name="Dev",
        connected=True,
        connection="2.4ghz",
        battery_pct=42,
        power=PowerState.ON_BATTERY,
        status_raw=0,
    )
    base.update(kw)
    return DeviceStatus(**base)
