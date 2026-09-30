"""Filter-side binding semantics from 7d6dd8 and 7d6df4.

The linked source is owned by the caller. This does not synthesize the App's
external positioning module or its type-2 readiness state.
"""
from dataclasses import dataclass


@dataclass
class ObservationSource:
    kind: int
    heading_enabled: bool = False


class ObservationBinding:
    def __init__(self, flag1=False, flag2=False):
        self.source = None
        self.flag1, self.flag2 = flag1, flag2

    def bind(self, source):
        self.source = source
        if source.kind == 2:
            self.flag1 = True

    def refresh(self):
        if self.source is not None and self.source.kind == 2:
            self.flag2 = self.source.heading_enabled
        return self.flag1, self.flag2
