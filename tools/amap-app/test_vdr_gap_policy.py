import unittest
from types import SimpleNamespace
import numpy as np
from vdr_gap_policy import GapPolicy


class GapPolicyTest(unittest.TestCase):
    def test_configuration_and_strict_sample_gap_threshold(self):
        for enabled, gap, expected in ((False, 1000, 0), (True, 300, 0), (True, 301, 100000)):
            engine = SimpleNamespace(correction=SimpleNamespace(covariance=np.eye(21)))
            GapPolicy(enabled=enabled)(engine, SimpleNamespace(maximum_sample_gap=gap))
            self.assertEqual(engine.correction.covariance[0, 0], 1+expected)
            self.assertEqual(engine.correction.covariance[9, 9], 1)


if __name__ == '__main__':
    unittest.main()
