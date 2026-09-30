"""Differential test of the Python selection port against the pinned ARM64 code.

Only external registry lookups and diagnostics are fixture callbacks. The original
selection instructions execute unchanged; this does not test location propagation.
"""
import argparse
import hashlib
import io
import random
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC
from tunnel_mode_selection import Selection, enforce_tunnel_dr


def native(code, current, state, candidates, types, available):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for base, length in ((0x45d000, 0x2000), (0x81f000, 0x2000),
                         (0x471000, 0x1000), (0x700000, 0x10000),
                         (0x800000, 0x10000), (0x900000, 0x1000)):
        uc.mem_map(base, length)
    uc.mem_write(0x45dfbc, code)
    uc.mem_write(0x700000, struct.pack('<III', current.status, current.algorithm_id, current.extra))
    uc.mem_write(0x7001d0, struct.pack('<I', state))
    uc.mem_write(0x700200, struct.pack('<QQ', 0x700300, len(candidates)))
    # Native loads IDs from the second half of the double buffer.
    uc.mem_write(0x700300, bytes(8 * len(candidates)) + b''.join(struct.pack('<d', x) for x in candidates))
    objects = {key: 0x701000 + index * 0x100 for index, key in enumerate(types)}
    object_types = {objects[key]: value for key, value in types.items()}

    def hook(machine, address, size, _):
        if address == 0x81fc5c:
            value = 1 if available else 0
        elif address == 0x820388:
            value = objects.get(machine.reg_read(UC_ARM64_REG_X1), 0)
        elif address == 0x45e0c4:
            value = object_types[machine.reg_read(UC_ARM64_REG_X0)]
        elif address == 0x471520:
            value = 0  # Diagnostic log, no selection state effect.
        else:
            return
        machine.reg_write(UC_ARM64_REG_X0, value)
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, hook)
    for reg, value in ((UC_ARM64_REG_X1, 0x700000), (UC_ARM64_REG_X2, 0x700100),
                       (UC_ARM64_REG_X3, 0x700200), (UC_ARM64_REG_SP, 0x80f000),
                       (UC_ARM64_REG_LR, 0x900000)):
        uc.reg_write(reg, value)
    uc.emu_start(0x45dfbc, 0x900000, count=10000)
    if uc.reg_read(UC_ARM64_REG_PC) != 0x900000:
        raise AssertionError('Native selection did not return')
    packed = uc.reg_read(UC_ARM64_REG_X0)
    return Selection(packed & 0xffffffff, packed >> 32, uc.reg_read(UC_ARM64_REG_X1) & 0xffffffff)


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    if hashlib.sha256(data).hexdigest() != '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34':
        raise ValueError('Unsupported binary')
    elf = ELFFile(io.BytesIO(data))
    segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= 0x45dfbc < s['p_vaddr'] + s['p_filesz'])
    offset = 0x45dfbc - segment['p_vaddr']
    code = segment.data()[offset:offset + 0x118]
    rng = random.Random(20260928)
    for index in range(200):
        original = Selection(rng.randrange(4), rng.randrange(8), rng.randrange(100))
        types = {key: rng.choice((1, 2, 3, 258)) for key in range(8) if rng.random() > .2}
        candidates = rng.sample(range(10), rng.randrange(10))
        state = rng.choice((4, 5, 5, 5))
        available = rng.random() > .1
        expected = native(code, original, state, candidates, types, available)
        actual = enforce_tunnel_dr(original, state, candidates, types, available)
        if actual != expected:
            raise AssertionError((index, expected, actual))
    print('200 native/Python selection comparisons passed; position propagation is NOT verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
