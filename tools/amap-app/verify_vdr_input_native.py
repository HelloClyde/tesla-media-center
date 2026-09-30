"""Run the complete original input-correction function without arithmetic hooks."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0
from vdr_state_expression import corrected_input


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    machine.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        machine.mem_write(segment['p_vaddr'], segment.data())
    machine.mem_map(0x1000000, 65536)
    rng = random.Random(20260928)
    for case in range(1000):
        operands = [[rng.uniform(-100, 100) for _ in range(n)] for n in (3, 9, 3, 3, 9, 3, 3)]
        for index, (offset, values) in enumerate(zip((8, 16, 24, 32, 56, 64, 72), operands)):
            pointer = 0x1001000 + index * 256
            machine.mem_write(pointer, struct.pack('<' + 'd' * len(values), *values))
            machine.mem_write(0x1000000 + offset, struct.pack('<Q', pointer))
        machine.reg_write(UC_ARM64_REG_X0, 0x1000800)
        machine.reg_write(UC_ARM64_REG_X1, 0x1000000)
        machine.reg_write(UC_ARM64_REG_SP, 0x100e000)
        machine.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x100f100)
        machine.reg_write(UC_ARM64_REG_LR, 0x100f000)
        machine.emu_start(0x7cfe5c, 0x100f000, count=20000)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x100f000
        expected = struct.unpack('<3d', machine.mem_read(0x1000800, 24))
        actual = corrected_input(*operands)
        assert actual == expected, (case, actual, expected)
    print('1000 complete original input-correction calls matched Python exactly, without hooks. Physical field provenance and full navigation remain unverified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
