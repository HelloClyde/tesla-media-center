import json
import struct
import unittest

from native_model import extract_models, validate_glb


def fixture(external=False):
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 4}],
           'bufferViews': [{'buffer': 0, 'byteLength': 4}]}
    if external:
        doc['buffers'][0]['uri'] = 'https://example.invalid/model.bin'
    raw = json.dumps(doc).encode()
    raw += b' ' * (-len(raw) % 4)
    glb = (struct.pack('<4sII', b'glTF', 2, 32 + len(raw)) +
           struct.pack('<I4s', len(raw), b'JSON') + raw +
           struct.pack('<I4s', 4, b'BIN\0') + b'abcd')
    metadata = (struct.pack('<II', 12, 76) + bytes(24) +
                struct.pack('<II', 2, 8) + b'raw_gltf' + bytes(24) +
                struct.pack('<I', 100 + len(glb)))
    payload = struct.pack('<III', 13, len(glb) + 24, len(glb)) + glb + struct.pack('<III', 11, 0, 0)
    data = struct.pack('<7I', 0xffffffff, 0x8f0584f6, 20,
                       28 + len(metadata) + len(payload), 0, 0, 1) + metadata + payload
    return data, glb


class NativeModelTests(unittest.TestCase):
    def test_exact_payload_preserved(self):
        data, glb = fixture()
        self.assertEqual(extract_models(data), [glb])

    def test_all_truncations_rejected(self):
        data, _ = fixture()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                extract_models(data[:end])

    def test_sizes_types_and_trailer_rejected(self):
        data, _ = fixture()
        for offset in [0, 4, 8, 12, 16, 24, 28, 32, 64, 100, 104, 108, 112, len(data)-12]:
            damaged = bytearray(data)
            struct.pack_into('<I', damaged, offset, struct.unpack_from('<I', data, offset)[0] ^ 0xffffffff)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                extract_models(damaged)

    def test_external_resource_rejected(self):
        with self.assertRaisesRegex(ValueError, 'embedded buffer'):
            extract_models(fixture(external=True)[0])

    def test_glb_chunk_overflow_rejected(self):
        _, glb = fixture()
        damaged = bytearray(glb)
        struct.pack_into('<I', damaged, 12, 0xfffffffc)
        with self.assertRaisesRegex(ValueError, 'chunk bounds'):
            validate_glb(damaged)


if __name__ == '__main__':
    unittest.main()
