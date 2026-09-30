"""Compare calibration-enabled +7d5c20; skip global history insertion and diagnostic log."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_X5, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_X8, UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
import numpy as np

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







    from vdr_preintegration import Preintegration,PoseState,advance_pose
    from vdr_prediction_matrices import prediction_matrices
    from verify_vdr_preintegration_native import MATRICES,VECTORS
    def skip_history(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_PC,address+4)
    uc.hook_add(UC_HOOK_CODE,skip_history,begin=0x7d5c90,end=0x7d5c90)
    rng=np.random.default_rng(20260928)
    def mat(address,value):
        uc.mem_write(address,np.asarray(value,dtype='<f8').tobytes(order='F'))
    uc.hook_add(UC_HOOK_CODE,skip_history,begin=0x7d6254,end=0x7d6254)
    from vdr_calibration_gate import CalibrationGate
    from vdr_adaptive_prediction import predict_adaptive
    triggers=0
    for case in range(100):
        heap=0x2000000
        gate=CalibrationGate()
        call(0x7bdbe8,0)
        for _ in range(5):
            for reg,value in ((UC_ARM64_REG_D0,.1),(UC_ARM64_REG_D1,.1),(UC_ARM64_REG_D2,.001)):
                uc.reg_write(reg,struct.unpack('<Q',struct.pack('<d',value))[0])
            call(0x7bdc40,0)
            gate.update(.1,.1,.001)
        uc.mem_write(0x1000468,bytes(uc.mem_read(0x1000000,0x60)))
        dt_ms=(1,20,40,100,1000)[case%5]
        integrated=Preintegration(timestamp=1000+dt_ms,initial_timestamp=1000)
        for name in MATRICES[:5]:
            setattr(integrated,name,(rng.normal(size=(3,3))*.1).tolist())
        integrated.rotation=rotation_and_right_jacobian(rng.normal(size=3))[0]
        pose=PoseState(rotation=rotation_and_right_jacobian(rng.normal(size=3))[0],velocity=(rng.normal(size=3)*(100 if case%2 else 1)).tolist(),position=(rng.normal(size=3)*100).tolist(),gyro_bias=(rng.normal(size=3)*.01).tolist(),accel_bias=(rng.normal(size=3)*.1).tolist())
        mat(0x1000068,pose.rotation)
        for off,name in ((0x48,'velocity'),(0x60,'position'),(0x78,'gyro_bias'),(0x90,'accel_bias')):
            write(0x1000068+off,'3d',*getattr(pose,name))
        write(0x1000068+0x108,'I',127)
        for i,name in enumerate(MATRICES):
            mat(0x1002000+i*72,getattr(integrated,name))
        for i,name in enumerate(VECTORS):
            write(0x10021b0+i*24,'3d',*getattr(integrated,name))
        write(0x1002260,'3i',integrated.timestamp,1000,1)
        g=[0.,0.,-9.80665]
        write(0xa524a8,'3d',*g)
        a=rng.normal(size=(21,21));p=a@a.T+np.eye(21)
        a=rng.normal(size=(18,18));q=a@a.T+np.eye(18)
        write(0x10001a0,'3Q',0x1006000,21,21);mat(0x1006000,p)
        write(0x10001b8,'3Q',0x1008000,18,18);mat(0x1008000,q)
        calibration=rotation_and_right_jacobian(rng.normal(size=3))[0]
        mat(0x1000068+0xa8,calibration)
        write(0x10004e0,'B',1)
        call(0x7d5c20,0x1002000)
        from vdr_covariance_prediction import predict
        state=initialize_pose(1000,0.,0.,(120.,30.,10.),np.eye(3).tolist(),np.eye(3).tolist(),[0.,0.,0.])
        state.pose=pose
        state.calibration=calibration
        expected_state,expected,triggered=predict_adaptive(state,p,q,integrated,g,gate)
        triggers+=triggered
        ptr=struct.unpack('<Q',uc.mem_read(0x10001a0,8))[0]
        actual=np.frombuffer(uc.mem_read(ptr,21*21*8),dtype='<f8').reshape((21,21),order='F')
        np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-9)
        predicted=expected_state.pose
        expected_pose=[predicted.rotation[r][c] for c in range(3) for r in range(3)]
        for name in ('velocity','position','gyro_bias','accel_bias'):
            expected_pose.extend(getattr(predicted,name))
        actual_pose=struct.unpack('<21d',uc.mem_read(0x1000068,168))
        np.testing.assert_allclose(actual_pose,expected_pose,rtol=1e-9,atol=1e-9)
    print(f'100 complete adaptive native predictions matched covariance and pose, including {triggers} triggered adjustments. Only history insertion and diagnostic logging skipped.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
