"""Find ARM64 ADR/ADRP+ADD string references, invalidating overwritten registers.

Linear basic-block scan only: absence is not proof of no references. Does not
track pointers through memory, calls, merges, or relocation tables.
"""
import argparse
import io
import zipfile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile


def find(apk, label, library='libamaploc.so'):
    if '/' in library or '\\' in library or not library.endswith('.so'):
        raise ValueError('Expected a library basename')
    with zipfile.ZipFile(apk) as archive:
        elf = ELFFile(io.BytesIO(archive.read('lib/arm64-v8a/' + library)))
    targets = set()
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD':
            continue
        data = segment.data()
        position = 0
        needle = label.encode() + b'\0'
        while (position := data.find(needle, position)) >= 0:
            targets.add(segment['p_vaddr'] + position)
            position += 1
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    decoder.detail = True
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD' or not segment['p_flags'] & 1:
            continue
        pages = {}
        decoder.skipdata = True
        for instruction in decoder.disasm(segment.data(), segment['p_vaddr']):
            if instruction.id == 0:
                pages.clear()
                continue
            operands = instruction.operands
            reference = None
            if instruction.mnemonic == 'adr' and operands[1].imm in targets:
                reference = operands[1].imm
            elif instruction.mnemonic == 'add' and len(operands) == 3 and operands[2].type == 2:
                base = pages.get(operands[1].reg)
                if base is not None:
                    value = base + (operands[2].imm << operands[2].shift.value)
                    if value in targets:
                        reference = value
            if reference is not None:
                print(f'{instruction.address:#x} -> {reference:#x}: {instruction.mnemonic} {instruction.op_str}')
            _, writes = instruction.regs_access()
            for register in writes:
                # Wn writes also invalidate Xn tracked addresses.
                name = instruction.reg_name(register)
                for tracked in list(pages):
                    if tracked == register or instruction.reg_name(tracked) == name.replace('w', 'x', 1):
                        pages.pop(tracked)
            if instruction.mnemonic == 'adrp':
                pages[operands[0].reg] = operands[1].imm
            if instruction.mnemonic in ('bl', 'blr', 'b', 'br', 'ret') or instruction.mnemonic.startswith('b.') or instruction.mnemonic in ('cbz', 'cbnz', 'tbz', 'tbnz'):
                pages.clear()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('label')
    parser.add_argument('--library', default='libamaploc.so')
    args = parser.parse_args()
    find(args.apk, args.label, args.library)
