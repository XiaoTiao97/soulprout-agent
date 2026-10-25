"""豆包语音二进制帧编解码单测（无需网络）。运行：python -m unittest agent.tests.test_doubao_protocol"""

import gzip
import json
import struct
import unittest

from agent.services.doubao_speech import protocol as p


class AsrFrameTest(unittest.TestCase):
    def test_full_request_layout(self):
        frame = p.asr_full_request({"a": 1})
        self.assertEqual(frame[:4], bytes([0x11, 0x10, 0x10, 0x00]))
        size = struct.unpack(">I", frame[4:8])[0]
        self.assertEqual(json.loads(frame[8 : 8 + size]), {"a": 1})

    def test_audio_request_flags(self):
        mid = p.asr_audio_request(b"\x01\x02", last=False)
        last = p.asr_audio_request(b"", last=True)
        self.assertEqual(mid[:4], bytes([0x11, 0x20, 0x00, 0x00]))
        self.assertEqual(last[:4], bytes([0x11, 0x22, 0x00, 0x00]))
        self.assertEqual(mid[4:8], struct.pack(">I", 2))
        self.assertEqual(mid[8:], b"\x01\x02")

    def test_parse_server_response_with_seq_and_gzip(self):
        body = gzip.compress(json.dumps({"result": {"text": "你好"}}).encode())
        frame = bytes([0x11, 0x91, 0x11, 0x00]) + struct.pack(">i", 3) + struct.pack(">I", len(body)) + body
        msg = p.parse_asr_server(frame)
        self.assertFalse(msg.is_error)
        self.assertEqual(msg.sequence, 3)
        self.assertEqual(msg.payload["result"]["text"], "你好")

    def test_parse_server_last_negative_seq(self):
        body = b"{}"
        frame = bytes([0x11, 0x93, 0x10, 0x00]) + struct.pack(">i", -5) + struct.pack(">I", len(body)) + body
        msg = p.parse_asr_server(frame)
        self.assertEqual(msg.sequence, -5)
        self.assertTrue(msg.is_last)

    def test_parse_error(self):
        text = "bad".encode()
        frame = bytes([0x11, 0xF0, 0x10, 0x00]) + struct.pack(">I", 45000001) + struct.pack(">I", len(text)) + text
        msg = p.parse_asr_server(frame)
        self.assertTrue(msg.is_error)
        self.assertEqual(msg.error_code, 45000001)
        self.assertEqual(msg.payload, "bad")


class TtsFrameTest(unittest.TestCase):
    def test_start_connection_has_no_session_id(self):
        frame = p.tts_event_frame(p.EV_START_CONNECTION)
        self.assertEqual(frame[:4], bytes([0x11, 0x14, 0x10, 0x00]))
        self.assertEqual(struct.unpack(">i", frame[4:8])[0], 1)
        self.assertEqual(struct.unpack(">I", frame[8:12])[0], 2)
        self.assertEqual(frame[12:], b"{}")

    def test_session_event_carries_session_id(self):
        frame = p.tts_event_frame(p.EV_TASK_REQUEST, {"x": 1}, session_id="abc")
        self.assertEqual(struct.unpack(">i", frame[4:8])[0], 200)
        self.assertEqual(struct.unpack(">I", frame[8:12])[0], 3)
        self.assertEqual(frame[12:15], b"abc")

    def test_parse_audio_response(self):
        sid = b"sess"
        audio = b"\x00\x01\x02\x03"
        frame = (
            bytes([0x11, 0xB4, 0x00, 0x00])
            + struct.pack(">i", p.EV_TTS_RESPONSE)
            + struct.pack(">I", len(sid)) + sid
            + struct.pack(">I", len(audio)) + audio
        )
        msg = p.parse_tts_server(frame)
        self.assertTrue(msg.is_audio)
        self.assertEqual(msg.session_id, "sess")
        self.assertEqual(msg.audio, audio)

    def test_parse_connection_started_and_session_finished(self):
        cid = b"conn"
        frame = (
            bytes([0x11, 0x94, 0x10, 0x00])
            + struct.pack(">i", p.EV_CONNECTION_STARTED)
            + struct.pack(">I", len(cid)) + cid
            + struct.pack(">I", 2) + b"{}"
        )
        msg = p.parse_tts_server(frame)
        self.assertEqual(msg.event, p.EV_CONNECTION_STARTED)
        self.assertEqual(msg.session_id, "")

        body = json.dumps({"status_code": 20000000}).encode()
        frame = (
            bytes([0x11, 0x94, 0x10, 0x00])
            + struct.pack(">i", p.EV_SESSION_FINISHED)
            + struct.pack(">I", 1) + b"s"
            + struct.pack(">I", len(body)) + body
        )
        msg = p.parse_tts_server(frame)
        self.assertEqual(msg.event, p.EV_SESSION_FINISHED)
        self.assertEqual(msg.session_id, "s")
        self.assertEqual(msg.payload["status_code"], 20000000)


if __name__ == "__main__":
    unittest.main()
