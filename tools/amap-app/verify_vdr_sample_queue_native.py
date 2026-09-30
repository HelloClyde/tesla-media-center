"""Differential check of the complete native exact-sample queue operation."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import *
from vdr_sample_queue import take_exact_sample


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
    for section in elf.iter_sections():
        if section['sh_type'] == 'SHT_RELA':
            for relocation in section.iter_relocations():
                if relocation['r_info_type'] == 1027:  # R_AARCH64_RELATIVE
                    machine.mem_write(relocation['r_offset'], struct.pack('<Q', relocation['r_addend']))
    machine.mem_map(0x1000000, 65536)
    rng = random.Random(20260928)
    for case in range(1000):
        count = case % 13
        records = []
        for index in range(count):
            record = bytearray(32)
            struct.pack_into('<QIIfffB', record, 0, 0xa17fb0, 1 + index % 2,
                             rng.choice([0, 1, 0x7fffffff, 0x80000000, 0xffffffff]),
                             rng.random(), rng.random(), rng.random(), index % 2)
            records.append(bytes(record))
        timestamp = (struct.unpack_from('<I', records[case % count], 12)[0]
                     if count and case % 3 else 12345)
        output = bytes([0x5a]) * 32
        expected, remaining, result = take_exact_sample(records, timestamp, output)
        machine.mem_write(0x1000000, struct.pack('<QQQ', 0x1001000,
                          0x1001000 + count * 32, 0x1001000 + count * 32))
        if records:
            machine.mem_write(0x1001000, b''.join(records))
        machine.mem_write(0x1000800, output)
        for register, value in ((UC_ARM64_REG_X0, 0), (UC_ARM64_REG_X1, 0x1000000),
                                (UC_ARM64_REG_X2, timestamp), (UC_ARM64_REG_X3, 0x1000800),
                                (UC_ARM64_REG_SP, 0x100e000), (UC_ARM64_REG_TPIDR_EL0, 0x100f100),
                                (UC_ARM64_REG_LR, 0x100f000)):
            machine.reg_write(register, value)
        machine.emu_start(0x788568, 0x100f000, count=20000)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x100f000
        assert bool(machine.reg_read(UC_ARM64_REG_X0)) == expected, case
        assert bytes(machine.mem_read(0x1000800, 32)) == result, case
        begin, end = struct.unpack('<QQ', machine.mem_read(0x1000000, 16))
        assert end - begin == len(remaining) * 32, case
        # Vector assignment preserves each destination object's vptr/padding.
        for index, record in enumerate(remaining):
            assert bytes(machine.mem_read(begin + index * 32 + 8, 21)) == record[8:29], case
    print('1000 native exact-sample queue calls matched Python, including queue mutation; no hooks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
