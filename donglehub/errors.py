class DongleHubError(Exception):
    """Base error for DongleHub."""


class DeviceUnavailable(DongleHubError):
    """The target USB/HID device could not be opened."""
