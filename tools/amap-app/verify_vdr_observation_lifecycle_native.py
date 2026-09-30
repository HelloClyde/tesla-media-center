"""Compare original preintegration concatenation +7cfaa0 with equal biases."""
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
from vdr_preintegration_composition import compose
from vdr_observation_lifecycle import ObservationLifecycle
from vdr_filter_update import CorrectionFilter
from vdr_observation_dispatch import GpsObservation
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








    def skip_call(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_PC,address+4)
    for address in (0x7d6540,0x7d654c,0x7d6554,0x7d6564,0x7d6570,0x7d6578,0x7d6918,
                    0x78c128,0x78c134,0x78c13c,0x78c200,0x78c20c,0x78c214):
        uc.hook_add(UC_HOOK_CODE,skip_call,begin=address,end=address)
    def gps_valid(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_X0,int(gps.valid))
        machine.reg_write(UC_ARM64_REG_PC,machine.reg_read(UC_ARM64_REG_LR))
    uc.hook_add(UC_HOOK_CODE,gps_valid,begin=0x101d000,end=0x101d000)
    rng=np.random.default_rng(20260928)
    for trajectory in range(6):
        heap=0x2000000
        uc.mem_write(0x1000000,bytes(0x1c000))
        state=initialize_pose(1000,0.,0.,(120.,30.,10.),np.eye(3).tolist(),np.eye(3).tolist(),[0.,0.,0.])
        state.pose.rotation=rotation_and_right_jacobian([.01,.02,.03])[0]
        state.pose.velocity=[.1,.2,.3]
        state.pose.position=[200.,10.,20.]
        covariance=np.eye(21)*.01
        expected=ObservationLifecycle(CorrectionFilter(state,covariance),installation_variance=.001)
        for off,values in ((0,state.pose.rotation),(0x48,state.pose.velocity),(0x60,state.pose.position),(0x78,state.pose.gyro_bias),(0x90,state.pose.accel_bias),(0xa8,state.calibration),(0xf0,state.auxiliary)):
            uc.mem_write(0x1000068+off,np.asarray(values,dtype='<f8').tobytes(order='F'))
        write(0x1000068+0x108,'i',state.flags)
        write(0x1000068+0x110,'5d',120.,30.,10.,state.frame.east_scale,111319.49079327358)
        write(0x10001a0,'3Q',0x100e000,21,21)
        uc.mem_write(0x100e000,covariance.astype('<f8').tobytes(order='F'))
        write(0x1000058,'d',.001)
        write(0x10004c8,'2Q',0x100f000,22)
        write(0x10004e0,'B',1)
        write(0x1000448,'i',-1)
        write(0xa27ab8,'Q',0x100c000)
        write(0x100c008,'B',0x70)
        for frame in range(60):
            timestamp=1000+frame*400
            if frame%13==12:
                timestamp-=400
            if frame%17==16:
                timestamp-=800
            integrated=Preintegration(initial_timestamp=timestamp-400,timestamp=timestamp,count=10)
            integrated.rotation=rotation_and_right_jacobian([.001,.002,.003])[0]
            integrated.rotation_gyro_derivative=(-np.eye(3)*.4).tolist()
            integrated.gyro_bias=(rng.normal(size=3)*.0001).tolist()
            integrated.mean_gyro=[.001,.002,.003]
            integrated.mean_accel=[0.,0.,9.80665]
            for off,name in enumerate(MATRICES):
                uc.mem_write(0x1006000+off*72,np.asarray(getattr(integrated,name),dtype='<f8').tobytes(order='F'))
            for off,name in enumerate(VECTORS):
                write(0x10061b0+off*24,'3d',*getattr(integrated,name))
            write(0x1006260,'3i',timestamp,integrated.initial_timestamp,integrated.count)
            motion=int(frame%20==0)
            detail=1 if frame%11==0 else 2
            flag1=bool(trajectory%2);flag2=bool(trajectory%3);force=bool(frame%3==0)
            calibration_state=0 if frame==45 else 1
            gps=GpsObservation(valid=bool(frame%4),longitude=120.001,latitude=30.001,altitude=12.,speed=0.,direction=0.,position_sigma=3.,heading_sigma_degrees=2.)
            write(0x1006278,'3i',calibration_state,motion,detail)
            write(0x1006288,'d',0.)
            write(0x1006250,'3f',.001,.002,.003)
            write(0x1006338,'Q',0x100b000)
            write(0x100b010,'Q',0x101d000)
            write(0x1006370,'7d',gps.longitude,gps.latitude,gps.altitude,gps.speed,gps.direction,gps.position_sigma,0.)
            write(0x10063a8,'d',gps.heading_sigma_degrees)
            write(0x10004e1,'2B',flag1,flag2)
            call(0x7d64a0,0x1006000,0,force)
            expected.observe(integrated,gps,calibration_state=calibration_state,config=0x70,direction=0.,motion=motion,motion_detail=detail,gyro=np.array([.001,.002,.003],dtype=np.float32).astype(float),flag1=flag1,flag2=flag2,force=force)
            result=expected.correction.state
            for off,values in ((0,result.pose.rotation),(0x48,result.pose.velocity),(0x60,result.pose.position),(0x78,result.pose.gyro_bias),(0x90,result.pose.accel_bias),(0xa8,result.calibration),(0xf0,result.auxiliary)):
                values=np.asarray(values).flatten(order='F')
                actual=np.frombuffer(uc.mem_read(0x1000068+off,values.size*8),dtype='<f8')
                np.testing.assert_allclose(actual,values,rtol=1e-7,atol=1e-8,err_msg=f'trajectory={trajectory} frame={frame} offset={off:x}')
            ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(0x10001a0,24))
            actual=np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
            np.testing.assert_allclose(actual,expected.correction.covariance,rtol=1e-7,atol=1e-9)
            assert struct.unpack('<i',uc.mem_read(0x1000448,4))[0]==expected.last_timestamp
            assert struct.unpack('<i',uc.mem_read(0x10001d0,4))[0]==expected.correction.count
            assert bool(uc.mem_read(0x10004e0,1)[0])==expected.correction.calibrate
            stored=expected.stationary_integrated
            for off,name in enumerate(MATRICES):
                actual=np.frombuffer(uc.mem_read(0x10001d8+off*72,72),dtype='<f8').reshape((3,3),order='F')
                np.testing.assert_allclose(actual,getattr(stored,name),rtol=1e-7,atol=1e-8,err_msg=name)
            for off,name in enumerate(VECTORS):
                actual=np.frombuffer(uc.mem_read(0x10001d8+0x1b0+off*24,24),dtype='<f8')
                np.testing.assert_allclose(actual,getattr(stored,name),rtol=1e-7,atol=1e-8,err_msg=name)
            assert struct.unpack('<3i',uc.mem_read(0x10001d8+0x260,12))==(stored.timestamp,stored.initial_timestamp,stored.count)
            begin,end=struct.unpack('<2Q',uc.mem_read(0x1000450,16))
            assert (end-begin)//72==len(expected.stationary_rotations)
            for index,rotation in enumerate(expected.stationary_rotations):
                actual=np.frombuffer(uc.mem_read(begin+index*72,72),dtype='<f8').reshape((3,3),order='F')
                np.testing.assert_allclose(actual,rotation,rtol=1e-7,atol=1e-8)
            actual=struct.unpack('<5d',uc.mem_read(0x1000068+0x110,40))
            np.testing.assert_allclose(actual,(result.frame.longitude,result.frame.latitude,result.frame.altitude,result.frame.east_scale,111319.49079327358),rtol=1e-9,atol=1e-8)
    print('360 complete initialized-filter observation calls matched sequential state, covariance, counters, calibration exit and all stationary window fields and rotation history; logs/global backup publication excluded.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
