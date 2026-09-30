"""Scalar equivalent of +7937e8/+79382c in the VDR state update.

Names describe expression operands, not yet established physical quantities.
Keep separate multiplies/adds: the original instructions do not fuse them.
"""
import math
from decimal import Decimal, localcontext


def _fma(a, b, c):
    if hasattr(math, 'fma'):
        return math.fma(a, b, c)
    # Research fallback for Python before 3.13: preserve one final rounding.
    with localcontext() as context:
        context.prec = 2200
        return float(Decimal.from_float(a) * Decimal.from_float(b) + Decimal.from_float(c))


def state_component(first, second, scaled, scale, correction, weight, time_squared):
    return ((first + second) + scale * scaled) + (weight * correction) * time_squared


def transform_vector(column_major_matrix, vector):
    """+37b754/+37b788: 3x3 column-major product, original sum order."""
    if len(column_major_matrix) != 9 or len(vector) != 3:
        raise ValueError('Expected a 3x3 matrix and a three-component vector')
    return tuple(column_major_matrix[row] * vector[0] +
                 (column_major_matrix[row + 3] * vector[1] +
                  column_major_matrix[row + 6] * vector[2]) for row in range(3))


def corrected_input(base, matrix1, reference1, input1, matrix2, reference2, input2):
    """Reconstruct +7cfe5c input expression without assigning sensor names.

    +7cff50 copies base then adds the first matrix product; +7cfee4
    subsequently adds the second. +38c334 subtracts reference minus input.
    First two matrix rows use SIMD FMLA; the last uses scalar FMUL/FADD.
    """
    if any(len(v) != 3 for v in (base, reference1, input1, reference2, input2)):
        raise ValueError('Expected three-component vectors')
    first = transform_vector_simd(matrix1, tuple(a - b for a, b in zip(reference1, input1)))
    second = transform_vector_simd(matrix2, tuple(a - b for a, b in zip(reference2, input2)))
    return tuple(second[i] + (first[i] + base[i]) for i in range(3))


def transform_vector_simd(matrix, vector):
    """Whole native 3-vector evaluation, including the two-row SIMD path."""
    scalar = transform_vector(matrix, vector)
    return tuple(_fma(matrix[row + 6], vector[2],
                      _fma(matrix[row + 3], vector[1], matrix[row] * vector[0]))
                 for row in range(2)) + (scalar[2],)
