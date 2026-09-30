"""Compare native default parameters and covariance initialization/reset."""
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
from vdr_filter_initialization import initial_covariances, DEFAULT_STATE_VARIANCES, DEFAULT_NOISE_VARIANCES
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





    call(0x7d5080,0)
    params=struct.unpack('<13d',uc.mem_read(0x1000000,104))
    assert params==DEFAULT_NOISE_VARIANCES+DEFAULT_STATE_VARIANCES
    rng=np.random.default_rng(20260928)
    for case in range(100):
        noise=DEFAULT_NOISE_VARIANCES if case==0 else tuple(10.**rng.uniform(-10,2,6))
        state=DEFAULT_STATE_VARIANCES if case==0 else tuple(10.**rng.uniform(-10,2,7))
        write(0x1000000,'13d',*(noise+state))
        # Reset must clear pre-existing cross terms, not just set diagonals.
        ptr=struct.unpack('<Q',uc.mem_read(0x10001a0,8))[0]
        uc.mem_write(ptr,rng.normal(size=(21,21)).astype('<f8').tobytes())
        call(0x7d51f8,0)
        for off,expected in zip((0x1a0,0x1b8),initial_covariances(state,noise)):
            ptr,rows,cols=struct.unpack('<3Q',uc.mem_read(0x1000000+off,24))
            actual=np.frombuffer(uc.mem_read(ptr,rows*cols*8),dtype='<f8').reshape((rows,cols),order='F')
            np.testing.assert_array_equal(actual,expected)
    print('Native constructor defaults and 100 covariance resets matched exactly, including clearing existing cross terms.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
