/** Compare decoded LNDS lines with App BMD road geometry in the same area.
 *
 * Diagnostic only: nearest road is not a lane-label ground truth. A small
 * unmodified distance in two cities can nevertheless reject an unnecessary
 * coordinate conversion in the TMC overlay.
 */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

const [lanePath, mapPath, longitude, latitude] = process.argv.slice(2);
const origin = [Number(longitude), Number(latitude)];
if (!lanePath || !mapPath || !origin.every(Number.isFinite)) {
  throw new Error('usage: node lane_alignment.cjs LANES_JSON BMD_MAP_JSON LNG LAT');
}
const { wgs84togcj02, gcj02towgs84 } = createRequire(
  path.resolve(__dirname, '../../web/package.json'))('coordtransform');
const lane = JSON.parse(fs.readFileSync(lanePath, 'utf8'));
const map = JSON.parse(fs.readFileSync(mapPath, 'utf8'));
if (!Array.isArray(lane.lines) || !Array.isArray(map.tiles)) {
  throw new Error('expected decoded LNDS lines and BMD map tiles');
}

const metres = 111319.49079327358;
const scale = [metres * Math.cos(origin[1] * Math.PI / 180), metres];
const xy = p => [(p[0] - origin[0]) * scale[0], (p[1] - origin[1]) * scale[1]];
const segments = [];
for (const tile of map.tiles) {
  if (tile.error || tile.missingLayers?.includes('collection')) {
    throw new Error('BMD road tile is incomplete');
  }
  for (const feature of tile.collection?.features || []) {
    if (feature.geometry?.type !== 'LineString') continue;
    const points = feature.geometry.coordinates;
    for (let i = 1; i < points.length; i++) segments.push([xy(points[i - 1]), xy(points[i])]);
  }
}
if (!segments.length) throw new Error('no BMD road segments');

const cell = 50;
const key = (x, y) => `${x}/${y}`;
const grid = new Map();
for (let index = 0; index < segments.length; index++) {
  const [[ax, ay], [bx, by]] = segments[index];
  for (let x = Math.floor(Math.min(ax, bx) / cell); x <= Math.floor(Math.max(ax, bx) / cell); x++) {
    for (let y = Math.floor(Math.min(ay, by) / cell); y <= Math.floor(Math.max(ay, by) / cell); y++) {
      const id = key(x, y);
      if (!grid.has(id)) grid.set(id, []);
      grid.get(id).push(index);
    }
  }
}

function distance(point) {
  const [x, y] = xy(point);
  const col = Math.floor(x / cell), row = Math.floor(y / cell);
  const candidates = new Set();
  for (let dx = -3; dx <= 3; dx++) {
    for (let dy = -3; dy <= 3; dy++) {
      for (const index of grid.get(key(col + dx, row + dy)) || []) candidates.add(index);
    }
  }
  let nearest = Infinity;
  for (const index of candidates) {
    const [[ax, ay], [bx, by]] = segments[index];
    const dx = bx - ax, dy = by - ay;
    const fraction = Math.max(0, Math.min(1,
      ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)));
    nearest = Math.min(nearest, Math.hypot(x - ax - fraction * dx, y - ay - fraction * dy));
  }
  return nearest;
}

const allPoints = lane.lines.flat();
const stride = Math.max(1, Math.floor(allPoints.length / 1800));
const sample = allPoints.filter((_, index) => index % stride === 0);
const comparison = {};
for (const [name, transform] of Object.entries({
  raw: p => p,
  wgsToGcj: p => wgs84togcj02(p[0], p[1]),
  gcjToWgs: p => gcj02towgs84(p[0], p[1]),
})) {
  const distances = sample.map(transform).map(distance).filter(Number.isFinite).sort((a, b) => a - b);
  const percentile = q => distances.length ? Number(distances[Math.floor((distances.length - 1) * q)].toFixed(2)) : null;
  comparison[name] = {
    coveredWithin150m: distances.length,
    medianMetres: percentile(0.5),
    p90Metres: percentile(0.9),
    within15m: distances.filter(value => value <= 15).length,
  };
}
console.log(JSON.stringify({ samples: sample.length, roadSegments: segments.length, comparison }));
