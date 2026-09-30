"""Compare +7d5810 for SPD observations, including periodic normalization cases."""
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
    UC_ARM64_REG_X8, UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
import numpy as np
from vdr_filter_update import CorrectionFilter
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



    # Skip only six diagnostic stream calls; execute all state math.
    def skip_log(machine, address, size, user):
        machine.reg_write(UC_ARM64_REG_PC, address+4)
    for address in (0x78c128,0x78c134,0x78c13c,0x78c200,0x78c20c,0x78c214):
        uc.hook_add(UC_HOOK_CODE, skip_log, begin=address, end=address)

    rng = np.random.default_rng(20260928)
    def matrix(header, address, values):
        rows,cols = values.shape
        write(header,'QQQ',address,rows,cols)
        uc.mem_write(address,values.astype('<f8').tobytes(order='F'))
    def read_matrix(header):
        ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(header,24))
        return np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
    for case in range(60):
        heap=0x2000000
        m=(1,2,3,6,9,12)[case%6]
        a=rng.normal(size=(21,21)); p=a@a.T + np.eye(21)
        h=rng.normal(size=(m,21))
        a=rng.normal(size=(m,m)); noise=a@a.T+np.eye(m)
        residual=rng.normal(size=(m,1))*.01
        matrix(0x10001a0,0x1002000,p)
        matrix(0x1001000,0x1004000,h)
        matrix(0x1001100,0x1005000,residual)
        matrix(0x1001200,0x1006000,noise)
        uc.mem_write(0x1000068,bytes(0x138))
        for offset in (0,0xa8):
            write(0x1000068+offset,'9d',*np.eye(3).flatten(order='F'))
        count=(0,98,99,998,999,1999)[case%6]
        write(0x10001d0,'I',count)
        write(0x10004e0,'B',case%2)
        uc.reg_write(UC_ARM64_REG_X8,0x1001300)
        call(0x7d5810,0x1001000,0x1001100,0x1001200)
        state=initialize_pose(1000,0.,0.,(120.,30.,0.),np.eye(3).tolist(),np.eye(3).tolist(),[0.,0.,0.])
        state.auxiliary=(0.,0.,0.)
        expected=CorrectionFilter(state,p,count,bool(case%2))
        expected_error=expected.update(h,residual,noise)
        expected_state,expected_p=expected.state,expected.covariance
        ptr,n=struct.unpack('<2Q',uc.mem_read(0x1001300,16))
        actual=np.frombuffer(uc.mem_read(ptr,n*8),dtype='<f8')
        np.testing.assert_allclose(actual,expected_error,rtol=1e-9,atol=1e-11)
        np.testing.assert_allclose(read_matrix(0x10001a0),expected_p,rtol=1e-9,atol=1e-11)
        pose=expected_state.pose
        flat=lambda m: np.array(m).flatten(order='F')
        for offset,values in ((0,flat(pose.rotation)),(0x48,pose.velocity),(0x60,pose.position),
                             (0x78,pose.gyro_bias),(0x90,pose.accel_bias),
                             (0xa8,flat(expected_state.calibration)),(0xf0,expected_state.auxiliary)):
            actual=np.frombuffer(uc.mem_read(0x1000068+offset,len(values)*8),dtype='<f8')
            np.testing.assert_allclose(actual,values,rtol=1e-9,atol=1e-11)
        assert struct.unpack('<I',uc.mem_read(0x10001d0,4))[0]==expected.count
    print('60 complete native filter updates matched correction, Joseph covariance, all pose fields and counter. Observation dimensions 1/2/3/6/9/12; both calibration modes. Includes 100/1000-step rotation normalization.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
