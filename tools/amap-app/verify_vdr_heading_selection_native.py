"""Compare original circular extrema and candidate selection, not mocks."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_heading_alignment import heading_extrema, select_heading


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
    uc.mem_map(0x1000000, 0x20000)
    uc.mem_map(0x2000000, 0x100000)
    heap = 0x2000000

    def runtime(machine, address, size, user):
        nonlocal heap
        if address in (0x9f2fb0, 0x9f2b50):
            length = machine.reg_read(UC_ARM64_REG_X0)
            result = heap
            heap += (length + 15) & ~15
            assert heap < 0x2100000
            machine.mem_write(result, bytes(length))
            machine.reg_write(UC_ARM64_REG_X0, result)
        elif address == 0x9f2bd0:
            dst = machine.reg_read(UC_ARM64_REG_X0)
            src = machine.reg_read(UC_ARM64_REG_X1)
            length = machine.reg_read(UC_ARM64_REG_X2)
            if length:
                machine.mem_write(dst, bytes(machine.mem_read(src, length)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0):
        uc.hook_add(UC_HOOK_CODE, runtime, begin=address, end=address)

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    def call(entry, x1, x2=0):
        for register, value in ((UC_ARM64_REG_X0, 0x1000000),
                                (UC_ARM64_REG_X1, x1), (UC_ARM64_REG_X2, x2),
                                (UC_ARM64_REG_SP, 0x101e000),
                                (UC_ARM64_REG_LR, 0x101f000),
                                (UC_ARM64_REG_TPIDR_EL0, 0x101f100)):
            uc.reg_write(register, value)
        try:
            uc.emu_start(entry, 0x101f000, count=2000000)
        except Exception as error:
            raise RuntimeError(f'PC={uc.reg_read(UC_ARM64_REG_PC):x}, LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x101f000
        return uc.reg_read(UC_ARM64_REG_X0)

    rng = random.Random(20260928)
    accepted = 0
    for case in range(500):
        heap = 0x2000000
        phase = rng.randrange(360)
        model = [2. + math.cos(2 * math.radians(i - phase)) for i in range(360)]
        if case % 5 == 0:
            model = [rng.uniform(0, 10) for _ in range(360)]
        elif case % 5 == 1:
            model = [round(v, 1) for v in model]
        elif case % 5 == 2:
            model = [5.] * 360
        speeds = [rng.uniform(.01, 5) for _ in range(360)]
        # Boundary cases at score ratio 2, equality, and all-zero speed scores.
        expected_extrema = heading_extrema(model)
        if len(expected_extrema) == 4 and case % 3 == 0:
            a, b = expected_extrema[0][0], expected_extrema[2][0]
            speeds[a], speeds[b] = ((2., 1.), (1., 2.), (0., 0.))[case % 9 // 3]
        write(0x1000000, '2Q', 0x1001000, 360)
        write(0x1000100, '2Q', 0x1002000, 360)
        write(0x1001000, '360d', *model)
        write(0x1002000, '360d', *speeds)
        write(0x1000200, '3Q', 0x1004000, 0x1004000, 0x1007000)
        assert call(0x7bcce8, 0x1000200) == 1
        begin, end = struct.unpack('<2Q', uc.mem_read(0x1000200, 16))
        actual = []
        for offset in range(begin, end, 24):
            index, value, flag = struct.unpack('<i4xdB', uc.mem_read(offset, 17))
            actual.append((index, value, bool(flag)))
        assert actual == expected_extrema, (case, actual, expected_extrema)
        write(0x1000300, '3Q', 0x1008000, 0x1008000, 0x1008100)
        result = call(0x7bcba4, 0x1000100, 0x1000300)
        expected = select_heading(model, speeds)
        assert bool(result) == (expected is not None), case
        begin, end = struct.unpack('<2Q', uc.mem_read(0x1000300, 16))
        if expected is not None:
            assert end - begin == 24
            assert struct.unpack('<i4x2d', uc.mem_read(begin, 24)) == expected, case
            accepted += 1
        else:
            assert begin == end
    print(f'500 extrema and 500 complete selection calls matched exactly; {accepted} accepted. Only allocation/copy runtime hooks; model scoring/history excluded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
