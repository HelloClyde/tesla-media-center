"""Reproduce pinned native evidence for ordinary/type-2 observation producers.

Static evidence only; does not infer upstream activation semantics from names.
"""
import argparse
import io
import zipfile
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from inspect_vdr_model import inspect

RANGES = (
    ('legacy engine allocation and interface return', 0x7dc3f0, 0x2c),
    ('legacy engine vtable initialization', 0x7dc1f0, 0x40),
    ('host engine creation', 0x75f508, 0x64),
    ('host queued record delivery', 0x75f8fc, 0x24),
    ('outer legacy record admission', 0x7dc4d0, 0xc4),
    ('outer extended record admission', 0x76a530, 0xb4),
    ('extended forwarding adapter', 0x76d2f8, 12),
    ('legacy external forwarding adapter', 0x76dbf4, 8),
    ('extended external forwarding adapter', 0x76dc40, 8),
    ('input record dispatcher A', 0x6a9f8c, 0xb0),
    ('input record dispatcher B', 0x6af870, 0x78),
    ('direct-origin record handler A', 0x6aa1a0, 0x50),
    ('direct-origin record handler B', 0x6aa29c, 0x34),
    ('offset-origin record handler', 0x6ad06c, 0x50),
    ('frame input dispatch from record+40', 0x6b46b0, 12),
    ('frame input direct dispatch', 0x6b4814, 12),
    ('fingerprint frame reset copy', 0x6a9680, 0x20),
    ('fingerprint frame origin input', 0x6aa8f4, 0x68),
    ('packed origin coordinate conversion', 0x6b4074, 0x24),
    ('fingerprint frame curvature scales', 0x6ada54, 0xe0),
    ('default root binding', 0x77aa70, 12),
    ('root source selection', 0x77accc, 0x88),
    ('external activation', 0x76dc70, 0x38),
    ('external fallback', 0x76de64, 0x5c),
    ('type-2 construction', 0x7c0f5c, 0xa0),
    ('type-2 observation generation', 0x7c0c50, 0x1bc),
    ('activation decision A', 0x6aa870, 0x40),
    ('activation decision B', 0x6ad1e4, 0x48),
    ('activation and heading flag', 0x6aaa34, 0x30),
    ('activation state predicate', 0x6b49b4, 16),
    ('fingerprint parser admission', 0x694304, 0x90),
    ('fingerprint parser result', 0x6946d8, 0x68),
    ('fingerprint container loading', 0x695874, 0x1e0),
    ('fingerprint decoder dispatch', 0x695a88, 0x88),
    ('download response admission and loading', 0x6963b8, 0xe0),
    ('decoder stream construction', 0x96f164, 20),
)


def report(apk, targets=()):
    contract = inspect(apk)
    print('Pinned library:', contract['library_sha256'])
    with zipfile.ZipFile(apk) as archive:
        elf = ELFFile(io.BytesIO(archive.read('lib/arm64-v8a/libamaploc.so')))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    targets = set(targets)
    for segment in segments:
        if not targets or not segment['p_flags'] & 1:
            continue
        raw = segment.data()
        for offset in range(0, len(raw) - 3, 4):
            word = struct.unpack_from('<I', raw, offset)[0]
            if word & 0xfc000000 not in (0x94000000, 0x14000000):
                continue
            delta = word & 0x3ffffff
            if delta & 0x2000000:
                delta -= 0x4000000
            address = segment['p_vaddr'] + offset
            target = address + delta * 4
            if target in targets:
                print('Direct call/tail-call', hex(address), '->', hex(target))
    for section in elf.iter_sections():
        if section['sh_type'] == 'SHT_RELA':
            for relocation in section.iter_relocations():
                if relocation['r_info_type'] == 1027 and relocation['r_addend'] in targets:
                    print('Relocated function pointer', hex(relocation['r_offset']),
                          '->', hex(relocation['r_addend']))
    address = 0xa8b11
    segment = next(s for s in segments if s['p_vaddr'] <= address
                   and address + 8 <= s['p_vaddr'] + s['p_filesz'])
    offset = address - segment['p_vaddr']
    for kind, delta in enumerate(segment.data()[offset:offset+8]):
        print('Input record kind dispatch', kind, hex(0x6a9fa4 + 4 * delta))
    for address in (0x95edf, 0x86445, 0x99fb6, 0x99fa1, 0x8fc76,
                    0x84299, 0x9bf52, 0x874e4):
        segment = next(s for s in segments if s['p_vaddr'] <= address
                       and address + 160 <= s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        message = segment.data()[offset:offset+160].split(b'\0', 1)[0].decode('utf-8')
        print('Native parser label', hex(address), message)
    address = 0xa130c8
    segment = next(s for s in segments if s['p_vaddr'] <= address
                   and address + 160 <= s['p_vaddr'] + s['p_filesz'])
    offset = address - segment['p_vaddr']
    print('Decoder descriptor first 160 bytes:', segment.data()[offset:offset+160].hex())
    for name, address, size in RANGES:
        segment = next(s for s in segments if s['p_vaddr'] <= address
                       and address + size <= s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        print('\n' + name)
        for instruction in decoder.disasm(segment.data()[offset:offset+size], address):
            print(hex(instruction.address), instruction.mnemonic, instruction.op_str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--callers', type=lambda value: int(value, 0), nargs='*', default=[])
    args = parser.parse_args()
    report(args.apk, args.callers)
