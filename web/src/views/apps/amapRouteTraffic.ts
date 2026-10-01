import { cumulative, type AppRoute, type Point } from './amapNavigation';
import type { TrafficRoad } from './amapTrafficOverlay';

export type CongestionRun = { status: 2 | 3; path: Point[]; start: number; end: number };
type Segment = { ax: number; ay: number; bx: number; by: number; dx: number; dy: number; length2: number;
  status: 2 | 3; name: string; angle?: number };

const CELL = 40;
const MATCH_METERS = 16;
const cellKey = (x: number, y: number) => `${Math.floor(x / CELL)},${Math.floor(y / CELL)}`;
const normalizedName = (value?: string) => (value || '').replace(/[\s·（）()]/g, '');

/** Color only the route portions supported by nearby, direction-compatible live traffic. */
export function routeCongestionRuns(route: AppRoute, roads: TrafficRoad[]): CongestionRun[] {
  if (!route.path.length || !roads[0]?.path?.length) return [];
  const [lng0, lat0] = roads[0].path[0];
  const metersX = 111319.49 * Math.cos(lat0 * Math.PI / 180), metersY = 111319.49;
  const xy = (point: Point) => [(point[0] - lng0) * metersX, (point[1] - lat0) * metersY] as const;
  const grid = new Map<string, Segment[]>();
  for (const road of roads) {
    if (road.status !== 2 && road.status !== 3) continue;
    for (let i = 1; i < road.path.length; i++) {
      const [ax, ay] = xy(road.path[i - 1]), [bx, by] = xy(road.path[i]);
      const dx = bx - ax, dy = by - ay, length2 = dx * dx + dy * dy;
      if (length2 < 1 || length2 > 1000 * 1000) continue;
      const segment: Segment = { ax, ay, bx, by, dx, dy, length2, status: road.status,
        name: normalizedName(road.name), angle: road.angle };
      const minX = Math.floor((Math.min(ax, bx) - MATCH_METERS) / CELL);
      const maxX = Math.floor((Math.max(ax, bx) + MATCH_METERS) / CELL);
      const minY = Math.floor((Math.min(ay, by) - MATCH_METERS) / CELL);
      const maxY = Math.floor((Math.max(ay, by) + MATCH_METERS) / CELL);
      for (let gx = minX; gx <= maxX; gx++) for (let gy = minY; gy <= maxY; gy++) {
        const key = `${gx},${gy}`, bucket = grid.get(key) || [];
        bucket.push(segment); grid.set(key, bucket);
      }
    }
  }
  const roadNames: string[] = Array(route.path.length).fill('');
  for (const step of route.steps) for (let i = step.start + 1; i <= step.end; i++) roadNames[i] = normalizedName(step.road);
  const lengths = cumulative(route), breaks = new Set(route.breaks);
  const runs: CongestionRun[] = [];
  let current: CongestionRun | undefined;
  const flush = () => { if (current) runs.push(current); current = undefined; };
  for (let i = 1; i < route.path.length; i++) {
    if (breaks.has(i)) { flush(); continue; }
    const a = route.path[i - 1], b = route.path[i];
    const [ax, ay] = xy(a), [bx, by] = xy(b);
    const dx = bx - ax, dy = by - ay, length = Math.hypot(dx, dy);
    if (length < .1) continue;
    const pieces = Math.min(1000, Math.max(1, Math.ceil(length / 20)));
    const routeName = roadNames[i];
    for (let piece = 0; piece < pieces; piece++) {
      const from = piece / pieces, to = (piece + 1) / pieces, middle = (from + to) / 2;
      const x = ax + dx * middle, y = ay + dy * middle;
      let best: Segment | undefined, bestDistance = MATCH_METERS * MATCH_METERS;
      for (const segment of grid.get(cellKey(x, y)) || []) {
        if (routeName && segment.name && routeName !== '无名道路' &&
            !routeName.includes(segment.name) && !segment.name.includes(routeName)) continue;
        const alignment = segment.angle === undefined
          ? Math.abs((dx * segment.dx + dy * segment.dy) / Math.sqrt(length * length * segment.length2))
          : (dx * Math.cos(segment.angle * Math.PI / 180) - dy * Math.sin(segment.angle * Math.PI / 180)) / length;
        if (alignment < .7) continue;
        const t = Math.max(0, Math.min(1, ((x - segment.ax) * segment.dx + (y - segment.ay) * segment.dy) / segment.length2));
        const distance = (x - segment.ax - t * segment.dx) ** 2 + (y - segment.ay - t * segment.dy) ** 2;
        if (distance < bestDistance) { bestDistance = distance; best = segment; }
      }
      if (!best) { flush(); continue; }
      const start: Point = [a[0] + (b[0] - a[0]) * from, a[1] + (b[1] - a[1]) * from];
      const end: Point = [a[0] + (b[0] - a[0]) * to, a[1] + (b[1] - a[1]) * to];
      const startDistance = lengths[i - 1] + (lengths[i] - lengths[i - 1]) * from;
      const endDistance = lengths[i - 1] + (lengths[i] - lengths[i - 1]) * to;
      if (!current || current.status !== best.status || Math.abs(current.end - startDistance) > 1) {
        flush(); current = { status: best.status, path: [start, end], start: startDistance, end: endDistance };
      } else { current.path.push(end); current.end = endDistance; }
    }
  }
  flush();
  return runs;
}

export function remainingCongestionPath(run: CongestionRun, progress: number): Point[] {
  if (progress <= run.start) return run.path;
  if (progress >= run.end) return [];
  const fraction = (progress - run.start) / (run.end - run.start);
  // Run points are approximately equally spaced in distance, with boundary pieces shorter.
  // Find the cut by cumulative geographic distance to avoid a discontinuity at GPS updates.
  let distance = 0;
  const target = (run.end - run.start) * fraction;
  for (let i = 1; i < run.path.length; i++) {
    const a = run.path[i - 1], b = run.path[i];
    const segment = Math.hypot((b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), b[1] - a[1]) * Math.PI / 180 * 6371000;
    if (distance + segment >= target) {
      const t = Math.max(0, Math.min(1, (target - distance) / (segment || 1)));
      return [[a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], ...run.path.slice(i)];
    }
    distance += segment;
  }
  return [];
}
