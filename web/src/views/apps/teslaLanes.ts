import * as THREE from 'three';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';

/** Real LNDS XY boundaries. Z and paint semantics have not been decoded. */
export function createLaneMesh(lines: number[][][], origin: MapPoint, size = 600) {
  const positions: number[] = [], seen = new Set<string>();
  const half = size / 2, width = 0.09;
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      if (![...line[i - 1].slice(0, 2), ...line[i].slice(0, 2)].every(Number.isFinite)) continue;
      const a = groundOffset(line[i - 1], origin), b = groundOffset(line[i], origin);
      const dx = b[0] - a[0], dz = b[1] - a[1];
      // Clip crossing segments too, rather than dropping both outside endpoints.
      let lo = 0, hi = 1, outside = false;
      for (const [p, q] of [[-dx, a[0] + half], [dx, half - a[0]], [-dz, a[1] + half], [dz, half - a[1]]]) {
        if (p === 0) { if (q < 0) outside = true; continue; }
        const t = q / p;
        if (p < 0) lo = Math.max(lo, t); else hi = Math.min(hi, t);
      }
      if (outside || lo >= hi) continue;
      const x = a[0] + lo * dx, z = a[1] + lo * dz, xx = a[0] + hi * dx, zz = a[1] + hi * dz;
      const length = Math.hypot(xx - x, zz - z);
      if (length < 0.02) continue;
      const ends = [`${x.toFixed(2)},${z.toFixed(2)}`, `${xx.toFixed(2)},${zz.toFixed(2)}`].sort().join('/');
      if (seen.has(ends)) continue;
      seen.add(ends);
      const ox = -(zz - z) / length * width, oz = (xx - x) / length * width;
      const v = [[x + ox, .04, z + oz], [x - ox, .04, z - oz], [xx + ox, .04, zz + oz], [xx - ox, .04, zz - oz]];
      for (const index of [0, 1, 2, 2, 1, 3]) positions.push(...v[index]);
      if (seen.size >= 100000) break;
    }
    if (seen.size >= 100000) break;
  }
  if (!positions.length) return undefined;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  const material = new THREE.MeshBasicMaterial({ color: '#68807c', side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'AppLaneBoundaries';
  mesh.userData.segmentCount = seen.size;
  return mesh;
}
