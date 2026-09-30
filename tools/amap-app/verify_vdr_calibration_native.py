"""Compare +767e30 with Python, including persistent bias and output flags."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X2, UC_ARM64_REG_X8, UC_ARM64_REG_LR, UC_ARM64_REG_PC,
    UC_ARM64_REG_S0, UC_ARM64_REG_S1, UC_ARM64_REG_S2,
    UC_ARM64_REG_S3, UC_ARM64_REG_S4, UC_ARM64_REG_S5)
from vdr_sample_calibration import calibrate_sample


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
    machine.mem_map(0x1000000, 4096)
    rng = random.Random(20260928)
    calls = 0
    for case in range(500):
        bias = None if case % 2 else tuple(rng.uniform(-10, 10) for _ in range(3))
        machine.mem_write(0x1000100, struct.pack('<B3x3f', bias is not None, *(bias or (0, 0, 0))))
        for step in range(4):
            primary = tuple(rng.uniform(-100, 100) for _ in range(3))
            alternate = tuple(rng.uniform(-100, 100) for _ in range(3))
            if step == 0:
                alternate = (901., 901., 901.)
            elif step == 1:
                alternate = ((900., 901., 901.), (901., 900., 901.),
                             (901., 901., 900.))[case % 3]
            expected, used, bias = calibrate_sample(primary, alternate, bias)
            machine.mem_write(0x1000000, bytes([0x5a]) * 32)
            for register, value in zip((UC_ARM64_REG_S0, UC_ARM64_REG_S1, UC_ARM64_REG_S2,
                                       UC_ARM64_REG_S3, UC_ARM64_REG_S4, UC_ARM64_REG_S5),
                                      primary + alternate):
                machine.reg_write(register, struct.unpack('<I', struct.pack('<f', value))[0])
            for register, value in ((UC_ARM64_REG_X0, 1), (UC_ARM64_REG_X1, 123456),
                                    (UC_ARM64_REG_X2, 0x1000100), (UC_ARM64_REG_X8, 0x1000000),
                                    (UC_ARM64_REG_LR, 0x1000f00)):
                machine.reg_write(register, value)
            machine.emu_start(0x767e30, 0x1000f00, count=200)
            assert machine.reg_read(UC_ARM64_REG_PC) == 0x1000f00
            result = bytes(machine.mem_read(0x1000000, 32))
            assert result[8:16] == struct.pack('<II', 1, 123456)
            assert result[16:28] == struct.pack('<3f', *expected), (case, step)
            assert result[28] == used
            state = bytes(machine.mem_read(0x1000100, 16))
            assert bool(state[0]) == (bias is not None)
            if bias is not None:
                assert state[4:16] == struct.pack('<3f', *bias), (case, step, 'bias')
            calls += 1
    print(f'{calls} native calibration calls matched Python, including sentinel boundaries and state reuse; no hooks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
