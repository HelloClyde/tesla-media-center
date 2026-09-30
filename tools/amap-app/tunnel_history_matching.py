"""History trend gate reconstructed from libamaploc+6a892c.

Sequence field semantics still need tracing. Do not feed arbitrary H5 headings
to this function or treat its boolean result as a navigation position.
"""
import math


def wrap_angle(value):
    if not math.isfinite(value):
        raise ValueError('Finite angle required')
    # Preserve both -180 and +180 as in +69f424, unlike a modulo wrapper.
    while value > 180:
        value -= 360
    while value < -180:
        value += 360
    return value


def population_deviation(values):
    """+6a889c: population, not sample, standard deviation."""
    if len(values) < 2:
        return 0.0
    total = 0.0
    for value in values:
        total += value
    mean = total / len(values)
    total = 0.0
    for value in values:
        total += (value - mean) * (value - mean)
    return math.sqrt(total / len(values))


def vector_norm(values):
    """+6a8908, using fused accumulation where Python provides it."""
    total = 0.0
    for value in values:
        total = math.fma(value, value, total) if hasattr(math, 'fma') else value * value + total
    return math.sqrt(total)


def history_statistics(first, second):
    """Return deviation and correlation before the native acceptance branch.

    Zero norms produce NaN as the native floating-point divides do. Preserve
    this for later branch validation rather than silently inventing a policy.
    """
    if not first or len(first) != len(second):
        return None
    a = [wrap_angle(v - first[0]) for v in first]
    b = [wrap_angle(v - second[0]) for v in second]
    differences = [wrap_angle(x - y) for x, y in zip(a, b)]
    na, nb = vector_norm(a), vector_norm(b)
    correlation = 0.0
    for x, y in zip(a, b):
        correlation += (x * y / na / nb) if na and nb else math.nan
    return population_deviation(differences), correlation


def accepts_statistics(deviation, correlation):
    """Native +6a8b58..6a8b70; unordered comparisons reject the match."""
    return deviation < 20.0 and correlation > 0.8


def history_matches(first, second):
    statistics = history_statistics(first, second)
    return statistics is not None and accepts_statistics(*statistics)
