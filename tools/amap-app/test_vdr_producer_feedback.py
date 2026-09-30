"""Feedback ordering matters: publication must precede the next bias refresh."""
import unittest

from vdr_window_gps import WindowGps
from vdr_window_producer import WindowProducer


class ProducerFeedbackTest(unittest.TestCase):
    def test_synchronous_feedback_enters_new_window_only(self):
        producer = WindowProducer()
        seen = []

        def publish(primary, lookahead):
            seen.append(primary.integrated.gyro_bias[:])
            producer.feedback_bias(primary.integrated.timestamp,
                                   [.01, .02, .03], [.1, .2, .3])

        producer.on_publish = publish
        producer.push(30000, (0, 0, 0), (0, 0, 9.8),
                      WindowGps(30000, 120, 30, speed=5))
        self.assertEqual(seen, [[0., 0., 0.]])
        self.assertEqual(producer.current.integrated.gyro_bias, [.01, .02, .03])
        self.assertEqual(producer.last_bias_refresh, 30000)

    def test_only_gps_restart_refreshes_and_threshold_is_strict(self):
        producer = WindowProducer()
        producer.feedback_bias(1000, [1, 2, 3], [4, 5, 6])
        producer._restart_current(29000, refresh=True)
        self.assertEqual(producer.last_bias_refresh, -1000)
        producer._restart_current(40000)
        self.assertEqual(producer.gyro_bias, [0., 0., 0.])
        producer._restart_current(40000, refresh=True)
        self.assertEqual(producer.gyro_bias, [1., 2., 3.])
        producer.feedback_bias(41000, [2, 3, 4], [5, 6, 7])
        producer._restart_current(70001, refresh=True)
        self.assertAlmostEqual(producer.gyro_bias[0], 2.9/1.9)


if __name__ == '__main__':
    unittest.main()
