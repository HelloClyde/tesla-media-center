"""Execute complete +7632c8; host acos/sincos only."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X8, UC_ARM64_REG_D0,
    UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_initial_attitude import align_vectors


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
    def runtime(machine, address, size, user):
        value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
        if address == 0x9f40d0:
            result = math.acos(value) if -1 <= value <= 1 else math.nan
            machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', result))[0])
        else:
            machine.mem_write(machine.reg_read(UC_ARM64_REG_X0), struct.pack('<d', math.sin(value)))
            machine.mem_write(machine.reg_read(UC_ARM64_REG_X1), struct.pack('<d', math.cos(value)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
    for address in (0x9f40d0, 0x9f2e20):
        uc.hook_add(UC_HOOK_CODE, runtime, begin=address, end=address)
    rng = random.Random(20260928)
    cases = [(x, y, z) for x in (0., 0.999e-9, 1e-9, -1e-9)
             for y in (0., 0.999e-9, 1e-9, -1e-9) for z in (-9.8, 0., 9.8)]
    cases += [tuple(rng.uniform(-30, 30) for _ in range(3)) for _ in range(1000)]
    max_error = 0.
    for case, vector in enumerate(cases):
        for register, value in ((UC_ARM64_REG_X8, 0x1000000),
                                (UC_ARM64_REG_SP, 0x100e000),
                                (UC_ARM64_REG_LR, 0x100f000),
                                (UC_ARM64_REG_TPIDR_EL0, 0x100f100)):
            uc.reg_write(register, value)
        for register, value in zip((UC_ARM64_REG_D0, UC_ARM64_REG_D1, UC_ARM64_REG_D2), vector):
            uc.reg_write(register, struct.unpack('<Q', struct.pack('<d', value))[0])
        uc.mem_write(0x1000000, bytes([0x5a]) * 72)
        target = (0., 0., 1.)
        uc.mem_write(0x1001000, struct.pack('<3d', *vector))
        uc.mem_write(0x1001100, struct.pack('<3d', *target))
        uc.reg_write(UC_ARM64_REG_X0, 0x1001000)
        uc.reg_write(UC_ARM64_REG_X1, 0x1001100)
        uc.emu_start(0x7632c8, 0x100f000, count=10000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x100f000
        actual = struct.unpack('<9d', uc.mem_read(0x1000000, 72))
        matrix = align_vectors(vector, target)
        expected = [matrix[r][c] for c in range(3) for r in range(3)]
        for a, b in zip(actual, expected):
            if math.isnan(a) and math.isnan(b): continue
            assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12), (case, vector, actual, expected)
            max_error = max(max_error, abs(a - b))
    print(f'{len(cases)} complete native vector-alignment calls matched Python; max error {max_error:.3g}; host acos/sincos only. Full alignment/fusion not covered.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
