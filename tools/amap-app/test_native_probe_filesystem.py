import errno
import stat
import struct
import unittest
from native_probe_filesystem import ProbeFilesystem


class ProbeFilesystemTest(unittest.TestCase):
    def test_directory_metadata_and_real_file_roundtrip(self):
        fs = ProbeFilesystem()
        fs.mkdir('/pb_data', 0o750)
        metadata = fs.metadata('/pb_data')
        self.assertEqual(len(metadata), 128)
        self.assertEqual(struct.unpack_from('<I', metadata, 16)[0], stat.S_IFDIR | 0o750)
        fd = fs.open('/pb_data/state', 0x42, 0o600)
        fs.write(fd, b'abc')
        fs.seek(fd, 1, 0)
        fs.write(fd, b'Z')
        fs.seek(fd, 0, 0)
        self.assertEqual(fs.read(fd, 99), b'aZc')
        self.assertEqual(fs.read(fd, 1), b'')
        self.assertEqual(struct.unpack_from('<q', fs.metadata('/pb_data/state'), 48)[0], 3)
        fs.close(fd)
        with self.assertRaises(OSError) as error:
            fs.read(fd, 1)
        self.assertEqual(error.exception.errno, errno.EBADF)

    def test_no_host_files_and_no_missing_parent_creation(self):
        fs = ProbeFilesystem()
        for path in ('/etc/passwd', '/system/build.prop'):
            with self.assertRaises(OSError) as error:
                fs.open(path, 0, 0)
            self.assertEqual(error.exception.errno, errno.ENOENT)
        with self.assertRaises(OSError):
            fs.mkdir('/missing/child', 0o755)
        self.assertNotIn('/missing', fs.nodes)

    def test_append_truncate_and_permissions(self):
        fs = ProbeFilesystem()
        fd = fs.open('/state', 0x42, 0o600)
        fs.write(fd, b'one')
        fs.close(fd)
        fd = fs.open('/state', 0x401, 0)
        fs.write(fd, b'two')
        self.assertEqual(bytes(fs.nodes['/state'][1]), b'onetwo')
        fs.close(fd)
        fs.open('/state', 0x201, 0)
        self.assertEqual(len(fs.nodes['/state'][1]), 0)
        fs.close(fs.open('/readonly', 0x41, 0o400))
        with self.assertRaises(OSError) as error:
            fs.open('/readonly', 1, 0)
        self.assertEqual(error.exception.errno, errno.EACCES)


if __name__ == '__main__':
    unittest.main()
