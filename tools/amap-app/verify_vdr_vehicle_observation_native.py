"""Compare full +7d3c78 moving vehicle observation, all noise flag combinations."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X5, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_D3, UC_ARM64_REG_X8, UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
import numpy as np
from vdr_vehicle_observation import vehicle_observation
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
        if address == 0x9f2b80:
            machine.reg_write(UC_ARM64_REG_X0, int(machine.mem_read(machine.reg_read(UC_ARM64_REG_X0),1)[0] == 0))
        elif address == 0x9f2b90:
            machine.mem_write(machine.reg_read(UC_ARM64_REG_X0), b'\x01')
        if address == 0x9f2ba0:
            machine.mem_write(machine.reg_read(UC_ARM64_REG_X0),bytes([machine.reg_read(UC_ARM64_REG_X1) & 255])*machine.reg_read(UC_ARM64_REG_X2))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2b80, 0x9f2b90, 0x9f2ba0, 0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30):
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
            uc.emu_start(entry, 0x101f000, count=20000000)
        except Exception as error:
            raise RuntimeError(f'PC={uc.reg_read(UC_ARM64_REG_PC):x}, LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x101f000
        return uc.reg_read(UC_ARM64_REG_X0)








    rng=np.random.default_rng(20260928)
    for case in range(200):
        heap=0x2000000
        for header in (0x1000000,0x1001000,0x1001100):
            uc.mem_write(header,bytes(24))
        r=np.array(rotation_and_right_jacobian(rng.normal(size=3))[0])
        c=np.array(rotation_and_right_jacobian(rng.normal(size=3))[0])
        v=rng.normal(size=3)*20;bg=rng.normal(size=3)*.01;l=rng.normal(size=3);gyro=rng.normal(size=3)
        if case%10==0:
            l=np.zeros(3)
        if case%13==0:
            gyro=bg.copy()
        pose=0x1002000
        for off,values in ((0,r),(0xa8,c),(0x48,v),(0x78,bg),(0xf0,l)):
            uc.mem_write(pose+off,np.asarray(values,dtype='<f8').tobytes(order='F'))
        for reg,value in zip((UC_ARM64_REG_D0,UC_ARM64_REG_D1,UC_ARM64_REG_D2),gyro):
            uc.reg_write(reg,struct.unpack('<Q',struct.pack('<d',value))[0])
        flag4=case%2;flag5=(case//2)%2
        uc.reg_write(UC_ARM64_REG_X5,flag5)
        call(0x7d3c78,0x1001000,0x1001100,pose,flag4)
        state=initialize_pose(1000,0.,0.,(120.,30.,0.),c.tolist(),c.tolist(),bg.tolist())
        state.pose.rotation=r.tolist();state.pose.velocity=v.tolist();state.auxiliary=l.tolist()
        expected_h,residual,variances=vehicle_observation(state,gyro,flag4,flag5)
        mh=struct.unpack('<Q',uc.mem_read(0x1000000,8))[0]
        ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(mh,24))
        actual=np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
        np.testing.assert_allclose(actual,expected_h,rtol=1e-11,atol=1e-11)
        for header,expected in ((0x1001000,residual),(0x1001100,variances)):
            vh=struct.unpack('<Q',uc.mem_read(header,8))[0]
            ptr,n=struct.unpack('<2Q',uc.mem_read(vh,16))
            actual=np.frombuffer(uc.mem_read(ptr,n*8),dtype='<f8')
            np.testing.assert_allclose(actual,expected,rtol=1e-11,atol=1e-11)
    print('200 full native moving-vehicle observations matched H/residual/noise for all four flag combinations, including zero offset and zero corrected gyro.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
