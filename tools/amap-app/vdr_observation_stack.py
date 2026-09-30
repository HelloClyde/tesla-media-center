"""Observation assembly +7d6748..+7d68a8 before the correction call."""
import numpy as np


def stack_observations(blocks):
    matrices, residuals, variances = [], [], []
    for matrix, residual, variance in blocks:
        matrix = np.asarray(matrix, dtype=float)
        residual = np.asarray(residual, dtype=float).reshape(-1)
        variance = np.asarray(variance, dtype=float).reshape(-1)
        if matrix.shape != (residual.size, 21) or variance.size != residual.size:
            raise ValueError('Observation block dimensions disagree')
        matrices.append(matrix)
        residuals.append(residual)
        variances.append(variance)
    if not matrices:
        return None
    return np.vstack(matrices), np.concatenate(residuals), np.diag(np.concatenate(variances))
