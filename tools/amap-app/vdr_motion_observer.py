"""Connect native motion activation, deferred samples and window publication.

Inputs must already be native-coordinate/unit sensor vectors. This adapter
does not turn geolocation into IMU data or infer browser sensor conversions.
"""
from dataclasses import dataclass, field
import numpy as np
from vdr_motion_classifier import MotionDetector
from vdr_state_transition import ObserverActivation


@dataclass
class MotionWindow:
    integrated: object
    sample_vectors: object = ()
    motion: int = -1
    detail: int = -1
    stable: int = -1
    gyro_bias: object = None
    diagnostics: object = field(default_factory=lambda: np.zeros(7))
    preferred: object = None
    fallback: object = None
    quality: int = -1
    gps: object = None
    direction: float = -1.
    missing_fix: bool = False
    missing_duration: int = 0
    maximum_sample_gap: int = 0


class MotionObserver:
    """Root+97c8 observer, vtable a18658, constructor 779f3c."""
    replay_enabled = True

    def __init__(self, *, estimate_bias=False):
        # Constructor packed constant at 79790: mask=62, start=-1.
        self.activation = ObserverActivation(mask=62)
        self.detector = MotionDetector()
        self.estimate_bias = estimate_bias

    @property
    def enabled(self):
        return self.activation.enabled

    def transition(self, timestamp, state):
        # Native slot0 is an empty callback. Slot8 resets classification only.
        self.activation.transition(timestamp, state, lambda _: None,
                                   lambda _: self.detector.reset())

    def sample(self, timestamp, gps, gyro, accel):
        # 77a0cc widens stored float32 samples before classifier processing.
        gyro = np.asarray(gyro, dtype=np.float32).astype(float)
        accel = np.asarray(accel, dtype=np.float32).astype(float)
        self.detector.classifier.push(gyro, accel)

    def publish(self, payload: MotionWindow):
        result = self.detector.publish(payload.integrated,
                                       estimate_bias=self.estimate_bias,
                                       sample_vectors=payload.sample_vectors)
        payload.motion, payload.detail, payload.stable, bias, payload.diagnostics = result
        # Native writes the output bias only once its accumulated count qualifies.
        if bias is not None:
            payload.gyro_bias = bias
