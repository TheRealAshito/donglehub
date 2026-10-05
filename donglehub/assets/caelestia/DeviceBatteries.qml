import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.services
import qs.utils

// Battery card for the Caelestia sidebar (or dashboard): MCHOSE V9 PRO
// headset + AttackShark X11 mouse, live via the DongleHub service.
ColumnLayout {
    id: root

    spacing: Tokens.spacing.small

    component DeviceRow: RowLayout {
        id: row

        property string glyph: "help"
        property real battery: -1
        property bool charging: false
        property bool connected: false

        spacing: Tokens.spacing.medium

        MaterialIcon {
            animate: true
            text: row.glyph
            color: row.connected ? Colours.palette.m3primary : Colours.palette.m3outlineVariant
            fontStyle: Tokens.font.icon.builders.medium.build()
        }

        StyledText {
            Layout.fillWidth: true

            animate: true
            text: !row.connected ? "Disconnected" : row.battery < 0 ? "—" : `${Math.round(row.battery)}%`
            color: row.connected ? Colours.palette.m3onSurface : Colours.palette.m3outlineVariant
            font: Tokens.font.body.small
        }

        MaterialIcon {
            animate: true
            visible: row.connected && row.charging
            text: "bolt"
            fill: 1
            color: Colours.palette.m3tertiary
            fontStyle: Tokens.font.icon.builders.medium.build()
        }

        MaterialIcon {
            animate: true
            text: row.connected ? Icons.getBatteryIcon(row.battery < 0 ? 0 : row.battery / 100, row.charging) : "battery_unknown"
            fill: 1
            color: {
                if (!row.connected)
                    return Colours.palette.m3outlineVariant;
                if (row.battery >= 0 && row.battery <= 0.2 * 100 && !row.charging)
                    return Colours.palette.m3error;
                return row.charging ? Colours.palette.m3tertiary : Colours.palette.m3onSurface;
            }
            fontStyle: Tokens.font.icon.builders.medium.build()
        }
    }

    DeviceRow {
        Layout.fillWidth: true

        glyph: "headphones"
        battery: DongleHub.headsetBattery
        charging: DongleHub.headsetCharging
        connected: DongleHub.headsetConnected
    }

    DeviceRow {
        Layout.fillWidth: true

        glyph: "mouse"
        battery: DongleHub.mouseBattery
        charging: DongleHub.mouseCharging
        connected: DongleHub.mouseConnected
    }
}
