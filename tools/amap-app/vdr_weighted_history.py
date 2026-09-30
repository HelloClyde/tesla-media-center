"""Decaying vector statistics at +76848c/+7684a4/+7685cc/+7685dc."""


class WeightedHistory:
    def __init__(self, decay):
        self.decay = decay
        self.reset()

    def reset(self):
        self.weight = 0.
        self.total_weight = 0.
        self.values = None

    def add(self, values, weight=1.):
        values = list(values)
        if self.values is not None and len(values) != len(self.values):
            raise ValueError('History vector dimensions must remain constant')
        self.weight = self.weight * self.decay + weight
        if self.values is None:
            self.values = [v * weight for v in values]
        else:
            self.values = [old * self.decay + v * weight
                           for old, v in zip(self.values, values)]
        self.total_weight += weight

    def mean(self):
        # Threshold verified from the constant used by +7685dc.
        if abs(self.weight) < 1e-6:
            return None
        return [v / self.weight for v in self.values]
