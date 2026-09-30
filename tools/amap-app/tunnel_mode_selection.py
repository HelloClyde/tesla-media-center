"""Partial translation of pinned libamaploc.so+0x45dfbc.

This selects an algorithm ID, not a vehicle position. Numeric state/type meanings
beyond the observed comparisons remain unverified. Not enabled in TMC.
"""
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Selection:
    status: int
    algorithm_id: int
    extra: int


def enforce_tunnel_dr(current: Selection, state_code: int,
                      candidate_ids: Sequence[int], algorithm_types: Mapping[int, int],
                      context_available: bool = True) -> Selection:
    """Port the observed branch order, keeping unknown numeric enums explicit.

    The native candidate buffer stores IDs as doubles; this typed boundary accepts
    already-decoded integer IDs. Candidate order is significant, not score-sorted.
    """
    if not context_available or state_code != 5:
        return current
    current_type = algorithm_types.get(current.algorithm_id)
    if current_type is None or current_type & 0xff == 2:
        return current
    for candidate in candidate_ids:
        candidate_type = algorithm_types.get(candidate)
        if candidate_type is not None and candidate_type & 0xff == 2:
            return Selection(1, candidate, 0)
    return current
