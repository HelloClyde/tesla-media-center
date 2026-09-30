"""Execute actual filter-constructor prefix; verify embedded recovery defaults.

Stops before child constructors. Does not claim runtime overrides are absent.
"""
import argparse
import io
import struct
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_LR, UC_ARM64_REG_SP, UC_ARM64_REG_TPIDR_EL0, UC_ARM64_REG_PC
from inspect_vdr_model import inspect
from vdr_observation_binding import ObservationBinding, ObservationSource


def verify(apk):
    parameters = inspect(apk)  # Includes pinned library hash verification.
    with zipfile.ZipFile(apk) as archive:
        elf = ELFFile(io.BytesIO(archive.read('lib/arm64-v8a/libamaploc.so')))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    machine = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    extent = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    machine.mem_map(0, (extent + 4095) & ~4095)
    for segment in segments:
        machine.mem_write(segment['p_vaddr'], segment.data())
    machine.mem_map(0x1000000, 0x20000)
    machine.reg_write(UC_ARM64_REG_X0, 0x1000000)
    machine.reg_write(UC_ARM64_REG_SP, 0x101e000)
    machine.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x101f000)
    machine.emu_start(0x7d5080, 0x7d5168, count=1000)
    assert machine.reg_read(UC_ARM64_REG_PC) == 0x7d5168
    actual = struct.unpack('<2d', machine.mem_read(0x1000048, 16))
    expected = parameters['recovery_constructor_variance']
    assert actual == (expected['gyro'], expected['acceleration'])
    print('Native constructor recovery variances verified:', actual)
    # Verify observation flags at their real bind/refresh entry points. A type-2
    # object latches flag1, and its +288 byte controls flag2 on refresh. Binding
    # another type does not clear either flag; this matters across transitions.
    machine.mem_write(0x10004e1, b'\x00\x00')
    def call(entry):
        machine.reg_write(UC_ARM64_REG_X0, 0x1000000)
        machine.reg_write(UC_ARM64_REG_X1, 0x1008000)
        machine.reg_write(UC_ARM64_REG_LR, 0x101f100)
        machine.emu_start(entry, 0x101f100, count=1000)
        assert machine.reg_read(UC_ARM64_REG_PC) == 0x101f100
    binding = ObservationBinding()
    for kind, value, flags in ((1, 1, (0, 0)), (2, 1, (1, 1)),
                              (2, 0, (1, 0)), (2, 1, (1, 1)), (1, 0, (1, 1))):
        machine.mem_write(0x1008008, struct.pack('<I', kind))
        machine.mem_write(0x1008288, bytes([value]))
        call(0x7d6dd8)
        call(0x7d6df4)
        assert tuple(machine.mem_read(0x10004e1, 2)) == flags
        source = ObservationSource(kind, bool(value))
        binding.bind(source)
        assert binding.refresh() == tuple(bool(v) for v in flags)
    source = ObservationSource(2, False)
    binding.bind(source)
    machine.mem_write(0x1008008, struct.pack('<I', 2))
    call(0x7d6dd8)
    for enabled in (True, False, True):
        source.heading_enabled = enabled
        machine.mem_write(0x1008288, bytes([enabled]))
        call(0x7d6df4)
        assert binding.refresh() == tuple(bool(v) for v in machine.mem_read(0x10004e1, 2))
    print('Native observation flags: type-2 latch and live +288 refresh verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
