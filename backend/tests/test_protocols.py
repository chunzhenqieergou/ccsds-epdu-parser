"""
四大航天数据协议解析模块单元测试
"""

import struct
import unittest

from app.protocols.ccsds import (
    ASM,
    APID_ATTITUDE,
    crc_ccitt,
    hex_to_bytes,
    parse_attitude_telemetry,
    parse_cadu_frame,
    parse_epdu_header,
)
from app.protocols.can import (
    decode_can_signal,
    parse_can_ext_frame,
    parse_can_std_frame,
)
from app.protocols.m1553b import (
    build_bc_rt_message,
    parse_command_word,
    parse_data_word,
    parse_status_word,
)
from app.protocols.rs422 import (
    Rs422Parser,
    build_frame,
    crc16_modbus,
    parse_frame,
)


class TestCcsds(unittest.TestCase):
    """CCSDS Space Packet 协议测试"""

    CADU_FRAME3_HEX = """
    1A CF FC 1D 00 00 0C AA AA AA AA AA AA AA AA AA AA AA AA 00 03 C0 03 00 11
    1A 1B 1C 1D 1E 1F 20 21 22 23 24 25 26 27 28 29 D0 80 AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    00 00 00 00
    """

    def setUp(self):
        self.frame = hex_to_bytes(self.CADU_FRAME3_HEX)[:256]

    def test_hex_to_bytes(self):
        result = hex_to_bytes("1A CF FC 1D")
        self.assertEqual(result, b"\x1A\xCF\xFC\x1D")

    def test_hex_to_bytes_with_newlines(self):
        result = hex_to_bytes("1A CF\nFC 1D")
        self.assertEqual(result, b"\x1A\xCF\xFC\x1D")

    def test_crc_ccitt_known(self):
        data = b"\x1A\xCF\xFC\x1D"
        crc = crc_ccitt(data)
        self.assertIsInstance(crc, int)
        self.assertLess(crc, 0x10000)

    def test_crc_ccitt_init_fallback(self):
        crc = crc_ccitt(b"", 0x0000)
        self.assertEqual(crc, 0x0000)

    def test_cadu_frame_asm_valid(self):
        result = parse_cadu_frame(self.frame)
        self.assertTrue(result["ASM_valid"])
        self.assertEqual(result["ASM"], ASM)

    def test_cadu_frame_length(self):
        result = parse_cadu_frame(self.frame)
        self.assertEqual(result["frame_length"], 256)

    def test_cadu_first_header_pointer(self):
        result = parse_cadu_frame(self.frame)
        self.assertEqual(result["first_header_pointer"], 0x000C)

    def test_cadu_short_frame(self):
        result = parse_cadu_frame(b"\x1A\xCF\xFC\x1D" + b"\x00" * 6)
        self.assertEqual(result["frame_length"], 10)

    def test_epdu_header_apid(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)
        self.assertEqual(hdr["APID"], 0x003)
        self.assertEqual(hdr["APID"], APID_ATTITUDE)

    def test_epdu_header_fields(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)
        self.assertEqual(hdr["version_number"], 0)
        self.assertEqual(hdr["packet_type"], 0)
        self.assertEqual(hdr["grouping_flags"], 3)  # 独立包
        self.assertGreater(hdr["data_field_length"], 0)

    def test_epdu_crc_passes(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)

        data_field_start = epdu_offset + 6
        data_field = self.frame[data_field_start:data_field_start + hdr["data_field_length"]]
        crc_received = struct.unpack(">H", data_field[-2:])[0]
        crc_input = self.frame[epdu_offset:data_field_start + hdr["data_field_length"] - 2]
        crc_calc = crc_ccitt(crc_input)

        self.assertEqual(crc_received, crc_calc)

    def test_attitude_telemetry_count(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)

        data_field_start = epdu_offset + 6
        data_field = self.frame[data_field_start:data_field_start + hdr["data_field_length"]]
        telemetry_data = data_field[:-2]
        params = parse_attitude_telemetry(telemetry_data)
        self.assertEqual(len(params), 9)  # 4 quat + 3 gyro + mode + actuator

    def test_attitude_telemetry_quaternion(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)

        data_field_start = epdu_offset + 6
        data_field = self.frame[data_field_start:data_field_start + hdr["data_field_length"]]
        telemetry_data = data_field[:-2]
        params = parse_attitude_telemetry(telemetry_data)
        q0 = params[0]
        self.assertIn("四元数", q0["name"])
        self.assertEqual(q0["raw"], 0x1A1B)  # big-endian int16

    def test_attitude_telemetry_gyro(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)

        data_field_start = epdu_offset + 6
        data_field = self.frame[data_field_start:data_field_start + hdr["data_field_length"]]
        telemetry_data = data_field[:-2]
        params = parse_attitude_telemetry(telemetry_data)
        gyro_x = params[4]
        self.assertIn("角速度X", gyro_x["name"])
        self.assertEqual(gyro_x["raw"], 0x2223)

    def test_attitude_telemetry_mode(self):
        mpdu_zone_start = 7
        cadu = parse_cadu_frame(self.frame)
        epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
        epdu_header_bytes = self.frame[epdu_offset:epdu_offset + 6]
        hdr = parse_epdu_header(epdu_header_bytes)

        data_field_start = epdu_offset + 6
        data_field = self.frame[data_field_start:data_field_start + hdr["data_field_length"]]
        telemetry_data = data_field[:-2]
        params = parse_attitude_telemetry(telemetry_data)
        mode = params[8]
        self.assertEqual(mode["raw"], 0x29)


class TestM1553B(unittest.TestCase):
    """MIL-STD-1553B 协议测试"""

    def test_parse_command_word_fields(self):
        w = 0x8823
        result = parse_command_word(w)
        self.assertEqual(result["rt_address"], 4)
        self.assertEqual(result["t_r"], 0)
        self.assertEqual(result["sub_address"], 4)
        self.assertEqual(result["word_count"], 3)

    def test_parse_command_word_boundary(self):
        result = parse_command_word(0xFFFF)
        self.assertEqual(result["rt_address"], 0x1F)
        self.assertEqual(result["sub_address"], 0x1F)
        self.assertEqual(result["word_count"], 0x1F)

    def test_parse_command_word_zero(self):
        result = parse_command_word(0x0000)
        self.assertEqual(result["rt_address"], 0)
        self.assertEqual(result["t_r"], 0)

    def test_parse_command_word_invalid(self):
        result = parse_command_word(-1)
        self.assertEqual(result, {})

    def test_parse_data_word(self):
        result = parse_data_word(0x1234)
        self.assertEqual(result["data"], 0x1234)
        self.assertIn("parity", result)

    def test_parse_status_word(self):
        result = parse_status_word(0x4800)
        self.assertEqual(result["rt_address"], 2)
        self.assertEqual(result["message_error"], 0)
        self.assertEqual(result["busy"], 0)

    def test_parse_status_word_busy(self):
        result = parse_status_word(0x4804)
        self.assertEqual(result["busy"], 1)

    def test_build_bc_rt_message_structure(self):
        msg = build_bc_rt_message(rt_address=10, sub_address=5, data_words=[0xAAAA, 0xBBBB])
        self.assertEqual(msg["word_count"], 2)
        cmd = msg["command_parsed"]
        self.assertEqual(cmd["rt_address"], 10)
        self.assertEqual(cmd["sub_address"], 5)
        self.assertEqual(len(msg["data_words"]), 2)

    def test_build_bc_rt_message_empty_data(self):
        msg = build_bc_rt_message(rt_address=0, sub_address=0, data_words=[])
        self.assertEqual(msg["word_count"], 0)
        self.assertEqual(msg["data_words"], [])


class TestCAN(unittest.TestCase):
    """CAN 总线协议测试"""

    def test_parse_can_std_frame(self):
        result = parse_can_std_frame(arb_id=0x123, dlc=4, data_bytes=bytes([0x01, 0x02, 0x03, 0x04]))
        self.assertEqual(result["id"], 0x123)
        self.assertEqual(result["id_type"], "STD")
        self.assertEqual(result["dlc"], 4)
        self.assertEqual(result["data"], bytes([0x01, 0x02, 0x03, 0x04]))

    def test_parse_can_std_frame_dlc_exceeds_data(self):
        result = parse_can_std_frame(arb_id=0x7FF, dlc=8, data_bytes=bytes([0xAA, 0xBB]))
        self.assertEqual(len(result["data"]), 2)

    def test_parse_can_ext_frame(self):
        result = parse_can_ext_frame(arb_id=0x18DAF110, dlc=8, data_bytes=b"\x00" * 8)
        self.assertEqual(result["id_type"], "EXT")
        self.assertEqual(result["id"], 0x18DAF110)
        self.assertGreater(result["base_id"], 0)
        self.assertGreater(result["ext_id"], 0)
        self.assertEqual(result["ide"], 1)

    def test_decode_can_signal_single_byte(self):
        data = bytes([0x12, 0x34, 0x56, 0x78])
        val = decode_can_signal(byte_offset=0, start_bit=0, length=8, data_bytes=data)
        self.assertEqual(val, 0x12)

    def test_decode_can_signal_nibble(self):
        data = bytes([0x34, 0x00, 0x00, 0x00])
        val = decode_can_signal(byte_offset=0, start_bit=0, length=4, data_bytes=data)
        self.assertEqual(val, 4)  # low nibble of 0x34

    def test_decode_can_signal_two_byte_little_endian(self):
        data = bytes([0x12, 0x34, 0x00, 0x00])
        val = decode_can_signal(byte_offset=0, start_bit=0, length=16, data_bytes=data)
        self.assertEqual(val, 0x3412)  # little-endian: low byte first

    def test_decode_can_signal_signed(self):
        data = bytes([0xFF, 0x00, 0x00, 0x00])
        val = decode_can_signal(byte_offset=0, start_bit=0, length=8, data_bytes=data, signed=True)
        self.assertEqual(val, -1)

    def test_decode_can_signal_scale_offset(self):
        data = bytes([0x64, 0x00, 0x00, 0x00])
        val = decode_can_signal(byte_offset=0, start_bit=0, length=8, data_bytes=data, scale=0.1, offset=10)
        self.assertAlmostEqual(val, 20.0)

    def test_decode_can_signal_empty_data(self):
        val = decode_can_signal(byte_offset=0, start_bit=0, length=8, data_bytes=b"")
        self.assertEqual(val, 0.0)


class TestRS422(unittest.TestCase):
    """RS-422 自定义串口协议测试"""

    def test_crc16_modbus_known(self):
        crc = crc16_modbus(b"\x01\x03\x00\x00\x00\x01")
        self.assertIsInstance(crc, int)
        self.assertLess(crc, 0x10000)

    def test_parse_frame_valid(self):
        frame = build_frame(satellite_id=3, params=[1.5, 2.5, 3.5])
        result = parse_frame(frame)
        self.assertIsNotNone(result)
        self.assertEqual(result["satellite_id"], 3)
        self.assertEqual(len(result["params"]), 3)
        self.assertTrue(result["crc_ok"])

    def test_parse_frame_crc_fail(self):
        frame = build_frame(satellite_id=1, params=[1.0])
        corrupted = bytearray(frame)
        corrupted[-3] ^= 0xFF
        result = parse_frame(bytes(corrupted))
        self.assertIsNotNone(result)
        self.assertFalse(result["crc_ok"])

    def test_parse_frame_bad_header(self):
        result = parse_frame(b"\x00\x00\x00\x03\x01\x00\x00\x00\x00\x00\x00")
        self.assertIsNone(result)

    def test_parse_frame_too_short(self):
        result = parse_frame(b"\xAA\x55")
        self.assertIsNone(result)

    def test_parse_frame_no_params(self):
        frame = build_frame(satellite_id=7, params=[])
        result = parse_frame(frame)
        self.assertIsNotNone(result)
        self.assertEqual(result["satellite_id"], 7)
        self.assertEqual(len(result["params"]), 0)
        self.assertTrue(result["crc_ok"])

    def test_rs422_parser_single_frame(self):
        frame = build_frame(satellite_id=1, params=[2.718])
        parser = Rs422Parser()
        results = []
        for b in frame:
            r = parser.feed(b)
            if r:
                results.append(r)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["satellite_id"], 1)
        self.assertTrue(results[0]["crc_ok"])

    def test_rs422_parser_bad_crc_discarded(self):
        good = build_frame(satellite_id=1, params=[1.0])
        bad = bytearray(build_frame(satellite_id=2, params=[2.0]))
        bad[-3] ^= 0xFF
        stream = good + bytes(bad)
        parser = Rs422Parser()
        results = []
        for b in stream:
            r = parser.feed(b)
            if r:
                results.append(r)
        self.assertEqual(len(results), 1)  # 坏 CRC 帧被丢弃
        self.assertEqual(results[0]["satellite_id"], 1)

    def test_rs422_parser_sync_recovery(self):
        frame = build_frame(satellite_id=5, params=[42.0])
        preamble = b"\x00\x01\x02"
        stream = preamble + frame
        parser = Rs422Parser()
        results = []
        for b in stream:
            r = parser.feed(b)
            if r:
                results.append(r)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["satellite_id"], 5)

    def test_rs422_parser_multiple_frames(self):
        f1 = build_frame(satellite_id=1, params=[10.0])
        f2 = build_frame(satellite_id=2, params=[20.0])
        stream = f1 + f2
        parser = Rs422Parser()
        results = []
        for b in stream:
            r = parser.feed(b)
            if r:
                results.append(r)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["satellite_id"], 1)
        self.assertEqual(results[1]["satellite_id"], 2)

    def test_rs422_parser_reset(self):
        frame = build_frame(satellite_id=1, params=[1.0])
        parser = Rs422Parser()
        for b in frame[:4]:
            r = parser.feed(b)
            self.assertIsNone(r)
        parser.reset()
        for b in frame:
            r = parser.feed(b)
            if r:
                self.assertEqual(r["satellite_id"], 1)
                break


if __name__ == "__main__":
    unittest.main()
