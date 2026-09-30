"""Offline, allowlisted evidence inventory; does not claim a working navigation engine."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

IDENTIFIERS = (
    'EnforceTunnelDR', 'TunnelMatching', 'MgcVdrHandler',
    'tunnel_main_route_weight', 'tunnel_rpe_offroute_conf',
    'tunnel_alg_file/tunnel_finger_file', 'nativeSetSignInfo',
    'nativeSendSensor', 'nativeInit', 'setupLocationKitPointer',
    'onRequestSensor', 'onMatchLocationChanged', 'onGnssLoss',
)


def inspect(apk):
    result = {'runtime_verified': False, 'tmc_integrated': False, 'libraries': []}
    with zipfile.ZipFile(apk) as archive:
        for name in ('libamaploc.so', 'liblocation_kit.so', 'libloc_base.so'):
            data = archive.read('lib/arm64-v8a/' + name)
            result['libraries'].append({
                'name': name, 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest(),
                'identifiers': [value for value in IDENTIFIERS if value.encode() in data],
            })
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.apk), ensure_ascii=False, indent=2))
