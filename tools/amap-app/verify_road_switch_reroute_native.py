"""Execute the pinned APK's avoid-link primitives with controlled native inputs.

Checks real ARM64 sampling, XML calls and float formatting conversions.
The XML container/printf calls are observed with bounded substitutes; nearby
candidate generation, flag derivation and HTTP acceptance are separate work.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_TPIDR_EL0, UC_ARM64_REG_D0)
from xml.sax.saxutils import escape
from road_switch_request import avoid_link_pair, encode_start_avoid_link

HORUS_SHA256 = 'cc8bc29dfb2116e7d6289e0f5fcd613c5e76d8fc396dc9ceafd3436ade004684'


def machine(native):
    elf = ELFFile(io.BytesIO(native))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD': continue
        address, size = segment['p_vaddr'], segment['p_memsz']
        start = address & ~4095
        uc.mem_map(start, (address - start + size + 4095) & ~4095)
        uc.mem_write(address, segment.data())
    for base in (0x2000000, 0x3000000, 0x4000000): uc.mem_map(base, 0x10000)
    uc.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x200f000)
    uc.reg_write(UC_ARM64_REG_SP, 0x300ff00)
    uc.reg_write(UC_ARM64_REG_LR, 0x4000000)
    return uc


def returned(uc, value):
    uc.reg_write(UC_ARM64_REG_X0, value)
    uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))


def verify_pair(native, points):
    uc = machine(native)
    path, segment, link, coordinates, output = (0x2000000, 0x2000100, 0x2000200, 0x2000400, 0x2000800)
    uc.mem_write(coordinates, b''.join(struct.pack('<ii', *point) for point in points))
    def hook(uc, address, size, user):
        values = {0xc6c6d0: segment, 0xc6c3fc: 1, 0xc6c510: 1,
                  0xc6c64c: link, 0xc6c8b4: coordinates, 0xc6c94c: len(points)}
        if address in values: returned(uc, values[address])
        elif address == 0x4000000: uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hook)
    for register, value in ((UC_ARM64_REG_X0, 1), (UC_ARM64_REG_X1, output),
                            (UC_ARM64_REG_X2, path), (UC_ARM64_REG_X3, 0), (UC_ARM64_REG_X4, 0)):
        uc.reg_write(register, value)
    uc.emu_start(0xc660c8, 0x4000000, count=5000)
    count = uc.reg_read(UC_ARM64_REG_X0)
    pair = None if not count else tuple(tuple(struct.unpack('<ii', uc.mem_read(output+index*8, 8))) for index in range(2))
    if pair != avoid_link_pair(points): raise ValueError('native avoid-link sampling mismatch')
    return pair


def verify_xml(native, pairs, hwflag, switchaction):
    uc = machine(native)
    root, coordinates = 0x2000000, 0x2000400
    uc.mem_write(coordinates, b''.join(struct.pack('<iiii', *pair[0], *pair[1]) for pair in pairs))
    nodes = {root: {'name': 'route', 'children': [], 'attributes': {}, 'text': ''}}
    def string(pointer):
        data = bytearray()
        for index in range(512):
            value = uc.mem_read(pointer+index, 1)[0]
            if not value: return data.decode('ascii')
            data.append(value)
        raise ValueError('oversized native string')
    def hook(uc, address, size, user):
        a, b, c = [uc.reg_read(register) for register in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        if address == 0xdc78a0:
            pointer = 0x2001000 + len(nodes)*16
            nodes[pointer] = {'name': string(b), 'children': [], 'attributes': {}, 'text': ''}
            nodes[a]['children'].append(pointer); returned(uc, pointer)
        elif address == 0xdc78b0:
            nodes[a]['attributes'][string(b)] = string(c); returned(uc, a)
        elif address == 0xdc79f0:
            value = string(b)
            if c not in (0, len(value)): raise ValueError('unexpected native XML text length')
            nodes[a]['text'] += value; returned(uc, a)
        elif address == 0xc6a798:
            fmt = string(uc.reg_read(UC_ARM64_REG_X3))
            if fmt == '%d':
                value = uc.reg_read(UC_ARM64_REG_X4) & 0xFFFFFFFF
                if value >= 1 << 31: value -= 1 << 32
                formatted = str(value)
            elif fmt == '%f':
                value = struct.unpack('<d', struct.pack('<Q', uc.reg_read(UC_ARM64_REG_D0)))[0]
                formatted = f'{value:.6f}'
            else: raise ValueError('unexpected native format')
            uc.mem_write(a, formatted.encode()+b'\0'); returned(uc, len(formatted))
        elif address == 0xc6c3c4: returned(uc, len(string(a)))
        elif address == 0x4000000: uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, hook)
    for register, value in ((UC_ARM64_REG_X1, root), (UC_ARM64_REG_X2, coordinates),
                            (UC_ARM64_REG_X3, len(pairs)), (UC_ARM64_REG_X4, hwflag), (UC_ARM64_REG_X5, switchaction)):
        uc.reg_write(register, value)
    uc.emu_start(0xc671c0, 0x4000000, count=10000)
    def xml(pointer):
        node = nodes[pointer]
        attributes = ''.join(f' {key}="{value}"' for key, value in node['attributes'].items())
        return '<'+node['name']+attributes+'>'+escape(node['text'])+''.join(xml(child) for child in node['children'])+'</'+node['name']+'>'
    fragment = xml(nodes[root]['children'][0]).encode('ascii')
    if fragment != encode_start_avoid_link(pairs, hwflag, switchaction):
        raise ValueError('native startAvoidLink XML mismatch')


def verify(apk):
    with zipfile.ZipFile(apk) as archive: native = archive.read('lib/arm64-v8a/libamaphorus.so')
    if hashlib.sha256(native).hexdigest() != HORUS_SHA256:
        raise ValueError('avoid-link verifier requires the pinned APK native library')
    samples = [[], [(432000001, 108000001)],
               [(432000001, 108000001), (432000009, 108000010)],
               [(-432000001, -108000001), (-432000009, -108000010)],
               [(600000001, 200000001), (600000009, 200000010)],
               [(432000000+index*100, 108000000+index*200) for index in range(3)],
               [(432000000+index*100, 108000000+index*200) for index in range(4)],
               [(432000000+index*100, 108000000+index*200) for index in range(5)],
               [(432000000+index*100, 108000000+index*200) for index in range(10)]]
    pairs = [verify_pair(native, sample) for sample in samples]
    valid = [pair for pair in pairs if pair is not None]
    for hwflag, action in ((0, 1), (0, 2), (1, 0), (6, 3), (255, 128)):
        verify_xml(native, valid, hwflag, action)
    return {'nativeSha256': hashlib.sha256(native).hexdigest(), 'samplingCases': len(samples),
            'xmlCases': 5, 'nativeAvoidLinkSamplingVerified': True, 'nativeAvoidLinkXMLVerified': True,
            'nearbyCandidatesVerified': False, 'switchFlagsDerivationVerified': False, 'HTTPAcceptanceVerified': False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk',type=Path,required=True)
    print(json.dumps(verify(parser.parse_args().apk),indent=2))
