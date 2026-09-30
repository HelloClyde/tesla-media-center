"""Locate direct ARM64 references to the pinned VDR global configuration page.

Reports instruction evidence only; GOT/indirect references require separate work.
"""
import argparse
import hashlib
import io
import struct
import zipfile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile


def inspect(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
    if hashlib.sha256(data).hexdigest() != '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34':
        raise ValueError('Unsupported library build')
    elf = ELFFile(io.BytesIO(data))
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    def read(address, size):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                       and s['p_vaddr'] <= address and address + size <= s['p_vaddr'] + s['p_filesz'])
        start = address - segment['p_vaddr']
        return segment.data()[start:start+size]
    branch = 0x7e1188 + 4 * struct.unpack('<H', read(0xb9802 + 141*2, 2))[0]
    print('Registry 141 constructor branch:', hex(branch))
    integer_ids = []
    for address in (0x9d6b0, 0x9db20, 0x9e760, 0x9da10, 0x9e120, 0x9cc30, 0x9d7a0, 0x9dd00):
        integer_ids.extend(struct.unpack('<2Q', read(address, 16)))
    print('SIMD-selected integer update IDs:', integer_ids)
    print('141 uses direct integer update:', 141 in integer_ids)
    print('Root +0x10 constructor constant (two int32):', struct.unpack('<2i', read(0x795e8, 8)))
    for address, size in ((branch, 16), (0x7e192c, 8), (0x7e199c, 12),
                          (0x7e1f28, 36), (0x7f1728, 16), (0x7f1678, 24),
                          (0x7e0fd8, 52), (0x7e2ab8, 36)):
        for ins in decoder.disasm(read(address, size), address):
            print(hex(ins.address), ins.mnemonic, ins.op_str)
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD' or not segment['p_flags'] & 1:
            continue
        code, base = segment.data(), segment['p_vaddr']
        for offset in range(0, len(code)-3, 4):
            word = struct.unpack_from('<I', code, offset)[0]
            if word & 0x9f000000 != 0x90000000:
                continue
            imm = ((word >> 5) & 0x7ffff) << 2 | ((word >> 29) & 3)
            if imm & (1 << 20):
                imm -= 1 << 21
            if ((base+offset) & ~0xfff) + (imm << 12) != 0xa52000:
                continue
            instructions = list(decoder.disasm(code[offset:offset+64], base+offset))
            if any('#0x3b8' in ins.op_str for ins in instructions):
                print('\nReference', hex(base+offset))
                for ins in instructions:
                    print(hex(ins.address), ins.mnemonic, ins.op_str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    inspect(parser.parse_args().apk)
