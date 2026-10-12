"""Verify the pinned APK's 5.1 attribute -> RouteLink.getLinkType chain.

Executes the actual road-record assignment and DriveLinkImpl getter. Only the
getter's validity predicate is controlled. This is not an MM/floor detector.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X19,
    UC_ARM64_REG_X22, UC_ARM64_REG_X27, UC_ARM64_REG_X28,
    UC_ARM64_REG_X29, UC_ARM64_REG_SP)
from verify_road_switch_reroute_native import machine, returned

ASSEMBLY_SHA256 = 'a8adb7b4920008157938d58fbb5106cc917964eb2600e6b9df55f36a0a98328e'
TBT_SHA256 = 'ff471ba3c18ccf539a76fcb46b15408a733a4f3e33f03dc9abf55b7ac9cbbdb3'


def verify_word(native, value):
    uc = machine(native)
    parsed, record, owner, link, table, vector, stop = (
        0x2000000, 0x2000200, 0x2000400, 0x2000600, 0x2000800, 0x2000a00, 0x4000000)
    frame, stack = 0x300fd00, 0x300ff00
    for offset, word in ((0x40, 4), (0x48, 7), (0x50, value & 0xFFFFFFFF)):
        uc.mem_write(parsed+offset, struct.pack('<I', word))
    uc.mem_write(frame-0x20, struct.pack('<Q', record))
    uc.mem_write(stack+0x28, struct.pack('<Q', owner))
    for register, word in ((UC_ARM64_REG_X22, parsed), (UC_ARM64_REG_X27, 1),
        (UC_ARM64_REG_X28, 0), (UC_ARM64_REG_X29, frame), (UC_ARM64_REG_SP, stack)):
        uc.reg_write(register, word)
    # Run actual 0xbb8b0..0xbb908 stores, including packing adjacent flags.
    uc.emu_start(0xbb8b0, 0xbb90c, count=1000)
    if struct.unpack('<III', uc.mem_read(record, 12)) != (value & 0xFFFFFFFF, 7, 4):
        raise ValueError('native road-record assignment changed')
    uc.mem_write(link, struct.pack('<Q', table))
    uc.mem_write(table+0x10, struct.pack('<Q', stop+0x100))
    uc.mem_write(link+0xa0, struct.pack('<Q', owner))
    uc.mem_write(owner+0x88, struct.pack('<QQ', vector, vector+8))
    uc.mem_write(vector, struct.pack('<Q', record))
    def hook(uc, address, size, user):
        if address == stop+0x100: returned(uc, 1)
        elif address == stop: uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM64_REG_X0, link)
    uc.emu_start(0x944cc, stop, count=1000)
    result = uc.reg_read(UC_ARM64_REG_X0) & 0xFFFFFFFF
    result = result if result < 1 << 31 else result - (1 << 32)
    if result != value: raise ValueError('native link-type getter changed')


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        native = archive.read('lib/arm64-v8a/libassembly_kit.so')
        tbt = archive.read('lib/arm64-v8a/libamaptbt.so')
    if hashlib.sha256(native).hexdigest() != ASSEMBLY_SHA256 or hashlib.sha256(tbt).hexdigest() != TBT_SHA256:
        raise ValueError('link-type verifier requires the pinned APK')
    elf = ELFFile(io.BytesIO(tbt))
    relocations = {r['r_offset']: r['r_addend'] for section in elf.iter_sections()
        if section['sh_type'] == 'SHT_RELA' for r in section.iter_relocations()}
    if relocations.get(0xf441b8) != 0xcb803 or relocations.get(0xf441c8) != 0x4a7130:
        raise ValueError('nativeGetLinkType JNI registration changed')
    def read(address, size):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
            and s['p_vaddr'] <= address < s['p_vaddr']+s['p_filesz'])
        start = segment['p_offset']+address-segment['p_vaddr']
        return tbt[start:start+size]
    if read(0xcb803, 18).split(b'\0')[0] != b'nativeGetLinkType':
        raise ValueError('unexpected JNI name')
    # ldr x1,[x8,#0xe0]; restore frame; br x1.
    if read(0x4a7174, 12) != bytes.fromhex('017140f9fd7bc3a820001fd6'):
        raise ValueError('RouteLink JNI getter slot changed')
    values = [-1, 0, 1, 2, 3, 4, 5, (1 << 31)-1, -(1 << 31)]
    for value in values: verify_word(native, value)
    return {'nativeRecordAssignmentVerified': True, 'jniGetterSlot': '0xe0',
        'nativeGetterCases': len(values), 'attributeField': 3,
        'nativeFloorDetectionVerified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().apk), indent=2))
