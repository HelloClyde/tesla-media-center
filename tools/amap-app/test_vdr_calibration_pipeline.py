"""Continuous IMU -> producer -> motion -> calibration integration check."""
from dataclasses import dataclass
import unittest
import numpy as np
from vdr_window_gps import WindowGps
from vdr_window_producer import WindowProducer
from vdr_window_dispatch import DispatchWindow, dispatch_window
from vdr_motion_observer import MotionObserver, MotionWindow
from vdr_calibration_observer import CalibrationObserver
from vdr_orientation_quality import OrientationQualityObserver
from vdr_direction_observer import DirectionObserver, DirectionGps


@dataclass
class Fix(WindowGps):
    position_sigma: float = 1.
    zero_speed_valid: bool = True


class CalibrationPipelineTest(unittest.TestCase):
    def test_all_initialization_observers_receive_continuous_windows(self):
        producer = WindowProducer()
        observers = [OrientationQualityObserver(), DirectionObserver(),
                     MotionObserver(), CalibrationObserver()]
        for observer in observers:
            observer.transition(1000, 4)
        outputs = []
        for step in range(500):
            timestamp = 1000 + step * 40
            gps = DirectionGps(timestamp, 120. + step * .000003, 30.,
                               speed=6., direction=0., position_sigma=1.) if step % 25 == 0 else None
            publications, gap = producer.push(timestamp, (0., 0., 0.), (.2, .3, 9.8), gps)
            self.assertIsNone(gap)
            for primary, lookahead in publications:
                output = MotionWindow(primary.integrated, gps=primary.gps)
                dispatch_window(DispatchWindow(primary.gps, output, primary.samples),
                                observers, lambda *args: None, lambda: None)
                outputs.append(output)
        self.assertGreater(outputs[-1].quality, 0)
        self.assertEqual(next(o for o in reversed(outputs) if o.gps is not None).direction, 0.)
        self.assertFalse(outputs[-1].missing_fix)
        self.assertIsNotNone(outputs[-1].fallback)

    def test_continuous_stationary_input_produces_fallback_and_bias(self):
        producer = WindowProducer()
        motion, calibration = MotionObserver(), CalibrationObserver()
        for observer in (motion, calibration):
            observer.transition(1000, 4)
        output = None
        for step in range(400):
            timestamp = 1000 + step * 20
            gps = Fix(timestamp, 120., 30.) if step % 25 == 0 else None
            publications, gap = producer.push(timestamp, (0., 0., 0.), (0., 0., 9.8), gps)
            self.assertIsNone(gap)
            for primary, lookahead in publications:
                output = MotionWindow(primary.integrated)
                window = DispatchWindow(primary.gps, output, primary.samples)
                dispatch_window(window, [motion, calibration], lambda *args: None, lambda: None)
        self.assertIsNotNone(output.fallback)
        np.testing.assert_allclose(output.fallback, [[0, 1, 0], [-1, 0, 0], [0, 0, 1]])
        self.assertIsNotNone(output.gyro_bias)
        np.testing.assert_allclose(output.gyro_bias, [0, 0, 0])
        self.assertEqual(output.stable, 1)
        # Completed calibration is not cleared when switching between states4/8.
        calibration.transition(9000, 8)
        self.assertTrue(calibration.window.fallback_ready)
        calibration.transition(10000, 16)
        self.assertFalse(calibration.enabled)
        self.assertFalse(calibration.window.fallback_ready)


if __name__ == '__main__':
    unittest.main()
