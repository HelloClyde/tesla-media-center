"""Compare complete +7bd500 across continuous device-frame IMU windows."""
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
    UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_attitude_calibration import AttitudeCalibration


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
        elif address in (0x9f40d0, 0x9f2e20):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address == 0x9f40d0:
                result = math.acos(value) if -1 <= value <= 1 else math.nan
                machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d',result))[0])
            else:
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X0),struct.pack('<d',math.sin(value)))
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X1),struct.pack('<d',math.cos(value)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20):
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
    align = AttitudeCalibration()
    base = 0x1000088
    write(base+8,'d',5.)
    write(base+0x10,'2i',5,2)
    write(base+0x18,'d',.95)
    write(base+0x48,'d',.95)
    write(base+0x78,'Q',0x1001000)
    write(0x1000130,'d',.99)
    write(0x1001000,'3Q',0x1002000,0x1002b40,0x1002b40)
    write(0x1001018,'3Q',0x1003000,0x1003b40,0x1003b40)
    angles=[i/180.*math.pi for i in range(360)]
    write(0x1002000,'360d',*map(math.sin,angles))
    write(0x1003000,'360d',*map(math.cos,angles))
    accepted=0
    for step in range(24):
        speeds=[20+4*math.sin(i*.16+step*.02) for i in range(76)]
        theta=math.radians(32)
        acc,gyro=[],[]
        for i in range(75):
            longitudinal=(speeds[i+1]-speeds[i])*5.
            lateral=.3*math.sin(i*.31)
            ax=longitudinal*math.cos(theta)+lateral*math.sin(theta)
            ay=longitudinal*math.sin(theta)-lateral*math.cos(theta)
            acc.append((ax+rng.uniform(-.01,.01),ay+rng.uniform(-.01,.01),9.8))
            gyro.append((0.,0.,-lateral/speeds[i]))
        speeds=speeds[:75]
        if step%7==0:
            acc,gyro,speeds=[(.01,.02,9.8)]*75,[(0.,0.,0.)]*75,[20.]*75
        acc=[v for v in acc for _ in range(5)]
        gyro=[v for v in gyro for _ in range(5)]
        speeds=[v for v in speeds for _ in range(5)]
        for header,address,values,stride in ((0x10001f0,0x1004000,acc,24),
            (0x10001d8,0x1007000,gyro,24),(0x1000208,0x100a000,speeds,8)):
            write(header,'3Q',address,address+len(values)*stride,address+len(values)*stride)
            flat=[v for row in values for v in row] if stride==24 else values
            write(address,f'{len(flat)}d',*flat)
        expected=align.advance(acc,gyro,speeds)
        call(0x7bd500,375,375,375)
        flags=bytes(uc.mem_read(0x10002b0,2))
        assert flags== (b'\x01\x01' if expected is not None else b'\x00\x00'), (step,flags,expected)
        if expected is not None:
            for address in (0x1000220,0x1000268):
                actual=struct.unpack('<9d',uc.mem_read(address,72))
                target=[expected[r][c] for c in range(3) for r in range(3)]
                for a,b in zip(actual,target):
                    assert math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-9),(step,actual,target)
            accepted+=1
        count=struct.unpack('<d',uc.mem_read(base+0x70,8))[0]
        assert count==align.heading.history.model.total_weight,(step,count,align.heading.history.model.total_weight)
    assert accepted>0
    print(f'24 complete native batch-calibration calls matched; {accepted} valid/cached rotations, flags and history matched. Host allocation/copy/acos/sincos only; acquisition and navigation fusion excluded.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
