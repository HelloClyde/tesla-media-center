"""Initialized-filter observation lifecycle from +7d64a0.

Native process-global backup recovery/publication is outside this object.
Input motion classification and sensor frames must already be native-convention.
"""
import copy
from dataclasses import dataclass, field
from vdr_filter_update import CorrectionFilter
from vdr_preintegration import Preintegration, signed32
from vdr_preintegration_composition import compose


@dataclass
class ObservationLifecycle:
    correction: CorrectionFilter
    last_timestamp: int = -1
    installation_variance: float = .001
    stationary_integrated: Preintegration = field(default_factory=Preintegration)
    stationary_rotations: list = field(default_factory=list)

    def observe(self, integrated, gps, *, calibration_state=1, config=0,
                direction=-1., motion=1, motion_detail=0, gyro=(0., 0., 0.),
                flag1=False, flag2=False, force=False, extra_position=None):
        self.correction.transition_calibration(calibration_state > 0, self.installation_variance)
        timestamp = signed32(integrated.timestamp)
        if timestamp <= self.last_timestamp:
            return None
        state = self.correction.state
        if not (state.frame.east_scale > 0 or state.flags):
            return None
        self.last_timestamp = timestamp
        # Reanchoring changes position/frame but leaves the rotation unchanged.
        self.correction.reanchor()
        reference = None
        if self.correction.calibrate:
            if motion != 0:
                self.stationary_integrated = Preintegration(timestamp=-1, initial_timestamp=-1)
                self.stationary_rotations.clear()
            elif flag1:
                if motion_detail >= 2:
                    self.stationary_integrated = compose(self.stationary_integrated, integrated)
            elif len(self.stationary_rotations) <= 3:
                self.stationary_rotations.append(copy.deepcopy(self.correction.state.pose.rotation))
            else:
                reference = self.stationary_rotations[1]
        return self.correction.correct_prepared_frame(
            gps, config=config, direction=direction, motion=motion, motion_detail=motion_detail,
            gyro=gyro, flag1=flag1, flag2=flag2, force=force,
            stationary_reference=reference, stationary_integrated=self.stationary_integrated,
            extra_position=extra_position)
