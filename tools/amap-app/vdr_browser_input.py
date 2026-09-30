"""Browser recording -> post-calibration VDR input.

Installation rotation and acceleration sign are explicit calibration inputs.
No resampling, invented GPS fields, or claim of a verified vehicle profile.
The caller must validate cadence before using the ordinary 25 Hz observers.
"""
import math
from vdr_batch import number


class BrowserInput:
    def __init__(self, rotation, acceleration_sign, accuracy_to_sigma):
        if (len(rotation) != 3 or any(len(row) != 3 for row in rotation)
                or not all(number(v) for row in rotation for v in row)):
            raise ValueError('Expected finite installation rotation')
        for i in range(3):
            for j in range(3):
                dot = sum(rotation[i][k] * rotation[j][k] for k in range(3))
                if abs(dot - (1 if i == j else 0)) > 1e-6:
                    raise ValueError('Installation rotation must be orthonormal')
        a, b, c = rotation
        determinant = (a[0]*(b[1]*c[2]-b[2]*c[1])
                       - a[1]*(b[0]*c[2]-b[2]*c[0])
                       + a[2]*(b[0]*c[1]-b[1]*c[0]))
        if abs(determinant - 1) > 1e-6:
            raise ValueError('Installation rotation must preserve handedness')
        if type(acceleration_sign) is not int or acceleration_sign not in (-1, 1):
            raise ValueError('Acceleration sign must be explicitly calibrated')
        if not number(accuracy_to_sigma) or accuracy_to_sigma <= 0:
            raise ValueError('Accuracy conversion must be explicit and positive')
        self.rotation = [list(row) for row in rotation]
        self.acceleration_sign = acceleration_sign
        self.accuracy_to_sigma = accuracy_to_sigma
        self.last_timestamp = -1

    def convert(self, sample, fix=None):
        elapsed = sample.get('elapsed')
        if not number(elapsed) or elapsed < 0:
            raise ValueError('Invalid monotonic receipt time')
        timestamp = math.floor(elapsed) + 1
        if not self.last_timestamp < timestamp < 2**31:
            raise ValueError('Relative millisecond timestamps must increase')
        def vector(key, sign):
            values = sample.get(key)
            if not isinstance(values, (list, tuple)) or len(values) != 3 or not all(map(number, values)):
                raise ValueError('Expected three finite sensor components')
            return [sign * sum(row[k]*values[k] for k in range(3)) for row in self.rotation]
        result = dict(timestamp=timestamp, gyro=vector('angularVelocity', 1),
                      acceleration=vector('acceleration', self.acceleration_sign))
        if fix is not None:
            required = ('elapsed', 'longitude', 'latitude', 'accuracy', 'altitude', 'speed')
            if not all(number(fix.get(key)) for key in required):
                raise ValueError('GPS lacks required measured values')
            if not 0 <= fix['elapsed'] <= elapsed:
                raise ValueError('GPS receipt must not be in the future')
            heading = fix.get('heading')
            if heading is not None and (not number(heading) or not 0 <= heading < 360):
                raise ValueError('Invalid browser heading')
            if (abs(fix['longitude']) > 180 or abs(fix['latitude']) > 90
                    or fix['accuracy'] < 0 or fix['speed'] < 0):
                raise ValueError('Invalid GPS range')
            result['gps'] = dict(timestamp=math.floor(fix['elapsed'])+1,
                longitude=fix['longitude'], latitude=fix['latitude'], altitude=fix['altitude'],
                speed=fix['speed'], direction=-1 if heading is None else (90-heading) % 360,
                position_sigma=fix['accuracy']*self.accuracy_to_sigma)
        self.last_timestamp = timestamp
        return result
