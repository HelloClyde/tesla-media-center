"""Explicit experimental runtime profile for the ordinary translated VDR.

No vehicle installation or recovery covariance is guessed. APK parameters are
read only from the pinned library. The optional neural backend remains absent.
"""
import copy
import json
from pathlib import Path
from inspect_vdr_model import inspect
from vdr_batch import number
from vdr_browser_batch import BrowserVdrBatch
from vdr_session import VdrSession, SessionConfiguration
from vdr_state_controller import StateConfiguration


def load_factory(profile_path):
    path = Path(profile_path).resolve()
    profile = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict) or profile.get('schema') != 'tmc-vdr-profile-v1':
        raise ValueError('Unsupported VDR profile schema')
    if profile.get('registry141') != 0 or type(profile.get('registry141')) is not int:
        raise ValueError('Only the verified registry141 constructor-default profile is supported')
    installation = profile.get('installation')
    variances = profile.get('recovery_variance')
    flags = profile.get('observation_flags')
    if not isinstance(installation, dict) or set(installation) != {
            'rotation', 'acceleration_sign', 'accuracy_to_sigma', 'maximum_gap'}:
        raise ValueError('Complete explicit installation profile required')
    if variances != 'native-constructor':
        if not isinstance(variances, dict) or set(variances) != {'gyro', 'acceleration'}:
            raise ValueError('Choose native-constructor or explicit recovery variances')
        if not all(number(value) and value > 0 for value in variances.values()):
            raise ValueError('Recovery variances must be finite and positive')
    if (not isinstance(flags, dict) or set(flags) != {'flag1', 'flag2'}
            or any(type(value) is not bool for value in flags.values())):
        raise ValueError('Explicit observation flags required')
    apk = profile.get('apk')
    if not isinstance(apk, str) or not apk:
        raise ValueError('Pinned APK path required')
    apk_path = Path(apk)
    if not apk_path.is_absolute():
        apk_path = path.parent / apk_path
    contract = inspect(apk_path)
    parameters = contract['linear_score']
    if variances == 'native-constructor':
        variances = contract['recovery_constructor_variance']
    configuration = SessionConfiguration(StateConfiguration(
        False, False, False, False, 60000, 10., False,
        variances['gyro'], variances['acceleration']),
        0, flags['flag1'], flags['flag2'], False, 0, 600)

    def factory():
        return BrowserVdrBatch(VdrSession(configuration, copy.deepcopy(parameters)),
                               **copy.deepcopy(installation))
    # Reject invalid rotation/sign/timing settings during configuration loading.
    factory()
    return factory
