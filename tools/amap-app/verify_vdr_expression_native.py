"""Execute original VDR scalar expression with controlled operand buffers."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_D0, UC_ARM64_REG_PC
from vdr_state_expression import state_component, transform_vector


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    machine.mem_map(0x793000, 4096)
    machine.mem_map(0x37b000, 4096)
    machine.mem_map(0x1000000, 65536)
    address, size = 0x7937e8, 112
    segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
    machine.mem_write(address, segment.data()[address-segment['p_vaddr']:address-segment['p_vaddr']+size])
    address, size = 0x37b754, 88
    segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
    machine.mem_write(address, segment.data()[address-segment['p_vaddr']:address-segment['p_vaddr']+size])
    rng = random.Random(20260928)
    for _ in range(1000):
        values = [rng.uniform(-1000, 1000) for _ in range(7)]
        first, second, scaled, scale, correction, weight, time_squared = values
        for offset, pointer, value in ((0x18, 0x1001000, first), (0x28, 0x1001100, second), (0x58, 0x1001200, scaled), (0x98, 0x1001300, correction)):
            machine.mem_write(0x1000000 + offset, struct.pack('<Q', pointer))
            machine.mem_write(pointer, struct.pack('<d', value))
        for offset, value in ((0x68, scale), (0x88, weight), (0xa8, time_squared)):
            machine.mem_write(0x1000000 + offset, struct.pack('<d', value))
        machine.reg_write(UC_ARM64_REG_X0, 0x1000000)
        machine.reg_write(UC_ARM64_REG_X1, 0)
        machine.reg_write(UC_ARM64_REG_SP, 0x100e000)
        machine.reg_write(UC_ARM64_REG_LR, 0x100f000)
        machine.emu_start(0x7937e8, 0x100f000, count=100)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x100f000
        expected = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
        assert expected == state_component(*values), (expected, values)
    for _ in range(1000):
        matrix = [rng.uniform(-100, 100) for _ in range(9)]
        vector = [rng.uniform(-100, 100) for _ in range(3)]
        machine.mem_write(0x1002000, struct.pack('<9d', *matrix))
        machine.mem_write(0x1002100, struct.pack('<3d', *vector))
        results = []
        for row in range(3):
            machine.mem_write(0x1000010, struct.pack('<Q', 0x1002000 + row * 8))
            machine.mem_write(0x1000020, struct.pack('<Q', 0x1002100))
            machine.reg_write(UC_ARM64_REG_X0, 0x1000000)
            machine.reg_write(UC_ARM64_REG_SP, 0x100e000)
            machine.reg_write(UC_ARM64_REG_LR, 0x100f000)
            machine.emu_start(0x37b754, 0x100f000, count=100)
            assert machine.reg_read(UC_ARM64_REG_PC) == 0x100f000
            results.append(struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0])
        assert tuple(results) == transform_vector(matrix, vector)
    print('1000 state expressions and 1000 three-component matrix products matched original ARM64 exactly. Operand provenance and full navigation remain unverified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
