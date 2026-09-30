"""Compare +7bc524 or +7bc6f8 with allocation/copy runtime substitutes."""
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
    UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_heading_alignment import heading_scores, model_heading_scores


def verify(apk, model=False):
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
    uc.mem_map(0x2000000, 0x100000)
    heap = 0x2000000

    def allocator(machine, address, size, user):
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
        uc.hook_add(UC_HOOK_CODE, allocator, begin=address, end=address)

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    # Constructor's sine/cosine tables, supplied identically to both sides.
    write(0x1000078, 'Q', 0x1001000)
    write(0x1001000, '3Q', 0x1002000, 0x1002b40, 0x1002b40)
    write(0x1001018, '3Q', 0x1003000, 0x1003b40, 0x1003b40)
    angles = [(i / 180.) * math.pi for i in range(360)]
    write(0x1002000, '360d', *map(math.sin, angles))
    write(0x1003000, '360d', *map(math.cos, angles))
    rng = random.Random(20260928)
    max_error = 0.
    rejected = 0
    for case in range(40):
        heap = 0x2000000
        rate = rng.uniform(.5, 25)
        acceleration = [tuple(rng.uniform(-5, 5) for _ in range(3)) for _ in range(75)]
        speed = [rng.uniform(0, 35) for _ in range(75)]
        if case == 0:
            acceleration = [(0., 0., 9.8)] * 75
            speed = [10.] * 75
        write(0x1000008, 'd', rate)
        write(0x1000100, '3Q', 0x1004000, 0x1004000 + 75 * 24, 0x1004000 + 75 * 24)
        write(0x1000200, '3Q', 0x1005000, 0x1005000 + 75 * 8, 0x1005000 + 75 * 8)
        write(0x1000300, '2Q', 0, 0)
        write(0x1004000, '225d', *(v for sample in acceleration for v in sample))
        write(0x1005000, '75d', *speed)
        expected = heading_scores(acceleration, speed, rate) if not model else None
        if model:
            rows = [(a[0], -a[1], 1., v, a[2] * v) for a, v in zip(acceleration, speed)]
            if case == 0:
                rows = [(0., 0., 1., 0., 0.)] * 75
            elif case == 1:
                rows = [(a[0], -a[1], 1., 10., a[2] * 10.) for a in acceleration]
            elif case == 2:
                rows = [(a[0], -a[1], 1., v * 1e-12, a[2] * v * 1e-12)
                        for a, v in zip(acceleration, speed)]
            write(0x1000100, '3Q', 0x1004000, 75, 5)
            write(0x1004000, '375d', *(rows[r][c] for c in range(5) for r in range(75)))
            expected = model_heading_scores(rows)
        for register, value in ((UC_ARM64_REG_X0, 0x1000000),
                                (UC_ARM64_REG_X1, 0x1000100),
                                (UC_ARM64_REG_X2, 0x1000300 if model else 0x1000200),
                                (UC_ARM64_REG_X3, 0x1000300),
                                (UC_ARM64_REG_SP, 0x100e000),
                                (UC_ARM64_REG_LR, 0x100f000),
                                (UC_ARM64_REG_TPIDR_EL0, 0x100f100)):
            uc.reg_write(register, value)
        try:
            uc.emu_start(0x7bc6f8 if model else 0x7bc524, 0x100f000, count=2000000)
        except Exception as error:
            raise RuntimeError(f'Native scoring failed at PC={uc.reg_read(UC_ARM64_REG_PC):x}, LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x100f000
        assert bool(uc.reg_read(UC_ARM64_REG_X0)) == (expected is not None), case
        if expected is None:
            rejected += 1
            continue
        pointer, length = struct.unpack('<2Q', uc.mem_read(0x1000300, 16))
        assert length == 360
        actual = struct.unpack('<360d', uc.mem_read(pointer, 360 * 8))
        for a, b in zip(actual, expected):
            assert math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-12), (case, a, b)
            max_error = max(max_error, abs(a - b))
    print(f'40 complete native {"model" if model else "speed"} scoring calls / {(40-rejected)*360} scores matched Python; {rejected} rejected; max error {max_error:.3g}. Only allocation/copy hooks; history not covered.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--model', action='store_true')
    args = parser.parse_args()
    verify(args.apk, args.model)
