pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

// DongleHub service: streams battery/charging state for the MCHOSE V9 PRO
// headset and AttackShark X11 mouse from the `donglehub` CLI.
//
// Requires `donglehub` on PATH (see shell/caelestia/README.md if it is not).
Singleton {
    id: root

    property bool headsetConnected: false
    property real headsetBattery: -1
    property bool headsetCharging: false
    property string headsetPower: "unknown"

    property bool mouseConnected: false
    property real mouseBattery: -1
    property bool mouseCharging: false
    property string mousePower: "unknown"

    function applySnapshot(obj: var): void {
        const h = obj.devices.headset;
        const m = obj.devices.mouse;

        root.headsetConnected = h.connected;
        root.headsetBattery = h.battery === null ? -1 : h.battery;
        root.headsetCharging = h.charging;
        root.headsetPower = h.power;

        root.mouseConnected = m.connected;
        root.mouseBattery = m.battery === null ? -1 : m.battery;
        root.mouseCharging = m.charging;
        root.mousePower = m.power;
    }

    function reload(): void {
        statusProc.running = true;
    }

    Process {
        id: watchProc

        running: true
        command: ["donglehub", "watch", "--interval", "30", "--json"]

        stdout: SplitParser {
            onRead: data => {
                try {
                    root.applySnapshot(JSON.parse(data));
                } catch (e) {
                    console.warn("DongleHub: bad snapshot:", e);
                }
            }
        }

        onExited: restartTimer.restart()
    }

    Process {
        id: statusProc

        command: ["donglehub", "status", "--json"]

        stdout: SplitParser {
            onRead: data => {
                try {
                    root.applySnapshot(JSON.parse(data));
                } catch (e) {
                }
            }
        }
    }

    Timer {
        id: restartTimer

        interval: 5000
        onTriggered: watchProc.running = true
    }
}
