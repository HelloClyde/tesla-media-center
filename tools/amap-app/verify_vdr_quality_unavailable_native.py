"""Verify77770c native unavailable paths without model/resource substitution."""
import argparse
import hashlib
import io
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_D0,
    UC_ARM64_REG_TPIDR_EL0)
from vdr_quality_inference import quality_inference


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
    calls = []
    ready = False

    def callback(machine, address, size, user):
        calls.append(address)
        machine.reg_write(UC_ARM64_REG_X0, int(ready) if address == 0x1010000 else 0)
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x1010000, 0x1010010):
        uc.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)
    # ready virtual+10 and model virtual+18 (7798b8) are boundary stubs.
    uc.mem_write(0x1001000, struct.pack('<Q', 0x1002000))
    uc.mem_write(0x1002010, struct.pack('<2Q', 0x1010000, 0x1010010))
    class Backend:
        def ready(self): return ready
        def model(self): return None

    for present, ready in ((False, False), (True, False), (True, True)):
        calls.clear()
        uc.mem_write(0x1000788, struct.pack('<Q', 0x1001000 if present else 0))
        for reg, value in ((UC_ARM64_REG_X0, 0x1000000), (UC_ARM64_REG_X1, 0x1003000),
                           (UC_ARM64_REG_SP, 0x101e000), (UC_ARM64_REG_LR, 0x101f000),
                           (UC_ARM64_REG_TPIDR_EL0, 0x101f100)):
            uc.reg_write(reg, value)
        uc.emu_start(0x77770c, 0x101f000, count=10000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x101f000
        actual = struct.unpack('<d', struct.pack('<Q', uc.reg_read(UC_ARM64_REG_D0)))[0]
        assert actual == quality_inference([], Backend() if present else None) == -1.
        assert calls == ([] if not present else [0x1010000, 0x1010010] if ready else [0x1010000])
    print('Three complete native unavailable-model paths return -1 and match Python.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
