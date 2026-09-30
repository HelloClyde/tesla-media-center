import unittest
from vdr_browser_resampler import BrowserResampler


def measured(timestamp):
    seconds = (timestamp-1)/1000
    return dict(timestamp=timestamp, gyro=[seconds, 0, -seconds],
                acceleration=[2*seconds, 0, 9.8])


class BrowserResamplerTest(unittest.TestCase):
    def test_irregular_linear_motion_is_reconstructed_on_25hz_grid(self):
        adapter = BrowserResampler(maximum_gap=80)
        results = []
        for timestamp in (1, 18, 35, 51, 73, 92, 113, 135, 161):
            results.extend(adapter.push(measured(timestamp)))
        self.assertEqual([s['timestamp'] for s in results], [1, 41, 81, 121, 161])
        for result in results:
            expected = measured(result['timestamp'])
            for key in ('gyro', 'acceleration'):
                for actual, target in zip(result[key], expected[key]):
                    self.assertAlmostEqual(actual, target, places=12)
        self.assertEqual(adapter.push(measured(170)), [])  # No extrapolation to201.

    def test_no_fill_across_sensor_outage_and_no_silent_resume(self):
        adapter = BrowserResampler(maximum_gap=80)
        adapter.push(measured(1))
        with self.assertRaises(ValueError):
            adapter.push(measured(1001))
        with self.assertRaises(ValueError):
            adapter.push(measured(1041))
        self.assertEqual(adapter.previous['timestamp'], 1)

    def test_input_and_output_are_independent_snapshots(self):
        adapter = BrowserResampler(maximum_gap=80)
        input_sample = measured(1)
        first = adapter.push(input_sample)[0]
        input_sample['gyro'][0] = 100
        first['acceleration'][0] = 100
        result = adapter.push(measured(41))[0]
        self.assertEqual(result['gyro'][0], .04)
        self.assertEqual(result['acceleration'][0], .08)
        with self.assertRaises(ValueError):
            adapter.push(measured(40))
        self.assertEqual(adapter.previous['timestamp'], 41)


if __name__ == '__main__':
    unittest.main()
