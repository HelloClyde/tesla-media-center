"""Compare complete +7bc014 across continuous IMU/GPS windows."""
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
    UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_heading_alignment import HeadingAlignment


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
    uc.mem_map(0x2000000, 0x1000000)
    heap = 0x2000000

    def runtime(machine, address, size, user):
        nonlocal heap
        if address in (0x9f2fb0, 0x9f2b50):
            length = machine.reg_read(UC_ARM64_REG_X0)
            result = heap
            heap += (length + 15) & ~15
            assert heap < 0x3000000
            machine.mem_write(result, bytes(length))
            machine.reg_write(UC_ARM64_REG_X0, result)
        elif address in (0x9f2bd0, 0x9f2c90):
            dst = machine.reg_read(UC_ARM64_REG_X0)
            src = machine.reg_read(UC_ARM64_REG_X1)
            length = machine.reg_read(UC_ARM64_REG_X2)
            if length:
                machine.mem_write(dst, bytes(machine.mem_read(src, length)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90):
        uc.hook_add(UC_HOOK_CODE, runtime, begin=address, end=address)

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    def call(entry, x1, x2=0, x3=0, x4=0):
        for register, value in ((UC_ARM64_REG_X0, 0x1000000),
                                (UC_ARM64_REG_X1, x1), (UC_ARM64_REG_X2, x2), (UC_ARM64_REG_X3, x3), (UC_ARM64_REG_X4, x4),
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
    calls = 0
    for rate in (5., 25.):
        heap = 0x2000000
        uc.mem_write(0x1000000, bytes(0x1000))
        align = HeadingAlignment(rate, 3)
        write(0x1000008, 'd', rate)
        write(0x1000010, '2i', align.block_size, 3)
        write(0x1000018, 'd', .95)
        write(0x1000048, 'd', .95)
        write(0x1000078, 'Q', 0x1001000)
        write(0x1001000, '3Q', 0x1002000, 0x1002b40, 0x1002b40)
        write(0x1001018, '3Q', 0x1003000, 0x1003b40, 0x1003b40)
        angles = [(i / 180.) * math.pi for i in range(360)]
        write(0x1002000, '360d', *map(math.sin, angles))
        write(0x1003000, '360d', *map(math.cos, angles))
        for step in range(24):
            speed = [20 + 4 * math.sin(i * .16 + step * .02) for i in range(76)]
            theta = math.radians(32)
            acc, gyro = [], []
            for i in range(75):
                longitudinal = (speed[i+1] - speed[i]) * rate
                lateral = .3 * math.sin(i * .31)
                ax = longitudinal * math.cos(theta) + lateral * math.sin(theta)
                ay = longitudinal * math.sin(theta) - lateral * math.cos(theta)
                acc.append((ax + rng.uniform(-.01,.01), ay + rng.uniform(-.01,.01), 9.8))
                gyro.append((0., 0., -lateral / speed[i]))
            speed = speed[:75]
            if step % 7 == 0:
                acc, gyro, speed = [(0.,0.,9.8)]*75, [(0.,0.,0.)]*75, [20.]*75
            acc = [v for v in acc for _ in range(align.block_size)]
            gyro = [v for v in gyro for _ in range(align.block_size)]
            speed = [v for v in speed for _ in range(align.block_size)]
            for header, address, values, stride in ((0x1000100,0x1004000,acc,24),
                (0x1000200,0x1007000,gyro,24),(0x1000300,0x100a000,speed,8)):
                write(header,'3Q',address,address+len(values)*stride,address+len(values)*stride)
                flat = [item for row in values for item in row] if stride==24 else values
                write(address,f'{len(flat)}d',*flat)
            write(0x1000400,'3Q',0x1000600,0x1000600,0x1000700)
            expected = align.advance(acc,gyro,speed)
            assert call(0x7bc014,0x1000100,0x1000200,0x1000300,0x1000400)==1
            begin,end = struct.unpack('<2Q',uc.mem_read(0x1000400,16))
            if expected is None:
                assert begin==end, (rate,step,'unexpected native candidate')
            else:
                assert end-begin==24, (rate,step,'missing native candidate')
                candidate = struct.unpack('<i4x2d',uc.mem_read(begin,24))
                assert candidate[0]==expected[0], (rate,step,candidate,expected)
                for a,b in zip(candidate[1:],expected[1:]):
                    assert math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-9), (rate,step,a,b)
                accepted += 1
            for address,history in ((0x1000018,align.history.speed),(0x1000048,align.history.model)):
                weight = struct.unpack('<d',uc.mem_read(address+8,8))[0]
                total = struct.unpack('<d',uc.mem_read(address+0x28,8))[0]
                assert math.isclose(weight,history.weight,rel_tol=1e-12,abs_tol=1e-12)
                assert total==history.total_weight, (rate,step,total,history.total_weight)
            calls += 1
    assert accepted > 0
    print(f'{calls} complete native alignment windows matched; {accepted} returned cached/updated candidates; history weights matched. Upstream alignment and navigation fusion excluded.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
