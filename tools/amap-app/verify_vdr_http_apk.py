"""Run HTTP loss/recovery with linear coefficients extracted from the pinned APK.

The installation, state/observation settings and trajectory remain synthetic.
The optional neural quality model is not available in this verifier.
"""
import argparse
import unittest
import json
import tempfile
from pathlib import Path
from inspect_vdr_model import inspect
from test_vdr_http_pipeline import HttpPipelineTest
from vdr_runtime import load_factory


def verify(apk):
    contract = inspect(apk)  # Recheck the actual ELF digest, not a cached JSON.
    profile = dict(schema='tmc-vdr-profile-v1', apk=str(Path(apk).resolve()), registry141=0,
        installation=dict(rotation=[[1,0,0],[0,1,0],[0,0,1]], acceleration_sign=1,
                          accuracy_to_sigma=1, maximum_gap=80),
        recovery_variance='native-constructor',
        observation_flags=dict(flag1=False, flag2=False))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'synthetic-profile.json'
        path.write_text(json.dumps(profile), encoding='utf-8')
        runtime_factory = load_factory(path)
    states = runtime_factory().native.session.configuration.states
    assert states.gyro_bias_variance == contract['recovery_constructor_variance']['gyro']
    assert states.accel_bias_variance == contract['recovery_constructor_variance']['acceleration']
    class ApkParameterPipelineTest(HttpPipelineTest):
        @staticmethod
        def session_factory():
            return runtime_factory().native.session
    class ApkBrowserPipelineTest(ApkParameterPipelineTest):
        browser_input = True
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
        for case in (ApkParameterPipelineTest, ApkBrowserPipelineTest))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print('Verified library:', contract['library_sha256'])
    print('Linear model: actual APK; registry141: constructor default 0; recovery timeout: 60000 ms; attitude threshold: 10 degrees')
    print('Recovery variances: native constructor; installation/trajectory: synthetic; runtime overrides/neural backend: absent')
    return result.wasSuccessful()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.apk) else 1)
