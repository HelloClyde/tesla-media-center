"""Compare +7bd1a4 queue state/interpolation while executing its real callees."""
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
from vdr_attitude_calibration import CalibrationWindow
from vdr_sample_calibration import f32


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
    for section in elf.iter_sections():
        if section['sh_type'] == 'SHT_RELA':
            for relocation in section.iter_relocations():
                if relocation['r_info_type'] == 1027:
                    uc.mem_write(relocation['r_offset'], struct.pack('<Q', relocation['r_addend']))
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
        elif address == 0x9f2ba0:
            dst=machine.reg_read(UC_ARM64_REG_X0)
            value=machine.reg_read(UC_ARM64_REG_X1)&255
            length=machine.reg_read(UC_ARM64_REG_X2)
            machine.mem_write(dst,bytes([value])*length)
        elif address in (0x9f40d0, 0x9f2e20):
            value = struct.unpack('<d', struct.pack('<Q', machine.reg_read(UC_ARM64_REG_D0)))[0]
            if address == 0x9f40d0:
                result = math.acos(value) if -1 <= value <= 1 else math.nan
                machine.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d',result))[0])
            else:
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X0),struct.pack('<d',math.sin(value)))
                machine.mem_write(machine.reg_read(UC_ARM64_REG_X1),struct.pack('<d',math.cos(value)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0, 0x9f2c90, 0x9f40d0, 0x9f2e20, 0x9f2ba0):
        uc.hook_add(UC_HOOK_CODE, runtime, begin=address, end=address)

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    def call(entry, x1, x2=0, x3=0, x4=0, x0=0x1000000):
        for register, value in ((UC_ARM64_REG_X0, x0),
                                (UC_ARM64_REG_X1, x1), (UC_ARM64_REG_X2, x2), (UC_ARM64_REG_X3, x3), (UC_ARM64_REG_X4, x4),
                                (UC_ARM64_REG_SP, 0x101e000),
                                (UC_ARM64_REG_LR, 0x101f000),
                                (UC_ARM64_REG_TPIDR_EL0, 0x101f100)):
            uc.reg_write(register, value)
        try:
            uc.emu_start(entry, 0x101f000, count=2000000)
        except Exception as error:
            raise RuntimeError(f'PC={uc.reg_read(UC_ARM64_REG_PC):x}, LR={uc.reg_read(UC_ARM64_REG_LR):x}') from error
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x101f000
        return uc.reg_read(UC_ARM64_REG_X0)

    window=CalibrationWindow()
    call(0x7bd064,0)
    gps, gyroptr, accptr=0x100d000,0x100d100,0x100d200
    native_batches=[0]
    def batch(machine,address,size,user):
        native_batches[0]+=1
    uc.hook_add(UC_HOOK_CODE,batch,begin=0x7bd500,end=0x7bd500)
    for step in range(1200):
        timestamp=1000+step*40
        phase=step*.0064
        speed=20+4*math.sin(phase)
        longitudinal=4*.16*math.cos(phase)
        lateral=.3*math.sin(step*.0124)
        angle=math.radians(32)
        a=tuple(map(f32,(longitudinal*math.cos(angle)+lateral*math.sin(angle),
            longitudinal*math.sin(angle)-lateral*math.cos(angle),9.8)))
        g=tuple(map(f32,(0.,0.,-lateral/speed)))
        fix=step%25==0 and not 450<=step<575
        call(0x767b14,0,x0=gps)
        if fix:
            write(gps+8,'2i',0,timestamp)
            write(gps+0x38,'2d',120.,30.)
            write(gps+0x50,'d',speed)
            write(gps+0x60,'d',1.)
        for pointer,kind,values in ((gyroptr,2,g),(accptr,1,a)):
            write(pointer+8,'2i3f',kind,timestamp,*values)
        window.advance(timestamp,g,a,speed if fix else None)
        call(0x7bd1a4,gps,gyroptr,accptr)
        for offset,expected,stride in ((0x190,window.pending,32),
            (0x1f0,window.acceleration,24),(0x1d8,window.gyro,24),(0x208,window.speed,8)):
            begin,end=struct.unpack('<2Q',uc.mem_read(0x1000000+offset,16))
            assert (end-begin)//stride==len(expected),(step,hex(offset),(end-begin)//stride,len(expected))
            if stride==8:
                actual=struct.unpack(f'<{len(expected)}d',uc.mem_read(begin,len(expected)*8)) if expected else ()
                for x,y in zip(actual,expected):
                    assert math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12),(step,x,y)
            elif stride==24:
                for i,vector in enumerate(expected):
                    assert struct.unpack('<3d',uc.mem_read(begin+i*24,24))==vector,(step,offset,i)
            else:
                for i,(time,vector,_) in enumerate(expected):
                    assert struct.unpack('<i',uc.mem_read(begin+i*32+12,4))[0]==time
                    assert struct.unpack('<3f',uc.mem_read(begin+i*32+16,12))==vector
        assert native_batches[0]==window.batches,(step,native_batches,window.batches)
        ready = bool(uc.mem_read(0x10002b0, 1)[0])
        started = struct.unpack('<i', uc.mem_read(0x10002b4, 4))[0]
        assert (ready, started) == (window.fallback_ready, window.fallback_started)
        if ready:
            values = struct.unpack('<9d', uc.mem_read(0x1000220, 72))
            for row in range(3):
                for column in range(3):
                    assert math.isclose(values[column * 3 + row], window.fallback_rotation[row][column],
                                        rel_tol=1e-12, abs_tol=1e-12), (step, row, column)
    assert window.batches>0
    print(f'1200 complete native ingestion calls matched queues, speeds, {window.batches} batch triggers and fallback attitude/timing. GPS-quality gate not compared.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
