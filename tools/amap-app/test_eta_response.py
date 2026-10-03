import unittest

from eta_response import parse_eta_response


class EtaResponseTest(unittest.TestCase):
    def test_captured_no_event_frame_is_not_accepted(self):
        # Header observed in the bounded 2026-10-01 ETA probe. Its submitted
        # route ID is replaced here because only the header matters.
        raw = bytes.fromhex("3500000014004a7602c80000010000000000000000") + b"0" * 32
        frame = parse_eta_response(raw)
        self.assertEqual(frame.frame_length, 53)
        self.assertEqual(frame.data_version, 30282)
        self.assertEqual(frame.result_code, 2)
        self.assertEqual(frame.status_field, 200)
        self.assertEqual(frame.flags, 1)
        self.assertEqual(frame.data_length, 0)
        self.assertEqual(frame.data, b"")
        self.assertFalse(frame.accepted)

    def test_rejects_truncated_frame(self):
        with self.assertRaises(ValueError):
            parse_eta_response(b"\x35\x00")

    def test_rejects_incorrect_length(self):
        raw = bytes.fromhex("3500000014004a7602c80000010000000000000000") + b"0" * 31
        with self.assertRaises(ValueError):
            parse_eta_response(raw)


if __name__ == "__main__":
    unittest.main()
