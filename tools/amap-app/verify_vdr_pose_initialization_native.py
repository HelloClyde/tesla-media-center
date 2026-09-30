"""Compare +77b86c state construction, stopping at +77b990 before logging."""
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
from vdr_pose_initialization import initialize_pose
from vdr_preintegration import rotation_and_right_jacobian


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
        elif address in (0x9f40d0, 0x9f2e20, 0x9f2e30):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address == 0x9f2e30:
                result=math.cos(value)
                machine.reg_write(UC_ARM64_REG_D0,struct.unpack('<Q',struct.pack('<d',result))[0])
            elif address == 0x9f40d0:
                result = math.acos(value) if -1 <= value <= 1 else math.nan
                machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d',result))[0])
            else:
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X0),struct.pack('<d',math.sin(value)))
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X1),struct.pack('<d',math.cos(value)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30):
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
            uc.emu_start(entry, 0x77b990, count=2000000)
        except Exception as error:
            raise RuntimeError(f'PC={uc.reg_read(UC_ARM64_REG_PC):x}, LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x77b990
        return uc.reg_read(UC_ARM64_REG_X0)

    rng=random.Random(20260928)
    worst=0.
    def matrix(address,value):
        write(address,'9d',*(value[r][c] for c in range(3) for r in range(3)))
    for case in range(500):
        direction=rng.uniform(-360,720)
        speed=rng.uniform(0,40)
        origin=(rng.uniform(100,130),rng.uniform(20,45),rng.uniform(-50,1000))
        preferred=rotation_and_right_jacobian([rng.uniform(-1,1) for _ in range(3)])[0]
        fallback=rotation_and_right_jacobian([rng.uniform(-1,1) for _ in range(3)])[0]
        if case%2:
            preferred[0][0]=100. if case%4==1 else 10000.
        bias=[rng.uniform(-.1,.1) for _ in range(3)]
        timestamp=1000+case*40
        solution,history,output,timeptr=0x100b000,0x100c000,0x100d000,0x100d200
        write(0x1009d30,'Q',history)
        write(0x1009d48,'Q',case%3)
        record=history+(case%3)*0x138
        matrix(record+0xd0,preferred)
        matrix(record+0x88,fallback)
        write(record+0x118,'3d',*bias)
        write(solution,'i',timestamp)
        write(solution+8,'d',direction)
        write(solution+0x48,'4d',*origin,speed)
        uc.mem_write(output,bytes(0x138))
        call(0x77b86c,solution,timeptr,output)
        expected=initialize_pose(timestamp,direction,speed,origin,preferred,fallback,bias)
        assert struct.unpack('<i',uc.mem_read(timeptr,4))[0]==timestamp
        for offset,values in ((0,[expected.pose.rotation[r][c] for c in range(3) for r in range(3)]),
            (0x48,expected.pose.velocity),(0x60,expected.pose.position),(0x78,bias),
            (0x90,expected.pose.accel_bias),(0xa8,[expected.calibration[r][c] for c in range(3) for r in range(3)]),
            (0xf0,expected.auxiliary),(0x110,origin),(0x128,[expected.frame.east_scale,111319.49079327358])):
            actual=struct.unpack(f'<{len(values)}d',uc.mem_read(output+offset,len(values)*8))
            for a,b in zip(actual,values):
                assert math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-12),(case,hex(offset),actual,values)
                worst=max(worst,abs(a-b))
        assert struct.unpack('<I',uc.mem_read(output+0x108,4))[0]==0x7f
    print(f'500 native state-building paths matched all pose/frame fields, timestamp and flags; max error {worst:.3g}. Stopped before logging tail; native solution direction provenance remains upstream.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
