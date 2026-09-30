"""Compare native GPS admission for the paired-IMU window producer."""
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
from vdr_feature_history import FeatureHistory, quality_features
from types import SimpleNamespace
from verify_vdr_preintegration_native import MATRICES, VECTORS
from vdr_pose_initialization import initialize_pose
from vdr_preintegration import rotation_and_right_jacobian, Preintegration


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
        elif address in (0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390, 0x9f2e40):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address == 0x9f2e40:
                other = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D1)))[0]
                machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', math.atan2(value, other)))[0])
            elif address == 0x9f3390:
                machine.reg_write(UC_ARM64_REG_D0,struct.unpack("<Q",struct.pack("<d",math.asin(value)))[0])
            elif address in (0x9f2e30,0x9f2fc0):
                result=math.cos(value) if address == 0x9f2e30 else math.sin(value)
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

    for address in (0x9f2b80, 0x9f2b90, 0x9f2ba0, 0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390, 0x9f2e40):
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








    rng=np.random.default_rng(776)
    comparisons=0
    for capacity,dimensions in ((1,1),(5,2),(25,6)):
        expected=FeatureHistory(capacity,dimensions)
        write(0x1000000,'2i',capacity,dimensions)
        write(0x1000008,'3Q',0x1004000,capacity,dimensions)
        call(0x776904,0)
        for step in range(80):
            values=rng.normal(size=dimensions)*10
            if step % 19 == 0: values[0] = math.nan
            write(0x1002000,'2Q',0x1003000,dimensions)
            uc.mem_write(0x1003000,values.astype('<f8').tobytes())
            call(0x776bec,0x1002000)
            expected.push(values)
            assert struct.unpack('<i',uc.mem_read(0x1000020,4))[0]==expected.index
            assert bool(uc.mem_read(0x1000024,1)[0])==expected.ready
            for entry,wanted in ((0x776930,expected.mean()),(0x7769e8,expected.deviation()),
                                 (0x776ae4,expected.maximum()),(0x776b68,expected.minimum())):
                uc.reg_write(UC_ARM64_REG_X8,0x1007000)
                call(entry,0)
                pointer,size=struct.unpack('<2Q',uc.mem_read(0x1007000,16))
                actual=np.frombuffer(uc.mem_read(pointer,size*8),dtype='<f8')
                np.testing.assert_allclose(actual,wanted,atol=1e-12)
                comparisons+=1
    print(f'{comparisons} native history statistic outputs and240 insertions matched readiness and ring state.')
    histories=[]
    for index,dimensions in enumerate((6,2,2,2,2,1,1,1,6,6,6,6)):
        history=FeatureHistory(5,dimensions)
        for row in rng.normal(size=(5,dimensions)):
            history.push(row)
        histories.append(history)
        offset=0x10005a8+index*0x28
        pointer=0x1008000+index*0x200
        write(offset,'2i',5,dimensions)
        write(offset+8,'3Q',pointer,5,dimensions)
        write(offset+0x20,'iB',0,1)
        uc.mem_write(pointer,history.values.astype('<f8').tobytes(order='F'))
    uc.reg_write(UC_ARM64_REG_X8,0x1007000)
    call(0x7772b8,0)
    pointer,size=struct.unpack('<2Q',uc.mem_read(0x1007000,16))
    actual=np.frombuffer(uc.mem_read(pointer,size*8),dtype='<f8')
    np.testing.assert_allclose(actual,quality_features(histories),atol=1e-12)
    print('Complete native55-feature assembly matched all feature positions.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
