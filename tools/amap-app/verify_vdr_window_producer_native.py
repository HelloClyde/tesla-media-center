"""Compare complete native paired-IMU window scheduling and publication."""
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
from vdr_window_gps import WindowGps, WindowGpsGate
from vdr_window_producer import WindowProducer
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
        elif address in (0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address == 0x9f3390:
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

    for address in (0x9f2b80, 0x9f2b90, 0x9f2ba0, 0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2e30, 0x9f2fc0, 0x9f3390):
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








    def read_window(address):
        values=[]
        for off,name in enumerate(MATRICES):
            values.extend(struct.unpack('<9d',uc.mem_read(address+off*72,72)))
        for off,name in enumerate(VECTORS):
            values.extend(struct.unpack('<3d',uc.mem_read(address+0x1b0+off*24,24)))
        begin,end=struct.unpack('<2Q',uc.mem_read(address+0x3c0,16))
        samples=[]
        for pointer in range(begin,end,64):
            samples.append((struct.unpack('<i',uc.mem_read(pointer+12,4))[0],
                            struct.unpack('<3f',uc.mem_read(pointer+16,12)),
                            struct.unpack('<3f',uc.mem_read(pointer+48,12))))
        return values,struct.unpack('<3i',uc.mem_read(address+0x260,12)),samples,struct.unpack('<i',uc.mem_read(address+0x3e4,4))[0]
    def compare(actual,window):
        values=[]
        for name in MATRICES:
            values.extend(np.asarray(getattr(window.integrated,name)).flatten(order='F'))
        for name in VECTORS:
            values.extend(getattr(window.integrated,name))
        np.testing.assert_allclose(actual[0],values,rtol=1e-8,atol=1e-9)
        assert actual[1]==(window.integrated.timestamp,window.integrated.initial_timestamp,window.integrated.count),(actual[1],window.integrated)
        assert actual[2]==[(s.timestamp,tuple(s.first),tuple(s.second)) for s in window.samples]
        assert actual[3]==window.maximum_sample_gap,(sequence,sample,actual[3],window.maximum_sample_gap)
    def published(machine,address,size,user):
        events.append((read_window(machine.reg_read(UC_ARM64_REG_X1)),read_window(machine.reg_read(UC_ARM64_REG_X2))))
    uc.hook_add(UC_HOOK_CODE,published,begin=0x7dbbac,end=0x7dbbac)
    def record_gap(machine,address,size,user):
        current=machine.reg_read(UC_ARM64_REG_X1)&0xffffffff
        previous=machine.reg_read(UC_ARM64_REG_X2)&0xffffffff
        gaps.append((current if current<2**31 else current-2**32,previous if previous<2**31 else previous-2**32))
    uc.hook_add(UC_HOOK_CODE,record_gap,begin=0x7dbb5c,end=0x7dbb5c)
    publications=0
    for sequence in range(6):
        heap=0x2000000
        uc.mem_write(0x1000000,bytes(0x1c000))
        write(0xa27ac0,'Q',0xa17eb0)
        call(0x7db964,0)
        expected=WindowProducer()
        timestamp=1000
        for sample in range(200):
            # Execute actual native feedback accumulation, including retained
            # history across refreshes. Long-gap sequences cross the 30s gate.
            bias_gyro=(sample*.00001,.0002,-.0003)
            bias_accel=(.01,-.02,sample*.0001)
            write(0x1004000,'3d',*bias_gyro)
            write(0x1004100,'3d',*bias_accel)
            call(0x7dbe34,0x1004000,0x1004100)
            expected.feedback_bias(timestamp,bias_gyro,bias_accel)
            timestamp+=((0,20,40,200,201,1000,1001)[sample%7] if sequence>=4 else (300 if sample%61==60 else 40))
            relaxed=bool(sequence%2)
            write(0xa523c1,'B',int(relaxed))
            gps=None
            uc.mem_write(0x1002000,bytes(0x78))
            write(0x1002008,'2i',-1,-1)
            if sequence>=2 and sample%19==0 or sequence==0 and sample==0:
                gps=WindowGps(timestamp,120.+sample*.0001,30.,speed=5.)
                write(0x1002008,'2i',0,timestamp)
                write(0x1002038,'4d',gps.longitude,gps.latitude,gps.altitude,gps.speed)
            gyro=(.001,.002,.003);accel=(0.,0.,9.8)
            write(0x1003008,'2i3f',2,timestamp,*gyro)
            write(0x1003108,'2i3f',1,timestamp,*accel)
            events=[];gaps=[]
            call(0x7dbebc,0x1002000,0x1003000,0x1003100)
            wanted,gap=expected.push(timestamp,gyro,accel,gps,relaxed_gap=relaxed)
            assert gaps==([] if gap is None else [gap]),(sequence,sample,gaps,gap)
            assert len(events)==len(wanted),(sequence,sample,len(events),len(wanted))
            for event,pair in zip(events,wanted):
                compare(event[0],pair[0]);compare(event[1],pair[1])
            compare(read_window(0x1000148),expected.retained)
            compare(read_window(0x1000530),expected.current)
            assert struct.unpack('<i',uc.mem_read(0x1000090,4))[0]==expected.deadline
            assert struct.unpack('<i',uc.mem_read(0x1000014,4))[0]==expected.last_timestamp
            assert struct.unpack('<i',uc.mem_read(0x1000110,4))[0]==expected.last_bias_refresh
            np.testing.assert_allclose(struct.unpack('<6d',uc.mem_read(0x1000118,48)),
                                       expected.gyro_bias+expected.accel_bias,rtol=1e-12,atol=1e-14)
            publications+=len(events)
    print(f'1200 full native window producer calls matched {publications} publication pairs, all preintegration fields, current/retained windows scheduling timestamps and gap callbacks.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
