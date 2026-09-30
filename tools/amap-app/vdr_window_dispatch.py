"""Research port of libamaploc 779a34 / 77b360..77b3dc.

This preserves observer replay ordering only; it is not a navigation engine.
GPS and sample payloads remain caller-owned, with no inferred sensor units.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class SamplePair:
    timestamp: int
    first: Any
    second: Any


@dataclass
class DispatchWindow:
    gps: Any
    payload: Any
    samples: list[SamplePair] = field(default_factory=list)
    processed: bool = False


class WindowObserver(Protocol):
    enabled: bool
    replay_enabled: bool

    def sample(self, timestamp: int, gps: Any, first: Any, second: Any) -> None: ...

    def publish(self, payload: Any) -> None: ...


def replay_samples(observer: WindowObserver, window: DispatchWindow,
                   empty_gps_factory: Callable[[], Any]) -> None:
    """779a34: replay every sample; only the last gets window GPS."""
    if not observer.replay_enabled or not observer.enabled:
        return
    empty_gps = empty_gps_factory()
    for index, sample in enumerate(window.samples):
        gps = window.gps if index == len(window.samples) - 1 else empty_gps
        observer.sample(sample.timestamp, gps, sample.first, sample.second)


def dispatch_window(window: DispatchWindow, observers: list[WindowObserver],
                    trailing_callback: Callable[[Any, list[SamplePair]], None],
                    empty_gps_factory: Callable[[], Any]) -> bool:
    """77b360..77b3dc: replay all observers, publish all, then finalize.

    The trailing callback is the native root+d30 object's slot+18. Its
    implementation is intentionally not guessed here. The caller must keep
    native registration order and continue the manager state machine afterward.
    """
    if window.processed:
        return False
    for observer in observers:
        replay_samples(observer, window, empty_gps_factory)
    for observer in observers:
        if observer.enabled:
            observer.publish(window.payload)
    trailing_callback(window.gps, window.samples)
    window.processed = True
    window.samples.clear()
    return True
