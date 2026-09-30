"""GPS-speed/IMU direction scoring from libamaploc +7bc524.

Inputs are already rotated and block-averaged by the caller. Scores alone
are not accepted headings: +7bc6f8/+7bcba4 and history acceptance follow.
"""
import math
from vdr_weighted_history import WeightedHistory


class HeadingHistory:
    """History acceptance portion of +7bc014, after both scoring calls.

    required_weight is supplied by the native constructor's configuration;
    no guessed production threshold is substituted here.
    """
    def __init__(self, required_weight):
        self.required_weight = required_weight
        self.model = WeightedHistory(.95)
        self.speed = WeightedHistory(.95)
        self.candidate = None

    def reset(self):
        self.model.reset()
        self.speed.reset()
        self.candidate = None

    def add(self, model_scores, speed_scores):
        if select_heading(model_scores, speed_scores) is None:
            return self.candidate
        self.speed.add(speed_scores)
        self.model.add(model_scores)
        if self.model.total_weight < self.required_weight:
            return self.candidate
        model = self.model.mean()
        speed = self.speed.mean()
        if model is not None and speed is not None:
            candidate = select_heading(model, speed)
            if candidate is not None:
                self.candidate = candidate
        return self.candidate


class HeadingAlignment:
    """Complete +7bc014 window processing, with already aligned IMU inputs.

    Sensor alignment and assembling the timed window are upstream. Native
    callers provide exactly 75 blocks; explicitly reject other sizes here.
    """
    def __init__(self, rate, required_weight):
        self.rate = rate
        self.block_size = int(25. / rate) if abs(rate) >= 1e-6 else 0
        self.history = HeadingHistory(required_weight)

    def advance(self, acceleration, gyro, speed):
        n = len(speed)
        block = self.block_size
        if block <= 0 or n != 75 * block or len(acceleration) != n or len(gyro) != n:
            raise ValueError('Expected three matching vectors containing 75 complete blocks')
        accel = [[sum(acceleration[i][axis] for i in range(start, start + block)) / block
                  for axis in range(3)] for start in range(0, n, block)]
        speeds = [sum(speed[start:start + block]) / block for start in range(0, n, block)]
        lateral = [sum(gyro[i][2] * speed[i] for i in range(start, start + block)) / block
                   for start in range(0, n, block)]
        rms = math.sqrt(sum(a[0] * a[0] + a[1] * a[1] for a in accel) / 75.)
        change = sum(abs(speeds[i + 1] - speeds[i]) * self.rate for i in range(74)) / 74.
        if rms < .4 or change < .2:
            return self.history.candidate
        speed_scores = heading_scores(accel, speeds, self.rate)
        rows = [(a[0], -a[1], 1., v, g) for a, v, g in zip(accel, speeds, lateral)]
        model = model_heading_scores(rows)
        if model is None:
            return self.history.candidate
        return self.history.add(model, speed_scores)


def model_heading_scores(rows):
    """+7bc6f8: eliminate nuisance coefficients, then score 360 directions.

    Caller columns are (rotated_ax, -rotated_ay, 1, speed, rotated_gz*speed).
    None means the original matrix pivot checks reject this window.
    """
    if len(rows) != 75 or any(len(row) != 5 for row in rows):
        raise ValueError('Expected a 75 by 5 input matrix')
    gram = [[sum(row[r] * row[c] for row in rows) for c in range(5)]
            for r in range(4)]
    if abs(gram[3][3]) <= 1e-15:
        return None
    old = [row[:] for row in gram]
    for r in range(3):
        for c in range(5):
            gram[r][c] -= old[3][c] * old[r][3] / old[3][3]
    if abs(gram[2][2]) < 2.220446049250313e-16:
        return None
    old = [row[:] for row in gram]
    for r in range(2):
        for c in range(5):
            gram[r][c] -= old[2][c] * old[r][2] / old[2][2]
    old = [row[:] for row in gram]
    for c in range(5):
        gram[3][c] -= old[2][c] * old[3][2] / old[2][2]
    scores = []
    for angle in range(360):
        radians = (angle / 180.) * math.pi
        sine, cosine = math.sin(radians), math.cos(radians)
        bias = -(gram[2][1] * cosine + gram[2][0] * sine + gram[2][4]) / gram[2][2]
        factor = -(gram[3][1] * cosine + gram[3][0] * sine + gram[3][4]) / gram[3][3]
        error = 0.
        for row in rows:
            residual = row[1] * cosine + row[0] * sine
            residual += row[2] * bias
            residual += row[3] * factor
            residual += row[4]
            error += residual * residual
        scores.append(error / 75.)
    return scores


def heading_scores(acceleration, speed, rate):
    if len(acceleration) != 75 or len(speed) != 75:
        raise ValueError('Native scoring expects 75 block-averaged samples')
    changes = [(speed[i + 1] - speed[i]) * rate for i in range(74)]
    scores = []
    for angle in range(360):
        radians = (angle / 180.) * math.pi
        sine, cosine = math.sin(radians), math.cos(radians)
        error = 0.
        for i in range(74):
            projected = acceleration[i][1] * sine + acceleration[i][0] * cosine
            residual = projected - changes[i]
            error += residual * residual
        scores.append(error / 74.)
    return scores


def heading_extrema(scores):
    """Circular turning points and prominence flags from +7bcce8."""
    if len(scores) != 360 or not all(math.isfinite(v) for v in scores):
        raise ValueError('Expected 360 finite scores')
    minimum, maximum, start = 10000., -1., -1
    for i, value in enumerate(scores):
        maximum = max(maximum, value)
        if value < minimum:
            minimum, start = value, i
    if start < 0:
        raise ValueError('Native extrema requires a score below its 10000 sentinel')
    extrema = [(start, minimum)]
    previous = start
    rising = True
    for offset in range(1, 361):
        current = (start + offset) % 360
        if rising and scores[current] < scores[previous]:
            extrema.append((previous, scores[previous]))
            rising = False
        elif not rising and scores[current] > scores[previous]:
            extrema.append((previous, scores[previous]))
            rising = True
        previous = current
    threshold = (maximum - minimum) * .15
    return [(index, value,
             abs(value - extrema[i - 1][1]) > threshold and
             abs(value - extrema[(i + 1) % len(extrema)][1]) > threshold)
            for i, (index, value) in enumerate(extrema)]


def select_heading(model_scores, speed_scores):
    """+7bcba4 returns a candidate or None; caller owns history acceptance."""
    if len(speed_scores) != 360:
        raise ValueError('Expected 360 speed scores')
    extrema = heading_extrema(model_scores)
    if len(extrema) != 4 or extrema[0][1] > 1000.:
        return None
    first, second = extrema[0], extrema[2]
    a, b = speed_scores[first[0]], speed_scores[second[0]]
    if a >= b + b:
        return second[0], second[1], b
    if b >= a + a:
        return first[0], first[1], a
    return None
