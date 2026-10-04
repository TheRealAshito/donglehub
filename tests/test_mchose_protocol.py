"""Protocol tests for the MCHOSE V9 PRO 2.4G dongle (VID 0x291D / PID 0x385D).

Packets reverse-engineered from JoaoKSS/MCHOSE_v9_PRO_Controller.
"""
import pytest

from donglehub.protocols import mchose


def test_cmd_status_is_64_byte_report_with_expected_header():
    cmd = mchose.cmd_status()
    assert len(cmd) == 64
    assert cmd[0] == 0x55 and cmd[1] == 0x65 and cmd[2] == 0x01


def test_parse_status_reply_extracts_battery_and_status_bytes():
    reply = bytearray(64)
    reply[0], reply[1] = 0x55, 0x65
    reply[2], reply[3] = 87, 0x00
    assert mchose.parse_status_reply(bytes(reply)) == (87, 0x00)


def test_parse_status_reply_rejects_wrong_header():
    reply = bytearray(64)
    reply[0], reply[1] = 0x55, 0x11
    reply[2], reply[3] = 87, 0x00
    assert mchose.parse_status_reply(bytes(reply)) is None


def test_parse_status_reply_rejects_short_packet():
    assert mchose.parse_status_reply(b"\x55\x65\x57") is None


def test_cmd_eq_query_and_reply_roundtrip():
    cmd = mchose.cmd_eq_query()
    assert len(cmd) == 64
    assert cmd[0] == 0x55 and cmd[1] == 0x11
    reply = bytearray(64)
    reply[0], reply[1], reply[2] = 0x55, 0x11, 0x02
    assert mchose.parse_eq_reply(bytes(reply)) == 2
    assert mchose.parse_eq_reply(b"\x55\x11") is None
    reply2 = bytearray(64)
    reply2[0], reply2[1] = 0x55, 0x65
    assert mchose.parse_eq_reply(bytes(reply2)) is None


def test_cmd_eq_set_encodes_mode_and_validates_range():
    cmd = mchose.cmd_eq_set(1)
    assert cmd[0] == 0x55 and cmd[1] == 0x21 and cmd[2] == 0x01 and cmd[3] == 1
    with pytest.raises(ValueError):
        mchose.cmd_eq_set(3)
    with pytest.raises(ValueError):
        mchose.cmd_eq_set(-1)


def test_eq_mode_names_cover_three_profiles():
    assert set(mchose.EQ_MODES) == {0, 1, 2}


def test_cmd_firmware_is_feature_report_aa():
    cmd = mchose.cmd_firmware()
    assert len(cmd) == 64
    assert cmd[0] == 0xAA and cmd[1] == 0x01 and cmd[2] == 0x00


def test_parse_firmware_reply_formats_decimal_pairs():
    reply = bytearray(64)
    reply[0] = 0xAA
    reply[8], reply[9], reply[10], reply[11] = 1, 2, 3, 4
    assert mchose.parse_firmware_reply(bytes(reply)) == ("0102", "0304")


def test_parse_firmware_reply_returns_none_on_bad_header():
    reply = bytearray(64)
    reply[0] = 0x55
    assert mchose.parse_firmware_reply(bytes(reply)) is None
