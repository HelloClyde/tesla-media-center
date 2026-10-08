import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from ffvideo import tesla_skins


def png_image(size=512, color=b'\xff\xff\xff\xff'):
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    pixels = (b'\x00' + color * size) * size
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


class TeslaSkinsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.storage = patch.object(tesla_skins, 'skin_root', return_value=self.root)
        self.storage.start()
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        tesla_skins.add_tesla_skin_routes(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['last_visit'] = 1

    def tearDown(self):
        self.storage.stop()
        self.folder.cleanup()

    def test_upload_read_replace_and_delete_across_clients(self):
        url = '/api/tesla/skins/modely-high'
        self.assertEqual(self.client.get(url).status_code, 404)
        first = png_image(color=b'\xaa\xbb\xcc\xff')
        self.assertEqual(self.client.put(url, data=first, content_type='image/png').status_code, 200)
        other = self.app.test_client()
        with other.session_transaction() as session:
            session['last_visit'] = 1
        loaded = other.get(url)
        self.assertEqual(loaded.data, first)
        self.assertEqual(loaded.mimetype, 'image/png')
        self.assertEqual(loaded.headers['Cache-Control'], 'no-store')
        loaded.close()
        second = png_image(color=b'\x11\x22\x33\xff')
        self.assertEqual(other.put(url, data=second, content_type='image/png', headers={'If-None-Match': '*'}).status_code, 412)
        loaded = self.client.get(url)
        self.assertEqual(loaded.data, first)
        loaded.close()
        self.assertEqual(other.put(url, data=second, content_type='image/png').status_code, 200)
        loaded = self.client.get(url)
        self.assertEqual(loaded.data, second)
        loaded.close()
        self.assertEqual(other.delete(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_unsupported_model_and_invalid_images(self):
        self.assertEqual(self.client.put('/api/tesla/skins/not-a-model', data=png_image()).status_code, 400)
        url = '/api/tesla/skins/modely-high'
        self.assertEqual(self.client.put(url, data=b'not an image').status_code, 400)
        self.assertEqual(self.client.put(url, data=png_image(256)).status_code, 400)
        self.assertFalse(list(self.root.iterdir()))

    def test_requires_login_for_reads_and_writes(self):
        guest = self.app.test_client()
        for response in [guest.get('/api/tesla/skins/modely-high'),
                         guest.put('/api/tesla/skins/modely-high', data=png_image()),
                         guest.delete('/api/tesla/skins/modely-high')]:
            self.assertEqual(response.json['status'], 'need_login')
        self.assertFalse(list(self.root.iterdir()))


if __name__ == '__main__':
    unittest.main()
