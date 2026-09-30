"""Verify native signal conversion + VDR input handlers against Python.

Only the event pool allocator and downstream broadcaster are substituted.
This tests input adaptation, not downstream integration or full navigation.
"""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1,
    UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)
from vdr_sample_calibration import prepare_sensor_sample


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    machine.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        machine.mem_write(segment['p_vaddr'], segment.data())
    machine.mem_map(0x1000000, 0x20000)
    emitted = []

    def boundary(uc, address, size, user):
        if address == 0x8fd2ac:  # pool singleton; no sample calculations
            uc.reg_write(UC_ARM64_REG_X0, 0x1015000)
        elif address == 0x8fd390:  # pool allocation
            uc.reg_write(UC_ARM64_REG_X0, 0x1012000)
        elif address == 0x76d344:  # capture the real handler's output
            emitted.append(bytes(uc.mem_read(uc.reg_read(UC_ARM64_REG_X1), 32)))
        else:
            return
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    for address in (0x8fd2ac, 0x8fd390, 0x76d344):
        machine.hook_add(UC_HOOK_CODE, boundary, begin=address, end=address)

    def call(entry, first, second=0):
        for register, value in ((UC_ARM64_REG_X0, first), (UC_ARM64_REG_X1, second),
                                (UC_ARM64_REG_SP, 0x101e000), (UC_ARM64_REG_LR, 0x101f000),
                                (UC_ARM64_REG_TPIDR_EL0, 0x101f100)):
            machine.reg_write(register, value)
        try:
            machine.emu_start(entry, 0x101f000, count=10000)
        except Exception as error:
            raise RuntimeError(f'entry={entry:x}, pc={machine.reg_read(UC_ARM64_REG_PC):x}, lr={machine.reg_read(UC_ARM64_REG_LR):x}') from error
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x101f000

    rng = random.Random(20260928)
    calls = 0
    for kind, raw_type, conversion, handler, primary_offset, bias_offset, internal_type in (
            ('accelerometer', 2, 0x81358c, 0x769cbc, 0x30, 0xc890, 1),
            ('gyroscope', 4, 0x8135cc, 0x769da8, 0x34, 0xc8a0, 2)):
        for case in range(500):
            machine.mem_write(0x1000000, bytes(0xd000))
            machine.mem_write(0xa523e0, struct.pack('<QQ', 100000, 100000))
            bias = None
            for step in range(2):
                primary = tuple(rng.uniform(-10, 10) for _ in range(3))
                alternate = tuple(rng.uniform(-10, 10) for _ in range(3))
                if case % 5 == 0:
                    primary = (0., 0., 0.)
                elif case % 5 == 1:
                    primary = (1e-6, -1e-6, 0.)
                if case % 7 == 0:
                    alternate = (1000., 1000., 1000.)
                raw = bytearray(0x60)
                timestamp = 100040 + step * 40
                struct.pack_into('<I', raw, 8, raw_type)
                struct.pack_into('<QQ', raw, 0x10, timestamp, timestamp + 10)
                # Verified JNI writes z,x,y in PosSignal; converters/handlers
                # restore x,y,z. Gyro has one additional scalar before these.
                struct.pack_into('<3f', raw, primary_offset, primary[2], primary[0], primary[1])
                struct.pack_into('<3f', raw, primary_offset + 12, alternate[2], alternate[0], alternate[1])
                machine.mem_write(0x1011000, bytes(raw))
                call(conversion, 0x1011000)
                emitted.clear()
                # Isolate sample adaptation from the separate delivery-latency
                # watchdog, whose provider is not constructed in this fixture.
                # Keep calibration state intact across both samples.
                machine.mem_write(0x100c87c, bytes(4))
                call(handler, 0x1000000, 0x1012000)
                expected = prepare_sensor_sample(kind, primary, alternate, bias)
                if expected is None:
                    assert not emitted, (kind, case, step, 'zero gate')
                else:
                    values, used, bias = expected
                    assert len(emitted) == 1, (kind, case, step)
                    record = emitted[0]
                    assert record[8:16] == struct.pack('<II', internal_type, timestamp - 100000)
                    assert record[16:28] == struct.pack('<3f', *values), (kind, case, step)
                    assert record[28] == used
                state = bytes(machine.mem_read(0x1000000 + bias_offset, 16))
                assert bool(state[0]) == (bias is not None)
                if bias is not None:
                    assert state[4:16] == struct.pack('<3f', *bias)
                calls += 1
    print(f'{calls} native signal-conversion + VDR-input calls matched Python. Allocation/broadcast were substituted and the latency watchdog was reset between inputs; full navigation remains unverified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
