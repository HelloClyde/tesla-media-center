import unittest
from inspect_spx import rc4, lz4_block, inspect_spx

class SpxTests(unittest.TestCase):
    def test_rc4_vector(self):
        self.assertEqual(rc4(b'Key', b'Plaintext').hex(), 'bbf316e8d940af0ad3')
    def test_literals(self):
        self.assertEqual(lz4_block(b'\x30abc', 3), b'abc')
    def test_overlap(self):
        self.assertEqual(lz4_block(b'\x10a\x01\x00', 5), b'aaaaa')
    def test_invalid_blocks(self):
        for data, size in [(b'\xf0', 2), (b'\x30a', 3), (b'\x00\x00\x00',4),
                           (b'\x10a\x02\x00',5), (b'\x30abc',2), (b'\x00',1)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                lz4_block(data,size)
    def test_bad_header(self):
        with self.assertRaises(ValueError): inspect_spx(b'spx\n003\0')

if __name__ == '__main__': unittest.main()
