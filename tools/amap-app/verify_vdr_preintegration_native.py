"""Compare complete +7cf594 state updates; only libc services are replaced."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_D0, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_preintegration import Preintegration, PoseState, advance_pose, rotation_and_right_jacobian

MATRICES = ('rotation_gyro_derivative', 'velocity_gyro_derivative', 'velocity_accel_derivative',
            'position_gyro_derivative', 'position_accel_derivative', 'rotation')
VECTORS = ('velocity', 'position', 'gyro_bias', 'accel_bias', 'mean_gyro', 'mean_accel')


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    uc.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        uc.mem_write(segment['p_vaddr'], segment.data())
    uc.mem_map(0x1000000, 65536)

    def libc(machine, address, size, user):
        x0, x1, x2 = [machine.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        if address == 0x9f2bd0:
            machine.mem_write(x0, bytes(machine.mem_read(x1, x2)))
        elif address == 0x9f2ba0:
            machine.mem_write(x0, bytes([x1 & 255]) * x2)
        elif address == 0x9f2e20:
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            machine.mem_write(x0, struct.pack('<d', math.sin(value)))
            machine.mem_write(x1, struct.pack('<d', math.cos(value)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2bd0, 0x9f2ba0, 0x9f2e20):
        uc.hook_add(UC_HOOK_CODE, libc, begin=address, end=address)
    rng = random.Random(20260928)
    largest_error = 0.
    calls = 0
    for trajectory in range(50):
        state = Preintegration()
        if trajectory % 2:
            state.rotation = rotation_and_right_jacobian([rng.uniform(-1, 1) for _ in range(3)])[0]
            for name in MATRICES[:5]:
                setattr(state, name, [[rng.uniform(-1, 1) for _ in range(3)] for _ in range(3)])
            for name in VECTORS[:4]:
                setattr(state, name, [rng.uniform(-1, 1) for _ in range(3)])
        uc.mem_write(0x1000000, bytes(0x270))
        for index, name in enumerate(MATRICES):
            matrix = getattr(state, name)
            uc.mem_write(0x1000000 + index * 72, struct.pack('<9d', *(matrix[r][c] for c in range(3) for r in range(3))))
        for index, name in enumerate(VECTORS):
            uc.mem_write(0x10001b0 + index * 24, struct.pack('<3d', *getattr(state, name)))
        timestamp = 1000
        for sample in range(20):
            timestamp += rng.choice([0, 1, 20, 40, 100])
            gyro = [rng.uniform(-2, 2) for _ in range(3)]
            accel = [rng.uniform(-10, 10) for _ in range(3)]
            if trajectory % 5 == 0:
                gyro = [0., 0., 0.]
            elif trajectory % 5 == 1:
                gyro = [v + 1e-10 for v in state.gyro_bias]
            uc.mem_write(0x1001008, struct.pack('<IIfffB', 2, timestamp, *gyro, 0))
            uc.mem_write(0x1001108, struct.pack('<IIfffB', 1, timestamp, *accel, 0))
            for register, value in ((UC_ARM64_REG_X0, 0x1000000), (UC_ARM64_REG_X1, 0x1001000),
                                    (UC_ARM64_REG_X2, 0x1001100), (UC_ARM64_REG_SP, 0x100e000),
                                    (UC_ARM64_REG_LR, 0x100f000), (UC_ARM64_REG_TPIDR_EL0, 0x100f100)):
                uc.reg_write(register, value)
            uc.emu_start(0x7cf594, 0x100f000, count=200000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x100f000
            advanced = state.advance(timestamp, gyro, accel)
            assert struct.unpack('<3f', uc.mem_read(0x1000250, 12)) == tuple(state.latest_gyro)
            assert bool(uc.reg_read(UC_ARM64_REG_X0)) == advanced
            expected_values = []
            for name in MATRICES:
                matrix = getattr(state, name)
                expected_values.extend((name, matrix[r][c]) for c in range(3) for r in range(3))
            for name in VECTORS:
                expected_values.extend((name, value) for value in getattr(state, name))
            actual_values = struct.unpack('<72d', uc.mem_read(0x1000000, 576))
            for (name, expected), actual in zip(expected_values, actual_values):
                largest_error = max(largest_error, abs(actual - expected))
                assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (trajectory, sample, name, actual, expected)
            assert struct.unpack('<iii', uc.mem_read(0x1000260, 12)) == (state.timestamp, state.initial_timestamp, state.count)
            pose = PoseState(
                rotation=rotation_and_right_jacobian([rng.uniform(-2, 2) for _ in range(3)])[0],
                velocity=[rng.uniform(-20, 20) for _ in range(3)],
                position=[rng.uniform(-1000, 1000) for _ in range(3)],
                gyro_bias=[v + rng.uniform(-.01, .01) for v in state.gyro_bias],
                accel_bias=[v + rng.uniform(-.1, .1) for v in state.accel_bias])
            gravity = [rng.uniform(-10, 10) for _ in range(3)]
            packed = [pose.rotation[r][c] for c in range(3) for r in range(3)]
            for name in ('velocity', 'position', 'gyro_bias', 'accel_bias'):
                packed.extend(getattr(pose, name))
            uc.mem_write(0x1002000, struct.pack('<21d', *packed))
            uc.mem_write(0xa524a8, struct.pack('<3d', *gravity))
            uc.reg_write(UC_ARM64_REG_X0, 0x1002000)
            uc.reg_write(UC_ARM64_REG_X1, 0x1000000)
            uc.reg_write(UC_ARM64_REG_SP, 0x100e000)
            uc.reg_write(UC_ARM64_REG_LR, 0x100f000)
            uc.emu_start(0x78b9b8, 0x100f000, count=200000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x100f000
            updated = advance_pose(pose, state, gravity)
            expected_pose = [updated.rotation[r][c] for c in range(3) for r in range(3)]
            for name in ('velocity', 'position', 'gyro_bias', 'accel_bias'):
                expected_pose.extend(getattr(updated, name))
            for index, (expected, actual) in enumerate(zip(expected_pose, struct.unpack('<21d', uc.mem_read(0x1002000, 168)))):
                largest_error = max(largest_error, abs(actual - expected))
                assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (trajectory, sample, 'pose', index, actual, expected)
            calls += 1
    print(f'{calls} complete native IMU preintegration steps and {calls} complete pose-propagation calls matched Python; max absolute error={largest_error:.3g}. Only memcpy/memset/sincos substituted. Global navigation and TMC integration not verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
