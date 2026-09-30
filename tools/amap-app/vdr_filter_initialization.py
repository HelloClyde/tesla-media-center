"""Default variances +7d5080 and matrix reset +7d51f8."""
import numpy as np

# Gyro, acceleration, gyro bias, accel bias, mounting rotation, auxiliary.
DEFAULT_NOISE_VARIANCES = (1e-4, 1e-2, 1e-8, 1e-7, 1e-8, 1e-8)
# Attitude, velocity, position, gyro bias, accel bias, mounting, auxiliary.
DEFAULT_STATE_VARIANCES = (1., 2.5, 20., 1e-7, 1e-4, 1e-3, 1e-3)


def initial_covariances(state_variances=DEFAULT_STATE_VARIANCES,
                        noise_variances=DEFAULT_NOISE_VARIANCES):
    if len(state_variances) != 7 or len(noise_variances) != 6:
        raise ValueError('Expected seven state and six process-noise groups')
    return (np.diag(np.repeat(state_variances, 3)),
            np.diag(np.repeat(noise_variances, 3)))
