import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from ffvideo.gam4980 import add_gam4980_route


class SavesTest(unittest.TestCase):
    def test_authenticated_roundtrip_restart_validation_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as temp, patch('ffvideo.gam4980.DEFAULT_SAVE_ROOT', Path(temp)):
            app = Flask(__name__)
            app.secret_key = 'test'
            add_gam4980_route(app)
            client = app.test_client()
            url = '/api/gam4980/saves/100-123-456'
            self.assertEqual(client.put(url, data=bytes(0x14000)).json['status'], 'need_login')
            with client.session_transaction() as session:
                session['last_visit'] = 1
            self.assertEqual(client.get(url).status_code, 404)
            self.assertEqual(client.put(url, data=b'a' * 0x14000).status_code, 200)
            with client.get(url) as response:
                self.assertEqual(response.data, b'a' * 0x14000)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(client.put(url, data=b'bad').status_code, 413)
            self.assertEqual(client.put('/api/gam4980/saves/invalid', data=bytes(0x14000)).status_code, 400)
            with patch('ffvideo.gam4980.os.replace', side_effect=OSError('disk full')):
                self.assertEqual(client.put(url, data=b'b' * 0x14000).status_code, 500)
            second = Flask('restarted')
            second.secret_key = 'test'
            add_gam4980_route(second)
            other = second.test_client()
            with other.session_transaction() as session:
                session['last_visit'] = 1
            with other.get(url) as response:
                self.assertEqual(response.data, b'a' * 0x14000)
            self.assertEqual(len(list(Path(temp).iterdir())), 1)
