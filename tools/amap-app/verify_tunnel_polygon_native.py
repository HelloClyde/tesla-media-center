"""Differential test of unchanged ARM64 polygon math; only libc hypot is hooked."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *
from tunnel_polygon_matching import polygon_distance, select_polygon


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for base in (0x691000, 0x7a000, 0x7b000, 0x9f4000):
        machine.mem_map(base, 4096)
    machine.mem_map(0x1000000, 65536)
    for address, size in ((0x6918f4, 0x370), (0x7a120, 8), (0x7b9c0, 8)):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        machine.mem_write(address, segment.data()[offset:offset + size])

    def read_double(register):
        return struct.unpack('<d', struct.pack('<Q', machine.reg_read(register)))[0]

    def hypot(uc, address, size, context):
        value = math.hypot(read_double(UC_ARM64_REG_D0), read_double(UC_ARM64_REG_D1))
        uc.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', value))[0])
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    # ELF relocation at a28b68 resolves the 9f4050 PLT entry to libc hypot.
    machine.hook_add(UC_HOOK_CODE, hypot, begin=0x9f4050, end=0x9f4050)
    square = [(0., 0.), (10., 0.), (10., 10.), (0., 10.)]
    cases = [(p, v) for v in (square, square[::-1], square + [square[-1]], [], square[:2], [(0., 0.)] * 3)
             for p in ((5., 5.), (0., 0.), (10.01, 5.), (30., 5.), (30.00001, 5.), (-1., -1.))]
    rng = random.Random(20260928)
    for _ in range(1000):
        x, y = rng.uniform(-100, 100), rng.uniform(-100, 100)
        w, h = rng.uniform(.001, 100), rng.uniform(.001, 100)
        polygon = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        if rng.choice((False, True)):
            polygon.reverse()
        cases.append(((rng.uniform(-200, 200), rng.uniform(-200, 200)), polygon))
    largest_error = 0
    for point, vertices in cases:
        machine.mem_write(0x1000100, struct.pack('<dd', *point))
        machine.mem_write(0x1000200, struct.pack('<QQQ', 0x1000300, 0x1000300 + 16 * len(vertices), 0x1000300 + 16 * len(vertices)))
        if vertices:
            machine.mem_write(0x1000300, b''.join(struct.pack('<dd', *v) for v in vertices))
        machine.reg_write(UC_ARM64_REG_X0, 0x1000100)
        machine.reg_write(UC_ARM64_REG_X1, 0x1000200)
        machine.reg_write(UC_ARM64_REG_SP, 0x100f000)
        machine.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x1000000)
        machine.reg_write(UC_ARM64_REG_LR, 0x1000800)
        machine.emu_start(0x691afc, 0x1000800, count=10000)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x1000800
        expected = read_double(UC_ARM64_REG_D0)
        actual = polygon_distance(point, vertices)
        largest_error = max(largest_error, abs(actual - expected))
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9), (point, vertices, actual, expected)
    assert select_polygon((30., 5.), [square, square], 20.) == (0, 20., True)
    assert not select_polygon((30.00001, 5.), [square], 20.)[2]
    assert select_polygon((0., 0.), [[]], 20.)[0] is None
    print(f'{len(cases)} native/Python polygon comparisons passed; max error={largest_error:.3g}. Selection boundary checks passed; full navigation NOT verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
