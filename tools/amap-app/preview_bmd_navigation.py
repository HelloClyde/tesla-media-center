"""Offline Beijing fixture comparison; no online requests or webpage basemap.

Run after capturing the three documented BMD fixtures. This is an inspection
artifact, not a live map endpoint. Red is the separately decoded App route.
"""
import argparse
from html import escape
import json
import math
from pathlib import Path
from bmd_geometry import geographic_features
from route_v51 import decode


def build(assets, output):
    fixtures = [('bmd-type2-geographic-raw.bin', 13489, 4559),
                ('bmd-east-raw.bin', 13490, 4559), ('bmd-south-raw.bin', 13489, 4560)]
    features = []
    for file, x, y in fixtures:
        features.extend(geographic_features((assets / file).read_bytes(), (14, x, y))['features'])
    route = decode((assets / 'signed-version51.bin').read_bytes())[0]['path']
    points = [p for f in features for p in f['geometry']['coordinates']]
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    scale = 1080 / (east - west)
    vertical = scale / math.cos(math.radians((north + south) / 2))
    height = (north - south) * vertical + 100
    def pixel(p):
        return ((p[0] - west) * scale + 30, (north - p[1]) * vertical + 70)
    def line(points, color, width):
        xy = ' '.join(f'{x:.2f},{y:.2f}' for x, y in map(pixel, points))
        return f'<polyline points="{xy}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1140" height="{height:.0f}" viewBox="0 0 1140 {height:.0f}">',
           '<rect width="100%" height="100%" fill="#10242c"/>',
           '<text x="30" y="35" fill="#ecf4f5" font-family="sans-serif" font-size="21">App BMD 道路与名称 · 红线为 App 导航路线 · 离线验证预览</text>']
    for f in features:
        svg.append(line(f['geometry']['coordinates'], '#628a93', 1.2))
    svg.append(line(route, '#ff6b59', 4))
    used, cells = set(), set()
    for f in features:
        name = f['properties']['name']
        if not name or name in used:
            continue
        points = f['geometry']['coordinates']
        x, y = pixel(points[len(points) // 2])
        cell = (int(x / 100), int(y / 35))
        if cell in cells:
            continue
        used.add(name)
        cells.add(cell)
        svg.append(f'<text x="{x:.2f}" y="{y:.2f}" fill="#f2f7f8" stroke="#10242c" stroke-width="3" paint-order="stroke" font-family="sans-serif" font-size="12">{escape(name)}</text>')
    svg.append('</svg>')
    output.write_text('\n'.join(svg), encoding='utf-8')
    print(json.dumps({'lines': len(features), 'namedLines': sum(bool(f['properties']['name']) for f in features),
                      'previewLabels': len(used), 'routePoints': len(route), 'liveMap': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=Path('.local-data/amap-app'))
    parser.add_argument('--output', type=Path, default=Path('.local-data/amap-app/bmd-navigation-preview.svg'))
    args = parser.parse_args()
    build(args.assets, args.output)
