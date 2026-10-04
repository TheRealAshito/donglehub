#!/usr/bin/env bash
# DongleHub installer — tested layout for CachyOS/Arch; Debian/Ubuntu branch included.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing dependencies"
if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed python python-pyqt6 python-pyusb hidapi libusb wireplumber
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y python3 python3-venv python3-pyqt6 python3-usb \
        libhidapi-hidraw0 libusb-1.0-0 wireplumber
else
    echo "Unsupported distro: install python, PyQt6, pyusb, hidapi, libusb, wireplumber manually." >&2
fi

echo "==> Installing udev rules (device access without root)"
sudo install -Dm644 udev/90-donglehub.rules /etc/udev/rules.d/90-donglehub.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Installing donglehub into ~/.local/share/donglehub/venv"
VENV="$HOME/.local/share/donglehub/venv"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --quiet .
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV/bin/donglehub" "$HOME/.local/bin/donglehub"
ln -sf "$VENV/bin/donglehub-gui" "$HOME/.local/bin/donglehub-gui"

echo "==> Installing launcher"
install -Dm644 packaging/donglehub.desktop "$HOME/.local/share/applications/donglehub.desktop"

echo
echo "Done. Make sure ~/.local/bin is on your PATH, then try:  donglehub status"
echo "Caelestia sidebar widget: see shell/caelestia/README.md"
