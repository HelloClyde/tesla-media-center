"""Fixed-size feature histories at776bec, statistics776930..776be8."""
import struct
import numpy as np


def quality_features(histories):
    """7772b8: 12 native histories in manager address order -> 55 features."""
    first = histories[0]
    result = [first.maximum() - first.minimum(), first.deviation()]
    for history in histories[1:5]:
        result.extend((history.mean(), history.deviation()))
    result.append(histories[5].maximum() - histories[5].minimum())
    result.extend(history.mean() for history in histories[6:])
    return np.concatenate(result)


class FeatureHistory:
    def __init__(self, capacity, dimensions):
        if capacity <= 0 or dimensions <= 0:
            raise ValueError('Feature history dimensions must be positive')
        self.capacity, self.dimensions = capacity, dimensions
        self.reset()

    def reset(self):
        self.values = np.zeros((self.capacity, self.dimensions))
        self.index = 0
        self.ready = False

    def push(self, values):
        if len(values) < self.dimensions:
            return
        self.values[self.index] = values[:self.dimensions]
        self.index += 1
        if self.index >= self.capacity:
            self.ready = True
            self.index = 0

    def mean(self):
        result = np.zeros(self.dimensions)
        if self.ready:
            for row in self.values:
                result += row
            result /= self.capacity
        return result

    def deviation(self):
        result = np.zeros(self.dimensions)
        if self.ready:
            mean = self.mean()
            for row in self.values:
                result += (row - mean) ** 2
            result = np.sqrt(result / self.capacity)
        return result

    def maximum(self):
        bound = struct.unpack('<d', struct.pack('<Q', 0xc0f86a0000000000))[0]
        result = np.full(self.dimensions, bound)
        if self.ready:
            for row in self.values:
                for i, value in enumerate(row):
                    # Native b.pl retains the accumulator for unordered results.
                    if result[i] < value:
                        result[i] = value
        return result

    def minimum(self):
        bound = struct.unpack('<d', struct.pack('<Q', 0x40f86a0000000000))[0]
        result = np.full(self.dimensions, bound)
        if self.ready:
            for row in self.values:
                for i, value in enumerate(row):
                    # Native b.le also skips unordered comparisons.
                    if result[i] > value:
                        result[i] = value
        return result
