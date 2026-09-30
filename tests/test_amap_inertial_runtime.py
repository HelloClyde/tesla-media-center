import os
import unittest
from unittest.mock import patch
from flask import Flask
from ffvideo.amap_inertial_runtime import configure_inertial_runtime


class RuntimeConfigurationTest(unittest.TestCase):
    def test_missing_profile_stays_disabled(self):
        app = Flask(__name__)
        with patch.dict(os.environ, {}, clear=True):
            configure_inertial_runtime(app)
        self.assertNotIn('AMAP_VDR_FACTORY', app.config)
        self.assertEqual(app.config['AMAP_VDR_UNAVAILABLE_REASON'], 'profile_missing')

    def test_bad_profile_does_not_crash_application(self):
        app = Flask(__name__)
        app.config['AMAP_VDR_PROFILE'] = 'nonexistent-vdr-profile.json'
        with self.assertLogs(app.logger, level='ERROR'):
            configure_inertial_runtime(app)
        self.assertNotIn('AMAP_VDR_FACTORY', app.config)
        self.assertEqual(app.config['AMAP_VDR_UNAVAILABLE_REASON'], 'profile_invalid')

    def test_explicit_factory_is_preserved(self):
        app = Flask(__name__)
        factory = lambda: None
        app.config['AMAP_VDR_FACTORY'] = factory
        configure_inertial_runtime(app)
        self.assertIs(app.config['AMAP_VDR_FACTORY'], factory)


if __name__ == '__main__':
    unittest.main()
