"""Ordinary 7b4a78/7b4c04 manager, without the alternate graph backend.

State transitions, gap policy and bias publication are supplied by the root.
Output lookahead is a separate pose, never a second filter prediction.
"""
import copy
from vdr_preintegration import advance_pose
from vdr_quality_manager import valid_pose
from vdr_covariance_prediction import predict as predict_output_covariance


class FilterManager:
    def __init__(self, engine, quality, *, prepare_observation,
                 state_handler, gap_handler, bias_publisher):
        self.engine = engine
        self.quality = quality
        self.prepare_observation = prepare_observation
        self.state_handler = state_handler
        self.gap_handler = gap_handler
        self.bias_publisher = bias_publisher
        self.output = None
        self.output_covariance = None
        self.output_timestamp = None

    @property
    def state(self):
        return None if self.engine is None else self.engine.correction.state

    def install(self, engine):
        self.engine = engine
        self.output = None
        self.output_covariance = None
        self.output_timestamp = None

    def before_predict(self, window):
        if self.engine is not None:
            return self.quality.before_predict(self.engine, window)

    def predict(self, window):
        if self.engine is not None:
            return self.engine.predict(window.integrated)

    def handle_state(self, window):
        self.state_handler(self, window)

    def adjust_for_gap(self, window):
        if self.engine is not None:
            self.gap_handler(self.engine, window)

    def observe(self, window, lookahead):
        if self.engine is None:
            self.output = None
            self.output_covariance = None
            self.output_timestamp = None
            return
        gps, options = self.prepare_observation(window)
        result = self.engine.observe(window.integrated, gps, **options)
        self.output = copy.deepcopy(self.state)
        self.output_covariance = copy.deepcopy(self.engine.correction.covariance)
        self.output_timestamp = window.integrated.timestamp
        if valid_pose(self.output) and lookahead.integrated.count != 0:
            # TMC uncertainty metadata only; never feed this prediction back.
            _, self.output_covariance = predict_output_covariance(self.output,
                self.output_covariance, self.engine.base_noise, lookahead.integrated, self.engine.gravity)
            self.output.pose = advance_pose(self.output.pose, lookahead.integrated,
                                            self.engine.gravity)
            self.output_timestamp = lookahead.integrated.timestamp
        return result

    def publish_bias(self, state):
        self.bias_publisher(self.engine, state)
