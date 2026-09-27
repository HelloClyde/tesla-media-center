"""Bounded diagnostic downloader for the App's LNDS rendering tiles.

This is distinct from qc/hd/lnds. Payloads are retained verbatim, not claimed
to be decoded lane geometry. Only two tiles are requested per invocation.
"""
import hashlib
import json
from pathlib import Path

from bmd_tile import catalog, geographic_grid, tile_id, unpack, LIMIT
from route_v51 import fields, one

HOSTS = frozenset({
    'https://render-prod-lnds.amap.com',
    'https://render-prod-backup-lnds.amap.com',
})
LEVELS = {22: 15, 23: 14}


def version_catalog(raw):
    message = fields(raw)
    host = one(message, 5)
    if not isinstance(host, bytes) or host.decode('ascii') not in HOSTS:
        raise ValueError('unsupported LNDS host')
    versions = catalog(raw)
    if any(type(versions.get(kind)) is not int or not 0 < versions[kind] < 2**32
           for kind in LEVELS):
        raise ValueError('missing LNDS versions')
    return host.decode('ascii'), {kind: versions[kind] for kind in LEVELS}


def inspect_response(raw, identity, kind):
    if kind not in LEVELS or len(raw) > LIMIT:
        raise ValueError('invalid LNDS response')
    payload = unpack(raw, identity, kind)
    # Both verified live payloads repeat their tile identity inside the transport.
    message = fields(payload) if payload else {}
    if payload and one(message, 1) != identity:
        raise ValueError('LNDS inner identity mismatch')
    report = {
        'tileId': str(identity), 'tileType': kind,
        'responseBytes': len(raw), 'payloadBytes': len(payload),
        'payloadSha256': hashlib.sha256(payload).hexdigest(),
        'fieldCounts': {str(key): len(values) for key, values in message.items()},
        'geometryDecoded': False,
    }
    if kind == 22 and payload:
        from lane_render_blocks import decode_render_blocks
        blocks = decode_render_blocks(payload, identity)['blocks']
        report['blocks'] = [{key: value for key, value in block.items() if key != 'data'}
                            | {'bytes': len(block['data'])} for block in blocks]
    return payload, report


def capture(longitude, latitude, output):
    from tmc_map_helper import download
    from tmc_route_helper import check_assets, ASSETS
    from native_signer import load_material

    # Validate coordinates before loading native assets or doing network I/O.
    grids = {kind: geographic_grid(longitude, latitude, level)
             for kind, level in LEVELS.items()}
    check_assets()
    material = load_material(ASSETS)
    channel = material['getAosChannel']
    sign = hashlib.md5((channel + '@' + material['getAosKey']).encode()).hexdigest().upper()
    raw = download('https://m5.amap.com/ws/render/lnds/version/',
                   dict(channel=channel, diu='', sign=sign, output='bin'))
    host, versions = version_catalog(raw)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'version.bin').write_bytes(raw)
    report = {'host': host, 'tiles': [], 'geometryDecoded': False}
    for kind, grid in grids.items():
        identity = tile_id(*grid)
        response = download(host + '/ws/render/lnds/tile',
                            dict(version=versions[kind], tileType=kind,
                                 tileId=identity, i18nVer=0, ct=1))
        payload, item = inspect_response(response, identity, kind)
        (output / f'{kind}-response.bin').write_bytes(response)
        (output / f'{kind}-payload.bin').write_bytes(payload)
        if kind == 22 and payload:
            from lane_render_blocks import decode_render_blocks
            for block in decode_render_blocks(payload, identity)['blocks']:
                (output / f"22-block-{block['id']}.bin").write_bytes(block['data'])
        item.update(grid=grid, version=versions[kind])
        report['tiles'].append(item)
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--longitude', type=float, required=True)
    parser.add_argument('--latitude', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(capture(args.longitude, args.latitude, args.output), indent=2))
    except Exception as error:
        # Requests exceptions can contain signed URLs. Do not print those URLs.
        print(json.dumps({'error': type(error).__name__, 'geometryDecoded': False}))
        raise SystemExit(1)
