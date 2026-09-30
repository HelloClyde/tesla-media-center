"""Regression checks for the disassembled window observer contract."""

import unittest

from vdr_window_dispatch import DispatchWindow, SamplePair, dispatch_window


class WindowDispatchTest(unittest.TestCase):
    def test_replay_then_publish_and_no_duplicate_delivery(self):
        events = []

        class Observer:
            enabled = True
            replay_enabled = True

            def __init__(self, name):
                self.name = name

            def sample(self, timestamp, gps, first, second):
                events.append((self.name, 'sample', timestamp, gps, first, second))

            def publish(self, payload):
                events.append((self.name, 'publish', payload))

        observers = [Observer(name) for name in ('a', 'b', 'c', 'd')]
        observers[1].enabled = False
        observers[2].replay_enabled = False
        window = DispatchWindow('fix', 'window', [
            SamplePair(100, 'g1', 'a1'), SamplePair(120, 'g2', 'a2')])

        def trailing(gps, samples):
            events.append(('trailing', gps, len(samples)))

        self.assertTrue(dispatch_window(window, observers, trailing, lambda: 'invalid'))
        self.assertEqual(events, [
            ('a', 'sample', 100, 'invalid', 'g1', 'a1'),
            ('a', 'sample', 120, 'fix', 'g2', 'a2'),
            ('d', 'sample', 100, 'invalid', 'g1', 'a1'),
            ('d', 'sample', 120, 'fix', 'g2', 'a2'),
            ('a', 'publish', 'window'), ('c', 'publish', 'window'),
            ('d', 'publish', 'window'), ('trailing', 'fix', 2),
        ])
        self.assertEqual(window.samples, [])
        self.assertFalse(dispatch_window(window, observers, trailing, lambda: 'invalid'))
        self.assertEqual(len(events), 8)


if __name__ == '__main__':
    unittest.main()
