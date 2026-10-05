import QtQuick
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import qs.components
import qs.services
import qs.utils

// Battery status for the MCHOSE V9 PRO headset and AttackShark X11 mouse,
// driven by the DongleHub service (services/DongleHub.qml -> `donglehub watch`).
//
// Add to modules/bar/components/status/ and wire into StatusIcons.qml with a
// DelegateChoice for roleValue "donglehub" (see shell/caelestia/README.md).
ColumnLayout {
    id: root

    required property color colour

    spacing: Tokens.spacing.extraSmall / 2

    component DeviceRow: RowLayout {
        id: row

        required property string glyph
        required property string name
        required property bool connected
        required property real battery
        required property bool charging

        spacing: Tokens.spacing.extraSmall

        readonly property string text: !row.connected ? "—" : row.battery < 0 ? "…" : `${Math.round(row.battery)}%`
        readonly property color stateColour: {
            if (!row.connected)
                return Qt.alpha(root.colour, 0.4);
            if (row.charging)
                return Colours.palette.m3tertiary;
            if (row.battery >= 0 && row.battery <= 20)
                return Colours.palette.m3error;
            return root.colour;
        }

        MaterialIcon {
            animate: true
            text: row.glyph
            color: row.stateColour
            fontStyle: Tokens.font.icon.medium
        }

        StyledText {
            animate: true
            text: row.text
            color: row.stateColour
            font: Tokens.font.mono.medium
        }

        HoverHandler {
            id: hover
        }

        ToolTip.visible: hover.containsMouse
        ToolTip.text: !row.connected ? `${row.name}: disconnected` : `${row.name}: ${row.text}` + (row.charging ? " (charging)" : "")
    }

    DeviceRow {
        glyph: "headphones"
        name: "MCHOSE V9 PRO"
        connected: DongleHub.headsetConnected
        battery: DongleHub.headsetBattery
        charging: DongleHub.headsetCharging
    }

    DeviceRow {
        glyph: "mouse"
        name: "AttackShark X11"
        connected: DongleHub.mouseConnected
        battery: DongleHub.mouseBattery
        charging: DongleHub.mouseCharging
    }
}
