"""Validate history statistics primitives against pinned original ARM64 code."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_D0, UC_ARM64_REG_D8, UC_ARM64_REG_W22
from tunnel_history_matching import population_deviation, vector_norm, accepts_statistics


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    machine.mem_map(0x6a8000, 4096)
    machine.mem_map(0x7c000, 4096)
    machine.mem_map(0x1000000, 65536)
    address, size = 0x6a889c, 144
    segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
    offset = address - segment['p_vaddr']
    machine.mem_write(address, segment.data()[offset:offset + size])
    for address, size in ((0x6a8b58, 28), (0x7c3e0, 8)):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        machine.mem_write(address, segment.data()[offset:offset + size])
    rng = random.Random(20260928)
    cases = [[], [0.], [180.], [0.] * 20, [-180., 180.]]
    cases += [[rng.uniform(-360, 360) for _ in range(rng.randrange(2, 200))] for _ in range(1000)]
    for values in cases:
        machine.mem_write(0x1000000, struct.pack('<QQ', 0x1000100, 0x1000100 + len(values) * 8))
        if values:
            machine.mem_write(0x1000100, struct.pack('<' + 'd' * len(values), *values))
        for address, function in ((0x6a889c, population_deviation), (0x6a8908, vector_norm)):
            machine.reg_write(UC_ARM64_REG_X0, 0x1000000)
            machine.reg_write(UC_ARM64_REG_LR, 0x100f000)
            machine.emu_start(address, 0x100f000, count=10000)
            assert machine.reg_read(UC_ARM64_REG_PC) == 0x100f000
            expected = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            assert math.isclose(expected, function(values), abs_tol=1e-10, rel_tol=1e-12)
    deviations = [0., math.nextafter(20., 0.), 20., math.nextafter(20., math.inf), math.nan, math.inf]
    correlations = [-1., math.nextafter(.8, 0.), .8, math.nextafter(.8, 1.), 1., math.nan]
    for deviation in deviations:
        for correlation in correlations:
            for register, value in ((UC_ARM64_REG_D0, correlation), (UC_ARM64_REG_D8, deviation)):
                machine.reg_write(register, struct.unpack('<Q', struct.pack('<d', value))[0])
            machine.emu_start(0x6a8b58, 0x6a8b74, count=7)
            assert machine.reg_read(UC_ARM64_REG_PC) == 0x6a8b74
            assert bool(machine.reg_read(UC_ARM64_REG_W22)) == accepts_statistics(deviation, correlation)
    print(f'{len(cases) * 2} native/Python statistics comparisons and 36 acceptance boundary comparisons passed. Full history data flow and navigation NOT verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
