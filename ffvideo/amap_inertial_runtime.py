"""Install a server-admin supplied experimental profile; no implicit activation."""
import os
import sys
from pathlib import Path


def configure_inertial_runtime(app):
    if callable(app.config.get('AMAP_VDR_FACTORY')):
        return
    profile = app.config.get('AMAP_VDR_PROFILE') or os.environ.get('TMC_AMAP_VDR_PROFILE')
    if not profile:
        app.config['AMAP_VDR_UNAVAILABLE_REASON'] = 'profile_missing'
        return
    try:
        directory = str(Path(__file__).resolve().parents[1] / 'tools' / 'amap-app')
        if directory not in sys.path:
            sys.path.insert(0, directory)
        from vdr_runtime import load_factory
        app.config['AMAP_VDR_FACTORY'] = load_factory(profile)
        app.config.pop('AMAP_VDR_UNAVAILABLE_REASON', None)
    except Exception:
        app.config['AMAP_VDR_UNAVAILABLE_REASON'] = 'profile_invalid'
        app.logger.exception('Unable to initialize experimental Amap VDR profile')
