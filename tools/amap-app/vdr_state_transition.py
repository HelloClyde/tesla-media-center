"""Research translation of manager 77ae18 and observer 7799dc.

Callbacks are explicit: their filter/calibration side effects must be supplied
by their own translated implementations, not inferred from state names.
"""
from dataclasses import dataclass
from typing import Callable


def signed32(value):
    value &= 0xffffffff
    return value - 0x100000000 if value >= 0x80000000 else value


@dataclass
class ObserverActivation:
    mask: int
    enabled: bool = False
    started: int = -1

    def transition(self, timestamp, state, on_enable, on_disable):
        active = signed32(self.mask & state) > 0
        if not self.enabled and active:
            self.started = signed32(timestamp)
            self.enabled = True
            on_enable(timestamp)
        elif self.enabled and not active:
            self.enabled = False
            self.started = -1
            on_disable(timestamp)


@dataclass
class ManagerState:
    state: int
    state_since: int
    reason: int
    reason_since: int

    def transition(self, state: int, timestamp: int, reason: int, forced: int,
                   notify: Callable, observers: list[Callable],
                   trailing: Callable):
        state, timestamp, reason = map(signed32, (state, timestamp, reason))
        same = self.state == state
        if same and self.reason == reason:
            return
        state_age = (signed32(timestamp - self.state_since)
                     if not same and self.state_since > 0 else 0)
        reason_age = (signed32(timestamp - self.reason_since)
                      if self.reason_since > 0 else 0)
        notify(timestamp, (reason | state << 8) & 0xffffffff,
               (self.reason | self.state << 8) & 0xffffffff,
               state_age, reason_age, forced)
        if same:
            self.reason, self.reason_since = reason, timestamp
            return
        # 0x40 is a notification-only request in this routine.
        if state == 0x40:
            return
        previous = self.state
        self.state, self.state_since = state, timestamp
        self.reason, self.reason_since = reason, timestamp
        for observer in observers:
            observer(timestamp, state)
        trailing(timestamp, previous, state)
