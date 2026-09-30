import unittest
import math
from vdr_session import VdrSession, SessionConfiguration
from vdr_state_controller import StateConfiguration
from vdr_window_observation import FilterGps


def create_session(callback=None):
    return VdrSession(SessionConfiguration(
        StateConfiguration(False, True, True, True, 10000, 5., False, .01, .1),
        0, False, False, False, 0, 600),
        dict(means=[0.]*55, scales=[1.]*55, coefficients=[0.]*55, bias=0.),
        on_output=callback)


class VdrSessionTest(unittest.TestCase):
    def test_session_owns_continuous_input_to_output_and_feedback(self):
        outputs = []
        session, other = create_session(outputs.append), create_session()
        for step in range(1100):
            timestamp = 1000 + step*40
            gps = (FilterGps(timestamp, 120.+step*.000003, 30., speed=7.2,
                             direction=0., position_sigma=1.) if step % 25 == 0 else None)
            session.push(timestamp, (0., 0., 0.), (.2, .3, math.sqrt(9.80665**2-.13)), gps)
        self.assertGreater(len(outputs), 20)
        self.assertEqual(session.manager.state, 8)
        self.assertGreater(session.producer.gyro_history.total_weight, 20)
        self.assertEqual(other.manager.state, 1)
        self.assertEqual(len(other.history), 0)
        self.assertTrue(all(math.isfinite(o['longitude']) for o in outputs))
        outputs[-1]['longitude'] = -999
        self.assertNotEqual(session.output['longitude'], -999)

    def test_invalid_sensor_input_is_rejected_before_mutation(self):
        session = create_session()
        for timestamp, gyro, acceleration in (
            (1790000000000, [0, 0, 0], [0, 0, 9.8]),
            (1000, [0, float('nan'), 0], [0, 0, 9.8]),
            (1000, [0, 0, 0], [0, 9.8])):
            with self.assertRaises(ValueError):
                session.push(timestamp, gyro, acceleration)
        self.assertEqual(session.producer.last_timestamp, -1)
        self.assertEqual(session.manager.state, 1)


if __name__ == '__main__':
    unittest.main()
