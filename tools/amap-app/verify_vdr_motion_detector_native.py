"""Compare native motion window publication and stationary bias estimate."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_D4, UC_ARM64_REG_D5, UC_ARM64_REG_D6, UC_ARM64_REG_X5, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_D3, UC_ARM64_REG_X8, UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
import numpy as np
from vdr_motion_classifier import MotionDetector
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
        elif address in (0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address in (0x9f2e30,0x9f2fc0):
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

    for address in (0x9f2b80, 0x9f2b90, 0x9f2ba0, 0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0):
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
    expected=MotionDetector()
    call(0x779f3c,0)
    emitted=0
    for sample in range(900):
        if sample in (300,600):
            call(0x77a0a0,0)
            expected.reset()
        phase=sample%200
        gyro=rng.normal(size=3)*(.02 if phase>=140 else .00001)
        accel=np.array([0.,0.,9.80665])+rng.normal(size=3)*(.1 if phase>=160 else .00001)
        # Wrapper +77a0cc inputs are float32 sample records.
        gyro=gyro.astype(np.float32).astype(float);accel=accel.astype(np.float32).astype(float)
        write(0x1002000+0x10,'3f',*gyro)
        write(0x1002100+0x10,'3f',*accel)
        call(0x77a0cc,sample*40,0,0x1002000,0x1002100)
        expected.classifier.push(gyro,accel)
        if sample%5:
            continue
        timestamp=sample*40+(1300000 if sample>=500 else 0)
        integrated=Preintegration(timestamp=timestamp,count=(4,5,10,25)[(sample//5)%4])
        integrated.mean_gyro=(rng.normal(size=3)*.00001).tolist()
        if sample%45==0:
            integrated.mean_gyro[0]+=.01
        uc.mem_write(0x1006000,bytes(0x3e8))
        write(0x1006260,'i',timestamp)
        write(0x1006268,'i',integrated.count)
        write(0x1006210,'3d',*integrated.mean_gyro)
        vectors=rng.normal(size=(sample%4,3))
        write(0x10063c0,'3Q',0x1008000,0x1008000+len(vectors)*64,0x1008000+len(vectors)*64)
        for index,vector in enumerate(vectors):
            write(0x1008000+index*64+0x30,'3f',*vector)
        estimate=bool(sample%20)
        write(0xa523c0,'B',0x80 if estimate else 0)
        call(0x77a100,0x1006000)
        motion,detail,stable,bias,diagnostics=expected.publish(integrated,estimate_bias=estimate,sample_vectors=vectors)
        assert struct.unpack('<3i',uc.mem_read(0x100627c,12))==(motion,detail,stable)
        actual=np.frombuffer(uc.mem_read(0x1006320,24),dtype='<f8')
        np.testing.assert_allclose(actual,np.zeros(3) if bias is None else bias,rtol=1e-10,atol=1e-12)
        ptr,n=struct.unpack('<2Q',uc.mem_read(0x10063b0,16))
        np.testing.assert_allclose(np.frombuffer(uc.mem_read(ptr,n*8),dtype='<f8'),diagnostics,rtol=1e-9,atol=1e-11)
        np.testing.assert_allclose(np.frombuffer(uc.mem_read(0x1000120,24),dtype='<f8'),expected.bias,rtol=1e-10,atol=1e-12)
        assert struct.unpack('<i',uc.mem_read(0x1000138,4))[0]==expected.bias_count
        assert struct.unpack('<i',uc.mem_read(0x1000158,4))[0]==expected.last_bias_timestamp
        emitted+=1
    print(f'900 native IMU adapter inputs and {emitted} complete motion publications matched classification, counters, bias, diagnostics and resets.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
