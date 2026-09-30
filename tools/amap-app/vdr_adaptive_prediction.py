"""Adaptive portion of +7d5c20, after ordinary state/covariance prediction."""
import numpy as np
from vdr_covariance_prediction import predict
from vdr_calibration_covariance import inflate_calibration_covariance


def adaptive_inputs(previous, predicted, covariance):
    world_to_vehicle = np.asarray(predicted.calibration).T @ np.asarray(predicted.pose.rotation).T
    velocity = world_to_vehicle @ predicted.pose.velocity
    h = np.zeros((2, 21))
    h[:, 3:6] = world_to_vehicle[1:, :]
    variances = np.diag(h @ covariance @ h.T)
    errors = np.abs(velocity[1:])/np.sqrt(variances)
    motion = np.linalg.norm(np.cross(np.asarray(previous.pose.rotation)[2, :],
                                    np.asarray(predicted.pose.rotation)[2, :]))
    return float(errors[0]), float(errors[1]), float(motion)


def predict_adaptive(state, covariance, base_noise, integrated, gravity, gate):
    predicted, updated = predict(state, covariance, base_noise, integrated, gravity)
    first, second, motion = adaptive_inputs(state, predicted, updated)
    triggered = gate.update(first, second, motion)
    if triggered:
        updated = inflate_calibration_covariance(updated, motion)
    return predicted, updated, triggered
