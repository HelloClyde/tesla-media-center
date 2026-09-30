"""Inspect pinned APK VDR model contract and embedded linear-score parameters.

No network access or model substitution. A missing named ZIP entry is not proof
that the model is absent from packaged containers or downloaded resources.
"""
import argparse
import hashlib
import io
import json
import struct
import zipfile
from elftools.elf.elffile import ELFFile


def inspect(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read('lib/arm64-v8a/libamaploc.so')
        digest = hashlib.sha256(data).hexdigest()
        if digest != '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34':
            raise ValueError('Unsupported libamaploc build; reverify addresses first')
        elf = ELFFile(io.BytesIO(data))

        def read(address, length):
            segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                           and s['p_vaddr'] <= address
                           and address + length <= s['p_vaddr'] + s['p_filesz'])
            offset = address - segment['p_vaddr']
            return segment.data()[offset:offset + length]

        def string(address):
            return read(address, 128).split(b'\0', 1)[0].decode('ascii')

        name = string(0x92a2a)
        candidates = [n for n in archive.namelist() if name in n or 'vdr_confidence' in n.lower()]
        return {
            'library_sha256': digest,
            'registry_type': 6,
            'resource_name': name,
            'input_name': string(0x9612a),
            'output_name': string(0x93f82),
            'matching_zip_entries': candidates,
            'resource_resolution_verified': False,
            # 7d5080 constructor: 7d512c -> object+48, 7d5150 -> object+50.
            # These are constructor defaults, not proof of later overrides.
            'recovery_constructor_variance': {
                'gyro': struct.unpack('<d', read(0x9d2e8, 8))[0],
                'acceleration': struct.unpack('<d', read(0x9e870, 8))[0],
            },
            'linear_score': {
                'feature_count': 55,
                'means': struct.unpack('<55d', read(0xb0320, 440)),
                'scales': struct.unpack('<55d', read(0xb04d8, 440)),
                'coefficients': struct.unpack('<55d', read(0xb0690, 440)),
                'bias': struct.unpack('<d', struct.pack('<Q', 0x406cf2b18548a9bd))[0],
            },
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    args = parser.parse_args()
    print(json.dumps(inspect(args.apk), ensure_ascii=False, indent=2, allow_nan=False))
