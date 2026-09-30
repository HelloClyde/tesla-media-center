"""Compare original observation selection block, stopping before stacking."""
import argparse
import hashlib
import io
import math
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X22, UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X29, UC_ARM64_REG_X5, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_D8, UC_ARM64_REG_D1, UC_ARM64_REG_D2, UC_ARM64_REG_D3, UC_ARM64_REG_X8, UC_ARM64_REG_D0, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
import numpy as np
from vdr_observation_dispatch import observation_blocks, GpsObservation
from vdr_filter_update import CorrectionFilter
from vdr_reanchor import reanchor
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








    def gps_valid(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_X0,int(gps.valid))
        machine.reg_write(UC_ARM64_REG_PC,machine.reg_read(UC_ARM64_REG_LR))
    uc.hook_add(UC_HOOK_CODE,gps_valid,begin=0x101d000,end=0x101d000)
    def skip_log(machine,address,size,user):
        machine.reg_write(UC_ARM64_REG_PC,address+4)
    for address in (0x78c128,0x78c134,0x78c13c,0x78c200,0x78c20c,0x78c214):
        uc.hook_add(UC_HOOK_CODE,skip_log,begin=address,end=address)
    rng=np.random.default_rng(20260928)
    stop_address=0x7d6748
    def stop_at_boundary(machine,address,size,user):
        if address==stop_address:
            machine.emu_stop()
    for address in (0x7d6748,0x7d68b0,0x7d690c):
        uc.hook_add(UC_HOOK_CODE,stop_at_boundary,begin=address,end=address)
    selected=0
    for case in range(600):
        heap=0x2000000
        uc.mem_write(0x1000000,bytes(0x1c000))
        sp=0x101c000
        uc.mem_write(sp,bytes(0x1000))
        filter_address=0x1000000;extended=0x1006000
        config=int(rng.integers(0,8))*16
        calibrate=bool(case%5)
        motion=int(case%3!=0)
        flag1=bool(case%2) if motion else False
        flag2=bool((case//2)%2);force=bool((case//4)%2)
        gps=GpsObservation(valid=bool(case%4),flag18=bool(case%7==0),longitude=120.001,latitude=30.001,altitude=14.,speed=(-1.,0.,5.,10.,99.9,100.)[case%6],direction=(-1.,0.,45.)[case%3],position_sigma=(.1,20.,20.001,100.)[(case//3)%4],heading_sigma_degrees=(.001,.002,2.,179.9,180.)[case%5])
        direction=(-1.,0.,30.,180.)[(case//3)%4]
        r=np.array(rotation_and_right_jacobian(rng.normal(size=3)*.1)[0])
        c=np.array(rotation_and_right_jacobian(rng.normal(size=3)*.1)[0])
        state=initialize_pose(1000,0.,0.,(120.,30.,10.),c.tolist(),c.tolist(),rng.normal(size=3).tolist())
        state.pose.rotation=r.tolist()
        state.pose.position=(rng.normal(size=3)*(30 if case%2 else 300)).tolist()
        state.pose.velocity=(rng.normal(size=3)*10).tolist()
        state.auxiliary=rng.normal(size=3).tolist()
        gyro=rng.normal(size=3).astype(np.float32).astype(float)
        reference=np.array(rotation_and_right_jacobian(rng.normal(size=3)*.05)[0])@r
        extra=(120.002,30.002,99.,3.) if case%2 else None
        for off,values in ((0,r),(0x48,state.pose.velocity),(0x60,state.pose.position),(0x78,state.pose.gyro_bias),(0xa8,c),(0xf0,state.auxiliary)):
            uc.mem_write(filter_address+0x68+off,np.asarray(values,dtype='<f8').tobytes(order='F'))
        write(filter_address+0x68+0x110,'5d',120.,30.,10.,state.frame.east_scale,111319.49079327358)
        a=rng.normal(size=(21,21))
        covariance=a@a.T*.001+np.eye(21)*.01
        write(filter_address+0x1a0,'3Q',0x100e000,21,21)
        uc.mem_write(0x100e000,covariance.astype('<f8').tobytes(order='F'))
        count=(0,99,999)[case%3]
        write(filter_address+0x1d0,'i',count)
        write(filter_address+0x4e0,'3B',calibrate,flag1,flag2)
        write(filter_address+0x450,'3Q',0x100a000,0x100a000+4*72,0x100a000+4*72)
        uc.mem_write(0x100a000+72,reference.astype('<f8').tobytes(order='F'))
        write(extended+0x27c,'i',motion)
        write(extended+0x288,'d',direction)
        write(extended+0x250,'3f',*gyro)
        write(extended+0x338,'Q',0x100b000)
        write(0x100b010,'Q',0x101d000)
        write(extended+0x350,'B',gps.flag18)
        write(extended+0x370,'7d',gps.longitude,gps.latitude,gps.altitude,gps.speed,gps.direction,gps.position_sigma,0.)
        write(extended+0x3a8,'d',gps.heading_sigma_degrees)
        write(0xa27ab8,'Q',0x100c000)
        write(0x100c008,'B',config)
        if extra is not None:
            write(0x100d008,'i',8)
            write(0x100d028,'4d',*extra)
        call(0x7d5560,0)
        prepared,_,_=reanchor(state,covariance)
        for reg,value in ((UC_ARM64_REG_X19,filter_address),(UC_ARM64_REG_X20,0x100d000 if extra else 0),(UC_ARM64_REG_X21,extended),(UC_ARM64_REG_X22,extended+0x338),(UC_ARM64_REG_X23,force),(UC_ARM64_REG_X24,0x101f100),(UC_ARM64_REG_X29,sp+0x370),(UC_ARM64_REG_SP,sp),(UC_ARM64_REG_TPIDR_EL0,0x101f100)):
            uc.reg_write(reg,value)
        try:
            stop_address=0x7d6748
            uc.emu_start(0x7d657c,0x101f000,count=20000000)
        except Exception as error:
            raise RuntimeError(f'case={case} PC={uc.reg_read(UC_ARM64_REG_PC):x} LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC)==0x7d6748
        expected,used=observation_blocks(prepared,gps,config=config,calibrate=calibrate,direction=direction,motion=motion,gyro=gyro,flag1=flag1,flag2=flag2,force=force,stationary_reference=reference,extra_position=extra)
        heads=[struct.unpack('<2Q',uc.mem_read(sp+offset,16)) for offset in (0xc8,0xb0,0x98)]
        assert (heads[0][1]-heads[0][0])//24==len(expected),(case,len(expected),heads)
        for index,block in enumerate(expected):
            for column,(begin,end) in enumerate(heads):
                expected_value=block[column]
                if column==0:
                    ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(begin+index*24,24))
                    actual=np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
                else:
                    ptr,rows=struct.unpack('<2Q',uc.mem_read(begin+index*16,16))
                    actual=np.frombuffer(uc.mem_read(ptr,rows*8),dtype='<f8')
                np.testing.assert_allclose(actual,expected_value,rtol=1e-10,atol=1e-10,err_msg=f'case={case} block={index} field={column}')
        native_used=struct.unpack('<d',struct.pack('<Q',uc.reg_read(UC_ARM64_REG_D8)))[0]
        assert native_used==float(used)
        corrected=CorrectionFilter(state,covariance,count,calibrate)
        correction,corrected_used=corrected.correct_prepared_frame(gps,config=config,direction=direction,motion=motion,gyro=gyro,flag1=flag1,flag2=flag2,force=force,stationary_reference=reference,extra_position=extra)
        assert corrected_used==used
        if expected:
            stop_address=0x7d68b0
            uc.emu_start(0x7d6748,0x101f000,count=20000000)
            assert uc.reg_read(UC_ARM64_REG_PC)==0x7d68b0
            ptr,n=struct.unpack('<2Q',uc.mem_read(sp+0x50,16))
            np.testing.assert_allclose(np.frombuffer(uc.mem_read(ptr,n*8),dtype='<f8'),correction,rtol=1e-8,atol=1e-8)
        else:
            stop_address=0x7d690c
            uc.emu_start(0x7d6748,0x101f000,count=20000000)
            assert uc.reg_read(UC_ARM64_REG_PC)==0x7d690c
        ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(filter_address+0x1a0,24))
        actual=np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
        np.testing.assert_allclose(actual,corrected.covariance,rtol=1e-8,atol=1e-9)
        result=corrected.state
        for off,values in ((0,result.pose.rotation),(0x48,result.pose.velocity),(0x60,result.pose.position),(0x78,result.pose.gyro_bias),(0x90,result.pose.accel_bias),(0xa8,result.calibration),(0xf0,result.auxiliary)):
            values=np.asarray(values).flatten(order='F')
            actual=np.frombuffer(uc.mem_read(filter_address+0x68+off,values.size*8),dtype='<f8')
            np.testing.assert_allclose(actual,values,rtol=1e-8,atol=1e-8)
        assert struct.unpack('<i',uc.mem_read(filter_address+0x1d0,4))[0]==corrected.count
        selected+=len(expected)
    print(f'600 native reanchor + selection + stacking + correction paths matched {selected} observations, pose, covariance and counter; upstream lifecycle excluded.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
