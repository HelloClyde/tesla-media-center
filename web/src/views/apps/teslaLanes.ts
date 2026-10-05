import * as THREE from 'three';
import { cumulative, type AppRoute } from './amapNavigation';
import { groundBounds, groundOffset, type MapPoint } from './teslaMapCoordinates';

const routeLengths = new WeakMap<AppRoute, { path: AppRoute['path']; values: number[] }>();

/** A visual inference from adjacent LNDS boundaries, not an APK paint enum.
 * A divider with another parallel boundary on both sides is an interior lane
 * divider. Outer edges and ambiguous junctions remain continuous. */
export function inferredLaneMarkings(lines: number[][][], origin: MapPoint,
  deckHeight?: (x:number,z:number,direction:readonly [number,number])=>number,
  kinds?: number[]): ('solid' | 'dashed')[] {
  type Segment = { x:number; z:number; dx:number; dz:number; length:number; height:number; line:number };
  const cellSize=12, cells=new Map<string,Segment[]>(), segments:Segment[][]=[];
  const key=(x:number,z:number)=>`${Math.floor(x/cellSize)}/${Math.floor(z/cellSize)}`;
  lines.forEach((line,index)=>{
    const owned:Segment[]=[];
    for(let i=1;i<line.length;i++) {
      const a=groundOffset(line[i-1],origin),b=groundOffset(line[i],origin);
      const dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz);
      if(!Number.isFinite(length) || length<2 || length>1000) continue;
      const x=(a[0]+b[0])/2,z=(a[1]+b[1])/2;
      const segment={x,z,dx,dz,length,height:deckHeight?.(x,z,[dx,dz])||0,line:index};
      owned.push(segment);
      const radius=Math.min(30,Math.max(6,length/2+6));
      for(let x=Math.floor((segment.x-radius)/cellSize);x<=Math.floor((segment.x+radius)/cellSize);x++)
        for(let z=Math.floor((segment.z-radius)/cellSize);z<=Math.floor((segment.z+radius)/cellSize);z++) {
          const id=key(x*cellSize,z*cellSize), entries=cells.get(id)||[];
          entries.push(segment);cells.set(id,entries);
        }
    }
    segments.push(owned);
  });
  return segments.map((owned,index)=>{
    if(kinds && kinds[index]!==3) return 'solid';
    for(const segment of owned) {
      let left=false,right=false;
      for(const other of cells.get(key(segment.x,segment.z))||[]) {
        if(other.line===index || Math.abs(segment.height-other.height)>1.5 ||
            Math.abs((segment.dx*other.dx+segment.dz*other.dz)/
            (segment.length*other.length))<.92) continue;
        const cross=(segment.dx*(other.z-segment.z)-segment.dz*(other.x-segment.x))/segment.length;
        if(Math.abs(cross)<1.6 || Math.abs(cross)>5.5) continue;
        const along=(segment.dx*(other.x-segment.x)+segment.dz*(other.z-segment.z))/segment.length;
        if(Math.abs(along)>(segment.length+other.length)/2) continue;
        if(cross>0) left=true;else right=true;
        if(left&&right) return 'dashed';
      }
    }
    return 'solid';
  });
}

/** LNDS contains every road in the tile. Keep only boundaries following the
 * driven route near the car until the APK's per-boundary style is understood. */
export function navigationLaneBoundaries(lines: number[][][], route: AppRoute, progress: number,
  origin: MapPoint, kinds?: number[], selectedKinds?: number[]): number[][][] {
  if (!Number.isFinite(progress) || route.path.length < 2) return [];
  let cached = routeLengths.get(route);
  if (!cached || cached.path !== route.path) {
    cached = { path: route.path, values: cumulative(route) };
    routeLengths.set(route, cached);
  }
  const lengths = cached.values, start = Math.max(0, progress - 30), end = progress + 320;
  const cellSize = 30, radius = 14, grid = new Map<string, {a:MapPoint;b:MapPoint;length:number}[]>();
  const key = (x:number,z:number) => `${Math.floor(x/cellSize)}/${Math.floor(z/cellSize)}`;
  const breaks = new Set(route.breaks);
  let low = 1, high = lengths.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (lengths[mid] < start) low = mid + 1; else high = mid;
  }
  for (let i = low; i < lengths.length && lengths[i - 1] <= end; i++) {
    if (breaks.has(i) || lengths[i] <= lengths[i - 1]) continue;
    const first = groundOffset(route.path[i - 1], origin), last = groundOffset(route.path[i], origin);
    const from = Math.max(0, (start - lengths[i - 1]) / (lengths[i] - lengths[i - 1]));
    const to = Math.min(1, (end - lengths[i - 1]) / (lengths[i] - lengths[i - 1]));
    if (from >= to) continue;
    const a:MapPoint = [first[0] + (last[0] - first[0]) * from, first[1] + (last[1] - first[1]) * from];
    const b:MapPoint = [first[0] + (last[0] - first[0]) * to, first[1] + (last[1] - first[1]) * to];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length < .1) continue;
    const segment = {a,b,length};
    for (let x = Math.floor((Math.min(a[0],b[0])-radius)/cellSize); x <= Math.floor((Math.max(a[0],b[0])+radius)/cellSize); x++)
      for (let z = Math.floor((Math.min(a[1],b[1])-radius)/cellSize); z <= Math.floor((Math.max(a[1],b[1])+radius)/cellSize); z++) {
        const cell = key(x*cellSize,z*cellSize), entries = grid.get(cell) || [];
        entries.push(segment); grid.set(cell,entries);
      }
  }
  const selected: number[][][] = [], selectedSources:number[]=[];
  for (const [lineIndex,line] of lines.entries()) for (let i = 1; i < line.length; i++) {
    const a = groundOffset(line[i - 1],origin), b = groundOffset(line[i],origin);
    const dx = b[0] - a[0], dz = b[1] - a[1], span = Math.hypot(dx,dz);
    if (!Number.isFinite(span) || span < .5 || span > 1000) continue;
    const pieces = Math.ceil(span / 20);
    for (let part = 0; part < pieces; part++) {
      const from = part / pieces, to = (part + 1) / pieces;
      const x = a[0] + dx * (from + to) / 2, z = a[1] + dz * (from + to) / 2;
      for (const segment of grid.get(key(x,z)) || []) {
        const rx = segment.b[0] - segment.a[0], rz = segment.b[1] - segment.a[1];
        if (Math.abs((dx*rx + dz*rz) / (span*segment.length)) < .78) continue;
        const t = Math.max(0,Math.min(1,((x-segment.a[0])*rx+(z-segment.a[1])*rz)/(segment.length**2)));
        if (Math.hypot(x-segment.a[0]-t*rx,z-segment.a[1]-t*rz) > radius) continue;
        const point = (fraction:number) => [line[i-1][0] + (line[i][0] - line[i-1][0]) * fraction,
          line[i-1][1] + (line[i][1] - line[i-1][1]) * fraction];
        selected.push([point(from),point(to)]);
        selectedSources.push(lineIndex);
        break;
      }
    }
  }
  // Keep adjoining samples from one LNDS boundary together. They are sampled
  // in source order, so a bridge level resolved before an XY overlap can be
  // carried along that same line without leaking onto a neighbouring line.
  const joined:number[][][]=[];
  let previousSource=-1;
  for(let i=0;i<selected.length;i++) {
    const [a,b]=selected[i], last=joined[joined.length-1];
    if(previousSource===selectedSources[i] && last &&
        Math.hypot(last[last.length-1][0]-a[0],last[last.length-1][1]-a[1])<1e-9) last.push(b);
    else {joined.push([a,b]);selectedKinds?.push(kinds?.[selectedSources[i]] ?? 0);}
    previousSource=selectedSources[i];
  }
  return joined;
}

/** Geographic LNDS tiles covering the visible ground patch, nearest first. */
export function laneViewportTiles(point: MapPoint, size = 600): [number, number][] {
  const [west, north, east, south] = groundBounds(point, size / 2);
  const n = 2 ** 15;
  const x = (value: number) => Math.max(0, Math.min(n - 1, Math.floor((value + 180) / 360 * n)));
  const y = (value: number) => Math.max(0, Math.min(n - 1, Math.floor((90 - value) / 180 * n)));
  const tiles: [number, number][] = [];
  for (let xx = x(west); xx <= x(east); xx++) {
    for (let yy = y(north); yy <= y(south); yy++) tiles.push([xx, yy]);
  }
  const cx = x(point[0]), cy = y(point[1]);
  return tiles.sort((a, b) => (a[0] - cx) ** 2 + (a[1] - cy) ** 2 -
    (b[0] - cx) ** 2 - (b[1] - cy) ** 2).slice(0, 16);
}

/** Real LNDS XY boundaries. Z and paint semantics have not been decoded. */
export function createLaneMesh(lines: number[][][], origin: MapPoint, size = 600,
  deckHeight?: (x: number, z: number, direction: readonly [number, number], preferredHeight?:number) => number,
  kinds?: number[]) {
  const positions: number[] = [], seen = new Set<string>();
  const half = size / 2, width = 0.09;
  const markingStyles=inferredLaneMarkings(lines,origin,deckHeight,kinds);
  for (const [lineIndex,line] of lines.entries()) {
    let previousHeight:number|undefined;
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
      const direction: readonly [number, number] = [dx, dz];
      // Long source edges can cross a deck boundary between their endpoints.
      // Sample the already-clipped edge locally without altering its XY line.
      const pieces = Math.ceil(length / 5);
      for (let piece = 0; piece < pieces; piece++) {
        const start = piece / pieces, end = (piece + 1) / pieces;
        const sx = x + (xx - x) * start, sz = z + (zz - z) * start;
        const ex = x + (xx - x) * end, ez = z + (zz - z) * end;
        const startHeight = deckHeight?.(sx, sz, direction, previousHeight) || 0;
        const endHeight = deckHeight?.(ex, ez, direction, startHeight) || 0;
        previousHeight=endHeight;
        // Keep short junction fragments visible as continuous lines.
        const dashed=markingStyles[lineIndex]==='dashed' && length>=10;
        const drawEnd=dashed ? .48 : 1;
        const drawX=sx+(ex-sx)*drawEnd, drawZ=sz+(ez-sz)*drawEnd;
        const sy = (Number.isFinite(startHeight) ? Math.max(0, startHeight) : 0) + .04;
        const ey = (Number.isFinite(endHeight) ? Math.max(0, endHeight) : 0) + .04;
        const drawY=sy+(ey-sy)*drawEnd;
        const v = [[sx + ox, sy, sz + oz], [sx - ox, sy, sz - oz], [drawX + ox, drawY, drawZ + oz], [drawX - ox, drawY, drawZ - oz]];
        for (const index of [0, 1, 2, 2, 1, 3]) positions.push(...v[index]);
      }
      if (seen.size >= 100000) break;
    }
    if (seen.size >= 100000) break;
  }
  if (!positions.length) return undefined;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  const material = new THREE.MeshBasicMaterial({ color: '#f8fbfa', transparent: true, opacity: .72,
    depthWrite: false, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'AppLaneBoundaries';
  mesh.userData.segmentCount = seen.size;
  return mesh;
}
