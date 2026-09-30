"""Compare original frame setup/project/unproject; only libc cos substituted."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X8,
    UC_ARM64_REG_D0, UC_ARM64_REG_D1, UC_ARM64_REG_D2,
    UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_local_frame import LocalFrame, METRES_PER_DEGREE


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

    def cos(machine, address, size, user):
        value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
        machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', math.cos(value)))[0])
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, cos, begin=0x9f2e30, end=0x9f2e30)

    def call(entry, vector):
        for register, value in ((UC_ARM64_REG_X0, 0x1000000), (UC_ARM64_REG_X1, 0x1001000),
                                (UC_ARM64_REG_X8, 0x1002000), (UC_ARM64_REG_SP, 0x100e000),
                                (UC_ARM64_REG_LR, 0x100f000), (UC_ARM64_REG_TPIDR_EL0, 0x100f100)):
            uc.reg_write(register, value)
        for register, value in zip((UC_ARM64_REG_D0, UC_ARM64_REG_D1, UC_ARM64_REG_D2), vector):
            uc.reg_write(register, struct.unpack('<Q', struct.pack('<d', value))[0])
        uc.emu_start(entry, 0x100f000, count=10000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x100f000

    rng = random.Random(20260928)
    for case in range(1000):
        origin = (rng.uniform(-170, 170), rng.uniform(-89.9, 89.9), rng.uniform(-100, 5000))
        frame = LocalFrame(*origin)
        uc.mem_write(0x1001000, struct.pack('<3d', *origin))
        call(0x78b238, (0., 0., 0.))
        assert struct.unpack('<3d', uc.mem_read(0x1000110, 24)) == origin
        assert struct.unpack('<2d', uc.mem_read(0x1000128, 16)) == (frame.east_scale, METRES_PER_DEGREE)
        geo = tuple(a + b for a, b in zip(origin, (rng.uniform(-.02, .02), rng.uniform(-.02, .02), rng.uniform(-100, 100))))
        call(0x78b278, geo)
        local = frame.project(*geo)
        assert struct.unpack('<3d', uc.mem_read(0x1002000, 24)) == local, case
        call(0x78b2e0, local)
        assert struct.unpack('<3d', uc.mem_read(0x1002000, 24)) == frame.unproject(*local), case
    print('1000 native frame initializations and 2000 forward/inverse conversions matched Python exactly with host cos; datum provenance and full navigation remain unverified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
