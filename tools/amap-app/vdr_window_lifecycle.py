"""Root77b308/77b628 window ordering with explicit manager dependencies.

The filter manager owns prediction, state restoration and lookahead publication.
Callbacks remain required for native producer bias feedback and output handling.
"""
from vdr_window_dispatch import dispatch_window
from vdr_initialization_history import record_from_window
from vdr_quality_manager import valid_pose


class WindowLifecycle:
    def __init__(self, *, manager, observers, records, filter_manager,
                 transition, observer_tail, empty_gps_factory,
                 bias_feedback, output_status, publish_output, retain_window=None):
        self.manager = manager
        self.observers = observers
        self.records = records
        self.filter = filter_manager
        self.transition = transition
        self.observer_tail = observer_tail
        self.empty_gps_factory = empty_gps_factory
        self.bias_feedback = bias_feedback
        self.output_status = output_status
        self.publish_output = publish_output
        self.timestamp = -1
        self.retain_window = retain_window

    def process(self, window, lookahead):
        payload = window.payload
        timestamp = payload.integrated.timestamp
        self.timestamp = timestamp
        if self.manager.state == 1:
            self.transition(2, timestamp, 0, 1)
        dispatch_window(window, self.observers, self.observer_tail, self.empty_gps_factory)
        self.records.append(record_from_window(payload))
        if self.retain_window is not None:
            self.retain_window(payload)
        self.filter.before_predict(payload)
        self.filter.predict(payload)
        previous = self.manager.state
        self.filter.handle_state(payload)
        # 77b738 optional inflation is skipped only on full reinitialization.
        reinitialized = ((previous == 4 and self.manager.state in (8,16)) or
                         (previous == 8 and self.manager.state == 16))
        if self.manager.state in (8,16,32) and not reinitialized:
            self.filter.adjust_for_gap(payload)
        self.filter.observe(payload, lookahead)
        self.filter.publish_bias(self.manager.state)
        if self.manager.state in (8,16,32) and valid_pose(self.filter.state):
            self.bias_feedback(timestamp, self.filter.state.pose.gyro_bias,
                               self.filter.state.pose.accel_bias)
        self.output_status(timestamp, payload)
        self.publish_output(timestamp, payload)
