"""Inventory original App junction-image contracts; no rendering-success claim."""
import argparse
import hashlib
import json
import re
import zipfile
import io
import struct


def inspect(apk):
    result = {}
    with zipfile.ZipFile(apk) as archive:
        for library in ('libamaptbt.so', 'libamaphorus.so'):
            data = archive.read('lib/arm64-v8a/' + library)
            entries = []
            for match in re.finditer(rb'[\x20-\x7e]{8,400}', data):
                value = match.group()
                if any(term in value for term in (b'new_vector_cross/', b'<cross ', b'<pict ',
                        b'ServerCrossImageLoader::', b'VectorCrossImageProvider::',
                        b'WidgetCross::setVectorData', b'WidgetCross::setRasterData', b'isShowCrossImg')):
                    entries.append({'file_offset': hex(match.start()), 'text': value.decode('ascii')})
            result[library] = {'sha256': hashlib.sha256(data).hexdigest(), 'contracts': entries}
    return result


def request_evidence(apk):
    """Read observed road XML templates and their request-builder instructions."""
    from elftools.elf.elffile import ELFFile
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    with zipfile.ZipFile(apk) as archive:
        elf = ELFFile(io.BytesIO(archive.read('lib/arm64-v8a/libamaptbt.so')))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    def read(address, size):
        segment = next(s for s in segments if s['p_vaddr'] <= address
                       and address + size <= s['p_vaddr'] + s['p_filesz'])
        offset = address - segment['p_vaddr']
        return segment.data()[offset:offset+size]
    templates = {hex(address): read(address, 600).split(b'\0', 1)[0].decode('utf-8')
                 for address in (0xaa229, 0xb62ca, 0x94256, 0x10bd8f, 0xb6304,
                                 0x9f263, 0xe262d, 0xa2e57, 0xe9abf, 0x9b98d, 0xd9bc1)}
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    relocations = {item['r_offset']: item['r_addend']
                   for section in elf.iter_sections() if section['sh_type'] == 'SHT_RELA'
                   for item in section.iter_relocations() if item.is_RELA()}
    endpoint_profiles = []
    for address in range(0xf4e130, 0xf4e2b0, 0x30):
        path_address = relocations[address]
        category_address = relocations[address + 0x28]
        endpoint_profiles.append({
            'table_address': hex(address),
            'path': read(path_address, 80).split(b'\0', 1)[0].decode('ascii'),
            'request_kind': struct.unpack('<I', read(address + 8, 4))[0],
            'variant': struct.unpack('<I', read(address + 12, 4))[0],
            'transfer_variant': struct.unpack('<I', read(address + 16, 4))[0],
            'host_profile': read(relocations[address + 0x18], 32).split(b'\0', 1)[0].decode('ascii'),
            'category': read(category_address, 40).split(b'\0', 1)[0].decode('ascii'),
        })
    instructions = [f'{i.address:#x} {i.mnemonic} {i.op_str}'
                    for i in decoder.disasm(read(0xb7408c, 0x32c), 0xb7408c)]
    ranges = {
        'cross_parameter_builder': (0xb7440c, 0x764),
        'road_collection_builder': (0xb74fb4, 0x530),
        'link_to_road_record': (0xb77584, 0x158),
        'coordinate_getters': (0xcd8080, 0x60),
        'road_id_getter': (0xcd8160, 0x18),
        'road_attribute_getters': (0xcd82c0, 0x6c),
        'record_class_store': (0xb7a33c, 0xc),
        'record_form_store': (0xb7a424, 0xc),
        'record_id_and_attributes': (0xb7a5b8, 0x24),
        'segment_link_lookup': (0xce0624, 0x7c),
        'cross_http_submission': (0x78f280, 0x158),
        'cross_http_response': (0x78f65c, 0xd4),
        'cross_response_decoder': (0x78ff38, 0x298),
        'aos_profile_selection': (0x673354, 0x164),
    }
    sources = {name: [f'{i.address:#x} {i.mnemonic} {i.op_str}'
                     for i in decoder.disasm(read(address, size), address)]
               for name, (address, size) in ranges.items()}
    call_targets = {0xb6f830, 0xb6fd70, 0xb73ff0, 0xb74fb4,
                    0xb77584, 0xb72634, 0xb72be8}
    call_sites = {hex(target): [] for target in sorted(call_targets)}
    for segment in segments:
        if not segment['p_flags'] & 1:
            continue
        data, base = segment.data(), segment['p_vaddr']
        for offset in range(0, len(data) - 3, 4):
            opcode = struct.unpack_from('<I', data, offset)[0]
            if opcode >> 26 != 0b100101:  # AArch64 BL immediate
                continue
            displacement = opcode & 0x3ffffff
            if displacement & (1 << 25):
                displacement -= 1 << 26
            target = base + offset + displacement * 4
            if target in call_targets:
                call_sites[hex(target)].append(hex(base + offset))
    return {'templates': templates, 'endpoint_profiles': endpoint_profiles,
            'request_builder': instructions,
            'road_record_sources': sources,
            'native_call_sites': call_sites,
            'verified_getter_slots': {
                'road_id': 'link vtable+0x80 -> record+0x40 -> XML id',
                'rc': 'link vtable+0xf0 -> record+0 -> XML rc',
                'fw': 'link vtable+0xe8 -> record+4 -> XML fw',
                'coordinates': 'link vtable+0x38; count at +0x40',
                'coordinates3d': 'link vtable+0x48; count at +0x50',
            },
            'scope': 'Static evidence only; version-specific offsets; no successful request claimed'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--request-evidence', action='store_true')
    args = parser.parse_args()
    result = inspect(args.apk)
    if args.request_evidence:
        result['request_evidence'] = request_evidence(args.apk)
    print(json.dumps(result, indent=2, ensure_ascii=False))
