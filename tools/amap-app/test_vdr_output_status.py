import unittest
from types import SimpleNamespace
from vdr_output_status import OutputStatus


class OutputStatusTest(unittest.TestCase):
    def test_running_retaining_and_unstable_boundaries(self):
        status = OutputStatus()
        window = SimpleNamespace(quality=2, motion=1, missing_fix=False)
        self.assertEqual(status.update(16, 1000, True, window=window), [3, 9, 4, 6])
        self.assertTrue(status.active)
        self.assertEqual(status.update(32, 1500, True), [5, 7])
        self.assertTrue(status.active)
        self.assertEqual(status.update(8, 2000, True, unstable_delay=500,
                                       reference_timestamp=1500), [4])
        self.assertFalse(status.flag66)
        self.assertEqual(status.update(8, 2001, True, unstable_delay=500,
                                       reference_timestamp=1500), [6])
        self.assertEqual(status.update(8, 2100, False), [5, 7])
        self.assertFalse(status.active)
        self.assertEqual(status.motion, 1)


if __name__ == '__main__':
    unittest.main()
