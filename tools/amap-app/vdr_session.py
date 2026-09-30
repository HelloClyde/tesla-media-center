"""Reusable ordinary VDR session for native-coordinate paired samples.

This composes the translated base manager, not the alternate graph backend or
road matcher. Browser conversion and production publication are separate.
"""
import copy
import math
import numpy as np
from vdr_position_observation import position_observation
from collections import deque
from dataclasses import dataclass
from vdr_window_producer import WindowProducer
from vdr_prepared_window import prepare_window, empty_gps
from vdr_window_lifecycle import WindowLifecycle
from vdr_motion_observer import MotionObserver
from vdr_calibration_observer import CalibrationObserver
from vdr_orientation_quality import OrientationQualityObserver
from vdr_direction_observer import DirectionObserver
from vdr_state_transition import ManagerState
from vdr_state_controller import StateConfiguration, StateController
from vdr_quality_manager import QualityManager
from vdr_filter_manager import FilterManager
from vdr_gap_policy import GapPolicy
from vdr_window_observation import WindowObservation
from vdr_initialization_replay import ReplayWindow
from vdr_output_status import OutputStatus


@dataclass(frozen=True)
class SessionConfiguration:
    states: StateConfiguration
    observation_config: int
    observation_flag1: bool
    observation_flag2: bool
    relaxed_gap: bool
    unstable_delay: int
    # Explicit integration retention limit, not asserted to be native capacity.
    history_limit: int


class VdrSession:
    def __init__(self, configuration, quality_parameters, *, on_output=None):
        if configuration.history_limit < 2:
            raise ValueError('History must retain at least two windows')
        if configuration.unstable_delay != 0:
            raise ValueError('Nonzero unstable-delay reference is not yet verified')
        self.configuration = configuration
        self.on_output = on_output
        self.manager = ManagerState(1, -1, 0, -1)
        self.observers = [OrientationQualityObserver(), DirectionObserver(),
                          MotionObserver(), CalibrationObserver()]
        self.quality = QualityManager(quality_parameters)
        self.records = deque(maxlen=configuration.history_limit)
        self.history = deque(maxlen=configuration.history_limit)
        self.events = deque(maxlen=100)
        self.output = None
        self.published_auxiliary = [0., 0., 0.]
        self.observation = WindowObservation(config=configuration.observation_config,
            flag1=configuration.observation_flag1, flag2=configuration.observation_flag2)
        self.controller = StateController(self.manager, self.records, self.history,
            self.quality, configuration.states,
            can_replay=lambda t: any(w.integrated.timestamp == t for w in self.history),
            transition=self.transition, notify_reinitialized=self.reinitialized,
            reset_manager=self.after_quality_reset)
        self.filter = FilterManager(None, self.quality, prepare_observation=self.observation,
            state_handler=self.controller, gap_handler=GapPolicy(enabled=configuration.relaxed_gap),
            bias_publisher=self.publish_auxiliary)
        self.producer = WindowProducer(on_publish=self.consume_window)
        self.status = OutputStatus()
        self.lifecycle = WindowLifecycle(manager=self.manager, observers=self.observers,
            records=self.records, filter_manager=self.filter, transition=self.transition,
            observer_tail=self.default_observer_tail, empty_gps_factory=empty_gps,
            bias_feedback=self.producer.feedback_bias, retain_window=self.retain,
            output_status=self.update_status, publish_output=self.publish)

    @staticmethod
    def default_observer_tail(*args):
        # 76dadc -> 77a6c8 initializes an empty observer group; 77a6e4/77a728
        # perform no work until observers are registered with that group.
        pass

    @staticmethod
    def after_quality_reset():
        # 7778b4 is implemented by QualityManager.reset in StateController.
        pass

    def transition(self, state, timestamp, reason, forced):
        self.manager.transition(state, timestamp, reason, forced,
            lambda *event: self.events.append(('state', event)),
            [observer.transition for observer in self.observers], self.default_observer_tail)

    def reinitialized(self, timestamp, flag):
        # Base native slot30 (77c42c) is empty; retain a diagnostic event.
        self.events.append(('reinitialized', (timestamp, flag)))

    def publish_auxiliary(self, engine, state):
        # 77b76c copies root+2b0 (pose auxiliary), not its gyro bias.
        if engine is not None and state in (8, 16):
            self.published_auxiliary = list(engine.correction.state.auxiliary)

    def retain(self, window):
        gps, options = self.observation(window)
        self.history.append(ReplayWindow(copy.deepcopy(window.integrated), gps,
                                         options, direction=window.direction))

    def consume_window(self, primary, lookahead):
        self.lifecycle.process(prepare_window(primary), lookahead)

    def update_status(self, timestamp, window):
        for event in self.status.update(self.manager.state, timestamp,
                self.quality.scores.ready, unstable_delay=self.configuration.unstable_delay,
                reference_timestamp=self.manager.state_since, window=window):
            self.events.append(('status', (timestamp, event)))

    def publish(self, timestamp, window):
        self.output = None
        if not self.status.active or self.filter.output is None:
            return
        state = self.filter.output
        if state.frame.east_scale <= 0:
            return
        coordinates = state.frame.unproject(*state.pose.position)
        if (not all(math.isfinite(v) for v in coordinates) or
                not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90):
            self.events.append(('invalid-output', (timestamp,)))
            return
        # TMC-derived uncertainty for route eligibility, not an APK accuracy field.
        h, _, _ = position_observation(state, *coordinates, 1.)
        horizontal = (h @ self.filter.output_covariance @ h.T)[:2, :2]
        if not np.isfinite(horizontal).all():
            self.events.append(('invalid-uncertainty', (timestamp,)))
            return
        variance = np.linalg.eigvalsh((horizontal + horizontal.T) / 2)
        if variance[0] < -1e-6:
            return
        estimated_accuracy = math.sqrt(5.991 * max(0., float(variance[-1])))
        vx, vy = state.pose.velocity[:2]
        speed = math.hypot(vx, vy)
        if not math.isfinite(speed):
            return
        self.output = dict(timestamp=self.filter.output_timestamp,
            longitude=coordinates[0], latitude=coordinates[1], altitude=coordinates[2],
            state=self.manager.state, missing_fix=bool(window.missing_fix),
            quality=self.quality.scores.primary, source='amap-vdr-ordinary',
            estimated_accuracy=estimated_accuracy, speed=speed,
            heading=(math.degrees(math.atan2(vx, vy)) % 360) if speed > .3 else None)
        if self.on_output is not None:
            self.on_output(copy.deepcopy(self.output))

    def push(self, timestamp, gyro, acceleration, gps=None):
        """gyro rad/s and acceleration including gravity m/s², native axes.

        This entry expects already paired sensor samples and internal relative
        millisecond timestamps. It does not accept epoch time or GPS as IMU.
        """
        if not isinstance(timestamp, int) or not 0 < timestamp < 2**31:
            raise ValueError('Expected positive signed-32 relative milliseconds')
        if len(gyro) != 3 or len(acceleration) != 3 or not all(
                math.isfinite(value) for value in (*gyro, *acceleration)):
            raise ValueError('Expected finite paired three-axis sensor readings')
        return self.producer.push(timestamp, gyro, acceleration, gps,
                                  relaxed_gap=self.configuration.relaxed_gap)
