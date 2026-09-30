"""Validated native-frame transport batches for VdrSession.

Not a browser conversion: axes, units, datum and relative clock must already
match the session contract. Validate the entire batch before any integration.
"""
import copy
import math
from vdr_window_observation import FilterGps


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


class NativeVdrBatch:
    def __init__(self, session):
        self.session = session
        self.last_timestamp = -1

    def consume_batch(self, samples):
        if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
            raise ValueError('Expected 1..100 native-frame samples')
        prepared = []
        previous = self.last_timestamp
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError('Invalid sample')
            timestamp = sample.get('timestamp')
            gyro, accel = sample.get('gyro'), sample.get('acceleration')
            if type(timestamp) is not int or not max(previous, 0) < timestamp < 2**31:
                raise ValueError('Sample timestamps must be increasing relative milliseconds')
            for vector in (gyro, accel):
                if not isinstance(vector, list) or len(vector) != 3 or not all(map(number, vector)):
                    raise ValueError('Sensor vectors must contain three finite numbers')
            previous = timestamp
            gps = None
            data = sample.get('gps')
            if data is not None:
                if not isinstance(data, dict):
                    raise ValueError('Invalid GPS record')
                required = ('longitude', 'latitude', 'altitude', 'speed', 'direction', 'position_sigma')
                if not all(number(data.get(key)) for key in required):
                    raise ValueError('GPS fields must be finite native-unit values')
                fix_time = data.get('timestamp')
                if (type(fix_time) is not int or not 0 < fix_time <= timestamp or
                        not -180 <= data['longitude'] <= 180 or not -90 <= data['latitude'] <= 90 or
                        data['position_sigma'] < 0 or data['speed'] < 0 or
                        not (data['direction'] == -1 or 0 <= data['direction'] < 360)):
                    raise ValueError('GPS record outside valid range')
                gps = FilterGps(fix_time, data['longitude'], data['latitude'],
                    altitude=data['altitude'], speed=data['speed'], direction=data['direction'],
                    position_sigma=data['position_sigma'])
            prepared.append((timestamp, gyro[:], accel[:], gps))
        for values in prepared:
            self.session.push(*values)
        self.last_timestamp = previous
        return dict(state=self.session.manager.state, output=copy.deepcopy(self.session.output),
                    accepted=len(prepared), timestamp=previous)
