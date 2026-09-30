"""Rotation projection +78c764; NumPy SVD replaces native SVD implementation."""
import numpy as np


def normalize_rotation(rotation):
    matrix = np.asarray(rotation, dtype=float)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError('Expected a finite 3x3 rotation matrix')
    maximum, minimum = matrix.max(), matrix.min()
    if abs(maximum) < 1e-30 and abs(maximum-minimum) < 1e-30:
        return matrix.tolist()
    u, _, vt = np.linalg.svd(matrix)
    correction = np.diag([1., 1., np.linalg.det(u)*np.linalg.det(vt)])
    return (u @ correction @ vt).tolist()
