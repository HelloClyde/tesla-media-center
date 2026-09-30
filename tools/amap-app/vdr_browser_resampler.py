"""TMC browser boundary: interpolate measured IMU onto the core's 25 Hz clock.

This is an integration adapter, not a claimed translation of an APK function.
Only bracketed measurements are interpolated. No extrapolation across missing
events and no GPS-to-IMU synthesis. The maximum permissible gap is explicit.
GPS association remains the caller's responsibility after resampling.
"""
from vdr_batch import number


class BrowserResampler:
    interval = 40

    def __init__(self, *, maximum_gap):
        if type(maximum_gap) is not int or not 40 <= maximum_gap <= 200:
            raise ValueError('Expected an explicit maximum gap of 40..200 ms')
        self.maximum_gap = maximum_gap
        self.previous = None
        self.next_timestamp = None
        self.failed = False

    def push(self, sample):
        if self.failed:
            raise ValueError('Sampling interrupted; create a new inertial session')
        timestamp = sample.get('timestamp')
        if type(timestamp) is not int or not 0 < timestamp < 2**31:
            raise ValueError('Expected positive relative milliseconds')
        current = {'timestamp': timestamp}
        for key in ('gyro', 'acceleration'):
            vector = sample.get(key)
            if not isinstance(vector, (list, tuple)) or len(vector) != 3 or not all(map(number, vector)):
                raise ValueError('Expected finite three-axis measurements')
            current[key] = list(vector)
        if self.previous is None:
            self.previous = current
            self.next_timestamp = timestamp + self.interval
            return [{key: value[:] if isinstance(value, list) else value for key, value in current.items()}]
        gap = timestamp - self.previous['timestamp']
        if gap <= 0:
            raise ValueError('Measurements must arrive in timestamp order')
        if gap > self.maximum_gap:
            self.failed = True
            raise ValueError('Sensor gap exceeds the interpolation limit')
        outputs = []
        while self.next_timestamp <= timestamp:
            fraction = (self.next_timestamp-self.previous['timestamp']) / gap
            result = {'timestamp': self.next_timestamp}
            for key in ('gyro', 'acceleration'):
                # Weighted endpoints avoid overflow in b-a for finite values.
                result[key] = [(1-fraction)*a + fraction*b
                               for a, b in zip(self.previous[key], current[key])]
            outputs.append(result)
            self.next_timestamp += self.interval
        self.previous = current
        return outputs
