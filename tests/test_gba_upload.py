import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from ffvideo.gba import add_gba_route


class UploadTest(unittest.TestCase):
    def test_upload_validation_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Flask(__name__);app.secret_key='test';add_gba_route(app)
            client=app.test_client()
            self.assertEqual(client.post('/api/gba/upload?name=test.gba',data=bytes(192)).json['status'],'need_login')
            with client.session_transaction() as session: session['last_visit']=1
            with patch('ffvideo.gba.get_gba_root_path',return_value=directory):
                self.assertEqual(client.post('/api/gba/upload?name=test.gba',data=bytes(192)).status_code,200)
                self.assertEqual(client.post('/api/gba/upload?name=test.gba',data=b'x'*192).status_code,409)
                self.assertEqual((Path(directory)/'test.gba').read_bytes(),bytes(192))
                for name in ['../bad.gba','bad.txt','nested/bad.gba']:
                    self.assertEqual(client.post('/api/gba/upload',query_string={'name':name},data=bytes(192)).status_code,400)
                self.assertEqual(client.post('/api/gba/upload?name=small.gba',data=b'x').status_code,413)
                self.assertEqual(client.post('/api/gba/upload?name=large.gba',data=bytes(32*1024*1024+1)).status_code,413)
