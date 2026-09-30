"""Compare complete native transition routines, with callback bodies stubbed."""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6,
    UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC,
)
from vdr_state_transition import ManagerState, ObserverActivation, signed32


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
    uc.mem_map(0x1000000, 0x30000)
    root, observer, table, end = 0x1000000, 0x1010000, 0x1011000, 0x102f000
    notify, trailing, enabled, disabled = 0x1020000, 0x1020010, 0x1020020, 0x1020030
    events = []

    def write(address, fmt, *values):
        uc.mem_write(address, struct.pack('<' + fmt, *values))

    def hook(machine, address, size, user):
        args = [machine.reg_read(reg) & 0xffffffff for reg in (
            UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
            UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6)]
        if address == notify:
            events.append(('notify', signed32(args[0]), args[1], args[2],
                           signed32(args[3]), signed32(args[4]), args[5]))
        elif address == trailing:
            events.append(('trailing', *map(signed32, args[:3])))
        elif address in (enabled, disabled):
            events.append(('enabled' if address == enabled else 'disabled', signed32(args[0])))
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    for address in (notify, trailing, enabled, disabled, 0x773584):
        uc.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)

    def call(entry, obj, *args):
        for reg, value in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                               UC_ARM64_REG_X3, UC_ARM64_REG_X4), (obj, *args)):
            uc.reg_write(reg, value & 0xffffffffffffffff)
        uc.reg_write(UC_ARM64_REG_SP, 0x102e000)
        uc.reg_write(UC_ARM64_REG_LR, end)
        uc.emu_start(entry, end, count=10000)
        assert uc.reg_read(UC_ARM64_REG_PC) == end

    write(root, 'Q', table)
    write(table + 0x38, 'Q', notify)
    write(root + 0xd30, 'Q', observer)
    write(observer, 'Q', table + 0x100)
    write(table + 0x120, 'Q', trailing)
    # Empty observer vectors isolate manager bookkeeping and notification.
    state = ManagerState(1, -1, 0, -1)
    write(root + 0x2c, '4i', state.state, state.state_since, state.reason, state.reason_since)
    rng = random.Random(770018)
    for index in range(1000):
        target = rng.choice((1, 2, 4, 8, 16, 32, 64, state.state))
        timestamp = rng.choice((-1, 0, 1000 + index * 20, 2147483647, -2147483648))
        reason, forced = rng.choice((0, 1, 16, state.reason)), rng.randrange(2)
        events.clear()
        call(0x77ae18, root, target, timestamp, reason, forced)
        expected = []
        state.transition(target, timestamp, reason, forced,
                         lambda *args: expected.append(('notify', *args)), [],
                         lambda *args: expected.append(('trailing', *args)))
        assert events == expected, (index, events, expected)
        assert struct.unpack('<4i', uc.mem_read(root + 0x2c, 16)) == (
            state.state, state.state_since, state.reason, state.reason_since)

    write(table + 0x100, '2Q', enabled, disabled)
    activation = ObserverActivation(0)
    for index in range(1000):
        activation.mask = rng.choice((0, 1, 6, 24, 63, 0x80000000, 0xffffffff))
        target, timestamp = rng.choice((1, 2, 4, 8, 16, 32, 64, -2147483648)), 1000 + index * 20
        write(observer + 8, 'IiB', activation.mask, activation.started, activation.enabled)
        events.clear()
        call(0x7799dc, observer, timestamp, target)
        expected = []
        activation.transition(timestamp, target,
                              lambda t: expected.append(('enabled', t)),
                              lambda t: expected.append(('disabled', t)))
        assert events == expected
        assert struct.unpack('<iB', uc.mem_read(observer + 12, 5)) == (activation.started, activation.enabled)
    print('Native transitions: 1000 manager calls and 1000 observer calls matched.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
