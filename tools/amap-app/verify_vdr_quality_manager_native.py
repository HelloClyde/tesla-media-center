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
from vdr_quality_manager import QualityManager
from vdr_preintegration import advance_pose
from vdr_window_producer import empty_integration
from vdr_window_gps import WindowGps
from inspect_vdr_model import inspect
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
        elif address in (0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390, 0x9f2e40, 0x9f3370):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address in (0x9f2e40, 0x9f3370):
                other = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D1)))[0]
                machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', (math.atan2(value, other) if address == 0x9f2e40 else math.fmod(value, other))))[0])
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

    for address in (0x9f2b80, 0x9f2b90, 0x9f2ba0, 0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390, 0x9f2e40, 0x9f3370):
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








    parameters=inspect(apk)['linear_score']
    expected=QualityManager(parameters)
    write(0x1000008,'d',5000.)
    write(0x1000018,'i',1000)
    for offset,key in ((0x20,'means'),(0x1d8,'scales'),(0x390,'coefficients')):
        write(0x1000000+offset,'55d',*parameters[key])
    write(0x1000548,'d',parameters['bias'])
    write(0x1000570,'3Q',0x1002000,0x1002270,0x1002270)
    for index,history in enumerate(expected.histories):
        offset=0x10005a8+index*0x28
        write(offset,'2i',history.capacity,history.dimensions)
        write(offset+8,'3Q',0x100a000+index*0x500,history.capacity,history.dimensions)
    call(0x7778b4,0)
    write(0xa524a8,'3d',*expected.gravity)
    write(0x1008000,'3Q',0x100f000,21,21)
    uc.mem_write(0x100f000,np.eye(21,dtype='<f8').tobytes(order='F'))
    write(0x1009000,'2Q',0x1009800,19)
    write(0x1007338,'Q',0x1009500)
    write(0x1009510,'Q',0x1010100)
    valid=True
    def gps_valid(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_X0,int(valid))
        machine.reg_write(UC_ARM64_REG_PC,machine.reg_read(UC_ARM64_REG_LR))
    uc.hook_add(UC_HOOK_CODE,gps_valid,begin=0x1010100,end=0x1010100)
    state=initialize_pose(1000,0.,10.,(120.,30.,0.),np.eye(3).tolist(),np.eye(3).tolist(),[0.]*3)
    for step in range(100):
        timestamp=1500+step*500
        integrated=empty_integration(timestamp-500)
        for tick in range(timestamp-480,timestamp+1,20): integrated.advance(tick,(.001,.002,.003),(.01,.02,9.80665))
        for off,name in enumerate(MATRICES): uc.mem_write(0x1007000+off*72,np.asarray(getattr(integrated,name),dtype='<f8').tobytes(order='F'))
        for off,name in enumerate(VECTORS): write(0x10071b0+off*24,'3d',*getattr(integrated,name))
        write(0x1007260,'3i',timestamp,integrated.initial_timestamp,integrated.count)
        direction=0. if step%5 else -1.
        write(0x1007288,'d',direction)
        for off,values in ((0,state.pose.rotation),(0x48,state.pose.velocity),(0x60,state.pose.position),(0x78,state.pose.gyro_bias),(0x90,state.pose.accel_bias),(0xa8,state.calibration),(0xf0,state.auxiliary)):
            uc.mem_write(0x1006000+off,np.asarray(values,dtype='<f8').tobytes(order='F'))
        write(0x1006108,'i',state.flags)
        write(0x1006110,'5d',120.,30.,0.,state.frame.east_scale,111319.49079327358)
        residual=np.zeros(19);residual[0]=step%2
        uc.mem_write(0x1009800,residual.astype('<f8').tobytes())
        call(0x777ba0,0x1007000,0x1006000,0x1008000,0x1009000)
        window=SimpleNamespace(integrated=integrated,direction=direction,gps=WindowGps(timestamp,120.,30.))
        expected.advance(state,window,np.eye(21),residual)
        for index,history in enumerate(expected.histories):
            offset=0x10005a8+index*0x28
            pointer,rows,cols=struct.unpack('<3Q',uc.mem_read(offset+8,24))
            actual=np.frombuffer(uc.mem_read(pointer,rows*cols*8),dtype='<f8').reshape(rows,cols,order='F')
            np.testing.assert_allclose(actual,history.values,atol=1e-8,rtol=1e-7,err_msg=f'step={step} history={index}')
            assert struct.unpack('<iB',uc.mem_read(offset+0x20,5))==(history.index,int(history.ready))
        np.testing.assert_allclose(struct.unpack('<2d',uc.mem_read(0x1000590,16)),[expected.scores.primary,expected.scores.secondary],atol=1e-7)
        state.pose=advance_pose(state.pose,integrated,expected.gravity)
    print('100 continuous complete native quality callbacks matched all12 histories and both scores.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
