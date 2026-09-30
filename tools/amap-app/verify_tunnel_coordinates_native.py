"""Compare the translated coordinate primitive with unchanged ARM64 instructions."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_D0, UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_D3, UC_ARM64_REG_D4, UC_ARM64_REG_D5, UC_ARM64_REG_X8, UC_ARM64_REG_LR, UC_ARM64_REG_PC
from tunnel_local_coordinates import local_coordinates


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    if hashlib.sha256(data).hexdigest() != '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34':
        raise ValueError('Unsupported binary')
    elf = ELFFile(io.BytesIO(data))
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for base in (0x69f000, 0x7b000, 0x1000000):
        machine.mem_map(base, 4096)
    for address, size in ((0x69f404, 32), (0x7bc78, 8)):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        machine.mem_write(address, segment.data()[offset:offset + size])
    rng = random.Random(20260928)
    largest_error = 0
    for _ in range(1000):
        angle0, angle1 = rng.uniform(-180, 180), rng.uniform(-90, 90)
        parameters = (angle0, angle1, math.radians(angle0) + rng.uniform(-.01, .01),
                      math.radians(angle1) + rng.uniform(-.01, .01),
                      rng.uniform(1, 7_000_000), rng.uniform(1, 7_000_000))
        for register, value in zip((UC_ARM64_REG_D0, UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_D3, UC_ARM64_REG_D4, UC_ARM64_REG_D5), parameters):
            machine.reg_write(register, struct.unpack('<Q', struct.pack('<d', value))[0])
        machine.reg_write(UC_ARM64_REG_X8, 0x1000000)
        machine.reg_write(UC_ARM64_REG_LR, 0x1000800)
        machine.emu_start(0x69f404, 0x1000800, count=32)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x1000800
        expected = struct.unpack('<dd', machine.mem_read(0x1000000, 16))
        actual = local_coordinates(*parameters)
        error = max(abs(a - b) for a, b in zip(actual, expected))
        largest_error = max(largest_error, error)
        assert error < 2e-8, (parameters, expected, actual)
    print(f'1000 native/Python coordinate comparisons passed; max error={largest_error:.3g}. Full matcher NOT verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
