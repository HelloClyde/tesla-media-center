import struct
import unittest
from extract_spx_file import extract
from inspect_spx import elf_hash, rc4

class ExtractTests(unittest.TestCase):
    def fixture(self):
        b=bytearray(1100)
        b[:8]=b'spx\n003\0'
        struct.pack_into('<6I',b,448,480,480,4,484,0,0)
        key=struct.pack('<4I',elf_hash(b[:8]),elf_hash(b[8:29]),484,480)
        b[484:488]=rc4(key,b'\x30abc')
        bundles=[dict(offset=0,size=600),dict(offset=600,size=500)]
        fields=[0,0,4,3,484,0,0,0,0]
        return b,bundles,fields
    def test_local_and_shared(self):
        b,bs,f=self.fixture()
        self.assertEqual(extract(b,bs,0,f),b'abc')
        f[4]=(484-600)&0xffffffff
        self.assertEqual(extract(b,bs,1,f),b'abc')
    def test_bounds(self):
        for offset in (0,599,1100,0xffffffff):
            b,bs,f=self.fixture();f[4]=offset
            with self.subTest(offset=offset), self.assertRaises(ValueError):extract(b,bs,0,f)

if __name__=='__main__':unittest.main()
