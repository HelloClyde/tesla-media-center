"""Run native dispatch block +77b360..77b3e0 and sample loop +779a34.

Observer bodies and the empty GPS constructor are boundary stubs. This checks
native ordering/arguments/flags/clearing, not observer algorithms or the full
manager publication function.
"""
import argparse
import hashlib
import io
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X19,
    UC_ARM64_REG_X21, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0,
)
from vdr_window_dispatch import DispatchWindow, SamplePair, dispatch_window


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    assert hashlib.sha256(data).hexdigest() == (
        '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34')
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    machine.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        machine.mem_write(segment['p_vaddr'], segment.data())
    machine.mem_map(0x1000000, 0x40000)
    root, window, samples = 0x1000000, 0x1010000, 0x1011000
    observers, table, pointers = 0x1014000, 0x1015000, 0x1016000
    sample_callback, publish_callback, trailing_callback = 0x1030000, 0x1030010, 0x1030020
    native_events = []

    def write(address, fmt, *values):
        machine.mem_write(address, struct.pack('<' + fmt, *values))

    def read(address, fmt):
        return struct.unpack('<' + fmt, machine.mem_read(address, struct.calcsize('<' + fmt)))

    def hook(uc, address, size, user):
        if address == 0x77b3e0:
            uc.emu_stop()
            return
        x0 = uc.reg_read(UC_ARM64_REG_X0)
        if address == 0x767b14:
            # Empty GPS contents are not inspected by the replay loop.
            uc.mem_write(x0, bytes(0x78))
        elif address == sample_callback:
            index = (x0 - observers) // 0x20
            first = uc.reg_read(UC_ARM64_REG_X3)
            second = uc.reg_read(UC_ARM64_REG_X4)
            native_events.append((index, 'sample', uc.reg_read(UC_ARM64_REG_X1),
                                  uc.reg_read(UC_ARM64_REG_X2) == window + 0x338,
                                  (first - samples) // 0x40,
                                  second - first))
        elif address == publish_callback:
            native_events.append(((x0 - observers) // 0x20, 'publish',
                                  uc.reg_read(UC_ARM64_REG_X1) == window))
        elif address == trailing_callback:
            native_events.append(('trailing', uc.reg_read(UC_ARM64_REG_X1) == window + 0x338,
                                  uc.reg_read(UC_ARM64_REG_X2) == window + 0x3c0))
        else:
            return
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    for address in (0x77b3e0, 0x767b14, sample_callback, publish_callback, trailing_callback):
        machine.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)

    class Observer:
        def __init__(self, index, enabled, replay_enabled, events):
            self.index, self.enabled, self.replay_enabled = index, enabled, replay_enabled
            self.events = events

        def sample(self, timestamp, gps, first, second):
            self.events.append((self.index, 'sample', timestamp, gps, first, second))

        def publish(self, payload):
            self.events.append((self.index, 'publish', payload))

    cases = 0
    for count in (0, 1, 2, 17):
        for flags in range(256):
            for processed in (False, True):
                native_events.clear()
                python_events = []
                write(root + 0x9cf8, '3Q', pointers, pointers + 32, pointers + 32)
                write(root + 0xd30, 'Q', observers + 0x100)
                write(observers + 0x100, 'Q', table + 0x100)
                write(table + 0x118, 'Q', trailing_callback)
                write(table + 0x10, '2Q', sample_callback, publish_callback)
                python_observers = []
                for index in range(4):
                    enabled, replay = bool(flags & (1 << (index * 2))), bool(flags & (2 << (index * 2)))
                    write(pointers + index * 8, 'Q', observers + index * 0x20)
                    write(observers + index * 0x20, 'Q', table)
                    write(observers + index * 0x20 + 0x10, '2B', enabled, replay)
                    python_observers.append(Observer(index, enabled, replay, python_events))
                write(window + 0x3c0, '3Q', samples, samples + count * 0x40, samples + count * 0x40)
                write(window + 0x3e0, 'B', processed)
                for index in range(count):
                    write(samples + index * 0x40 + 0xc, 'i', 1000 + index * 20)
                for register, value in (
                    (UC_ARM64_REG_X19, root), (UC_ARM64_REG_X21, window),
                    (UC_ARM64_REG_SP, 0x102e000), (UC_ARM64_REG_TPIDR_EL0, 0x102f000),
                ):
                    machine.reg_write(register, value)
                machine.emu_start(0x77b360, 0x1031000, count=100000)
                assert machine.reg_read(UC_ARM64_REG_PC) == 0x77b3e0
                python_window = DispatchWindow(True, True, [
                    SamplePair(1000 + index * 20, index, 0x20) for index in range(count)], processed)
                dispatch_window(python_window, python_observers,
                                lambda gps, values: python_events.append(('trailing', gps, True)),
                                lambda: False)
                assert native_events == python_events, (count, flags, processed, native_events, python_events)
                assert bool(read(window + 0x3e0, 'B')[0]) == python_window.processed
                assert (read(window + 0x3c8, 'Q')[0] - samples) // 0x40 == len(python_window.samples)
                cases += 1
    print(f'Native window dispatch: {cases} cases matched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
