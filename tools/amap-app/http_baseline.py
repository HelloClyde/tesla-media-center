"""Small, unsigned HTTP baseline for two statically observed Amap routes.
No login, extracted credential, signature guessing, or automatic retry.
Raw responses stay in ignored local output directory.
"""
import hashlib
import argparse
import json
from pathlib import Path
import time
import requests

ENDPOINTS = [
    ('legacy', 'https://m5.amap.com/ws/mapapi/navigation/auto/'),
    ('transfer', 'https://m5.amap.com/ws/transfer/navigation/auto/'),
]
PARAMS = dict(fromX='116.3975', fromY='39.9087', toX='116.4100', toY='39.9160',
              policy2='0', output='bin', route_version='2.5.3', invoker='plan')


def run(output, defaults=False):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    params = dict(PARAMS)
    if defaults:
        params.update(off=0, carplate='', cc='', usepoiquery='true', angle='-1',
                      threeD=1, v_type=0, v_height=0.0, v_load=0.0, v_weight=0.0,
                      v_width=0.0, v_length=0.0, v_size='0', v_axis='0', refresh=0,
                      playstyle='0', soundtype='9', end_poi_extension='0',
                      contentoptions=0, sloc_speed=0.0, use_truck_engine=0)
    for label, url in ENDPOINTS:
        meta = dict(label=label, url=url, params=params, signed=False,
                    constructor_defaults=defaults)
        try:
            response = requests.get(url, params=params, timeout=(10, 25),
                                    allow_redirects=False,
                                    headers={'User-Agent': 'TMC-local-protocol-research/0.1'})
            body = response.content
            (output / (label + '.bin')).write_bytes(body)
            meta.update(status=response.status_code, size=len(body),
                        content_type=response.headers.get('Content-Type', ''),
                        sha256=hashlib.sha256(body).hexdigest())
            try:
                obj = response.json()
                if isinstance(obj, dict):
                    meta['json_keys'] = list(obj)[:30]
                    meta['business_result'] = {k: obj[k] for k in ('code','status','infocode','message','msg','info','result')
                                               if k in obj and isinstance(obj[k], (str,int,bool,type(None)))}
            except ValueError:
                pass
            if len(body) >= 10 and 'json' not in meta['content_type']:
                meta['candidate_le16'] = int.from_bytes(body[:2], 'little')
        except requests.RequestException as error:
            meta['error_type'] = type(error).__name__
        results.append(meta)
        print(json.dumps(meta, ensure_ascii=False), flush=True)
        time.sleep(1)
    (output / 'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--defaults', action='store_true')
    args = parser.parse_args()
    suffix = '-defaults' if args.defaults else ''
    run(Path('.local-data/amap-app/http-baseline-20260927' + suffix), args.defaults)
