"""Whole7bf980 comparison, including threshold equality and timer recovery."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_LR
from vdr_gyro_quality_gate import GyroQualityGate


def verify(apk):
    with zipfile.ZipFile(apk) as z:
        data = z.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    uc.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        uc.mem_write(segment['p_vaddr'], segment.data())
    uc.mem_map(0x1000000, 0x2000)
    gate = GyroQualityGate()
    uc.mem_write(0x1000000, struct.pack('<2f', 1.5, .25))
    uc.mem_write(0x1000018, struct.pack('<4i', 3000, 1000, -1, -1000))
    sequence = [(1000, (2., 2., 2.)), (4000, (0., 0., 0.)),
                (4001, (0., 0., 0.)), (5000, (2., 2., 2.)),
                (8001, (.25, 0., 0.)), (8002, (.249, 0., 0.))]
    rng = random.Random(738)
    timestamp = 9000
    for _ in range(1000):
        timestamp += rng.choice((20, 3000, 3001))
        sequence.append((timestamp, tuple(rng.choice((0., .25, 1.5, 1.5001, -2., float('nan'))) for _ in range(3))))
    for timestamp, gyro in sequence:
        uc.mem_write(0x100010c, struct.pack('<i3f', timestamp, *gyro))
        uc.reg_write(UC_ARM64_REG_X0, 0x1000000)
        uc.reg_write(UC_ARM64_REG_X1, 0x1000100)
        uc.reg_write(UC_ARM64_REG_LR, 0x1001000)
        uc.emu_start(0x7bf980, 0x1001000, count=1000)
        actual = bool(uc.reg_read(UC_ARM64_REG_X0))
        assert actual == gate.advance(timestamp, gyro), (timestamp, gyro)
        assert struct.unpack('<2i', uc.mem_read(0x1000020, 8)) == (gate.status, gate.last_trigger)
    print(f'{len(sequence)} complete native gyro gate calls matched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
