"""Compare complete native weighted-history initialization, update, reset and mean."""
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
    UC_ARM64_REG_D0, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_weighted_history import WeightedHistory


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
    uc.mem_map(0x2000000, 0x100000)
    heap = 0x2000000

    def runtime(machine, address, size, user):
        nonlocal heap
        if address in (0x9f2fb0, 0x9f2b50):
            length = machine.reg_read(UC_ARM64_REG_X0)
            result = heap
            heap += (length + 15) & ~15
            assert heap < 0x2100000
            machine.mem_write(result, bytes(length))
            machine.reg_write(UC_ARM64_REG_X0, result)
        elif address == 0x9f2bd0:
            dst = machine.reg_read(UC_ARM64_REG_X0)
            src = machine.reg_read(UC_ARM64_REG_X1)
            length = machine.reg_read(UC_ARM64_REG_X2)
            if length:
                machine.mem_write(dst, bytes(machine.mem_read(src, length)))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (0x9f2fb0, 0x9f2f80, 0x9f2b50, 0x9f2b20, 0x9f2bd0):
        uc.hook_add(UC_HOOK_CODE, runtime, begin=address, end=address)

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    def call(entry, x1, x2=0):
        for register, value in ((UC_ARM64_REG_X0, 0x1000000),
                                (UC_ARM64_REG_X1, x1), (UC_ARM64_REG_X2, x2),
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

    def double(value):
        uc.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', value))[0])

    def close(a, b):
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a, b)

    rng = random.Random(20260928)
    updates = 0
    for decay in (0., .5, .95, 1.):
        heap = 0x2000000
        state = WeightedHistory(decay)
        double(decay)
        call(0x76848c, 0)
        write(0x1000200, '2Q', 0, 0)
        assert call(0x7685dc, 0x1000200) == 0
        for step in range(100):
            if step == 50:
                state.reset()
                call(0x7685cc, 0)
                assert call(0x7685dc, 0x1000200) == 0
            values = [rng.uniform(-10, 10) for _ in range(9)]
            weight = (0., 0.999e-6, 1e-6, 1., .5)[step % 5]
            write(0x1000100, '2Q', 0x1001000, len(values))
            write(0x1001000, '9d', *values)
            double(weight)
            call(0x7684a4, 0x1000100)
            state.add(values, weight)
            close(struct.unpack('<d', uc.mem_read(0x1000008, 8))[0], state.weight)
            close(struct.unpack('<d', uc.mem_read(0x1000028, 8))[0], state.total_weight)
            pointer, length = struct.unpack('<2Q', uc.mem_read(0x1000010, 16))
            assert length == 9
            for actual, expected in zip(struct.unpack('<9d', uc.mem_read(pointer, 72)), state.values):
                close(actual, expected)
            result = call(0x7685dc, 0x1000200)
            mean = state.mean()
            assert bool(result) == (mean is not None), (decay, step)
            if mean is not None:
                pointer, length = struct.unpack('<2Q', uc.mem_read(0x1000200, 16))
                assert length == 9
                for actual, expected in zip(struct.unpack('<9d', uc.mem_read(pointer, 72)), mean):
                    close(actual, expected)
            updates += 1
    print(f'{updates} native history updates and means matched, including resets, decay and weight thresholds; only allocation/copy hooks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
