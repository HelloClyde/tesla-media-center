import { cumulative, type AppRoute, type Point } from './amapNavigation';
import { geometryBounds } from './amapGeometryBounds';

export const ROUTE_BUBBLE_WIDTH = 142, ROUTE_BUBBLE_HEIGHT = 58;
export type ScreenPoint = { x: number; y: number };
export type PreviewArea = { left: number; top: number; right: number; bottom: number };
export type RouteBubblePlacement = { index: number; x: number; y: number; anchor: ScreenPoint };
const samples = new WeakMap<AppRoute, Point[]>();

/** Fit every displayed alternative, including the remaining navigation routes. */
export function previewRouteBounds(routes: AppRoute[], endpoints: Point[] = []): [Point, Point] | undefined {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const route of routes) {
    const bounds = geometryBounds(route.path);
    west = Math.min(west, bounds[0]); south = Math.min(south, bounds[1]);
    east = Math.max(east, bounds[2]); north = Math.max(north, bounds[3]);
  }
  for (const point of endpoints) {
    west = Math.min(west, point[0]); south = Math.min(south, point[1]);
    east = Math.max(east, point[0]); north = Math.max(north, point[1]);
  }
  if (![west, south, east, north].every(Number.isFinite)) return;
  return [[west, south], [east, north]];
}

/** Bound layout work independently of the number of native route vertices. */
export function routePreviewSamples(route: AppRoute): Point[] {
  const saved = samples.get(route);
  if (saved) return saved;
  const lengths = cumulative(route), total = lengths[lengths.length - 1];
  if (!total || route.path.length < 2) return [];
  const result: Point[] = [];
  let index = 1;
  for (let sample = 0; sample <= 64; sample++) {
    const target = total * sample / 64;
    while (index < lengths.length - 1 && (lengths[index] < target || lengths[index] === lengths[index - 1])) index++;
    const a = route.path[index - 1], b = route.path[index];
    const fraction = Math.max(0, Math.min(1, (target - lengths[index - 1]) / (lengths[index] - lengths[index - 1] || 1)));
    result.push([a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction]);
  }
  samples.set(route, result);
  return result;
}

export function routePreviewColor(index: number, selected: number, navigating = false): string {
  if (navigating) return index === selected ? '#1688ef' : '#929ba6';
  return index === selected ? '#12bc87' : ['#527da8', '#a77b50', '#8274a8', '#478c91'][index % 4];
}

function distanceToRoute(point: ScreenPoint, path: ScreenPoint[]): number {
  let nearest = Infinity;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1], b = path[i], dx = b.x - a.x, dy = b.y - a.y;
    const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy || 1)));
    nearest = Math.min(nearest, Math.hypot(point.x - a.x - t * dx, point.y - a.y - t * dy));
  }
  return nearest;
}

/** Prefer separated branches, with non-overlapping labels inside the map's free area. */
export function layoutRouteBubbles(paths: ScreenPoint[][], area: PreviewArea): RouteBubblePlacement[] {
  const halfWidth = ROUTE_BUBBLE_WIDTH / 2, halfHeight = ROUTE_BUBBLE_HEIGHT / 2;
  if (area.right - area.left < ROUTE_BUBBLE_WIDTH || area.bottom - area.top < ROUTE_BUBBLE_HEIGHT) return [];
  const result: RouteBubblePlacement[] = [];
  const offsets = [[0, -44], [0, 44], [92, 0], [-92, 0], [92, -44], [-92, 44]];
  paths.forEach((path, index) => {
    let best: RouteBubblePlacement | undefined, score = -Infinity;
    const from = Math.floor(path.length * .16), to = Math.ceil(path.length * .84);
    for (let i = from; i < to; i++) {
      const anchor = path[i];
      if (!anchor || anchor.x < area.left || anchor.x > area.right || anchor.y < area.top || anchor.y > area.bottom) continue;
      const separation = Math.min(120, ...paths.filter((_, other) => other !== index).map(other => distanceToRoute(anchor, other)));
      for (const [dx, dy] of offsets) {
        const x = Math.max(area.left + halfWidth, Math.min(area.right - halfWidth, anchor.x + dx));
        const y = Math.max(area.top + halfHeight, Math.min(area.bottom - halfHeight, anchor.y + dy));
        const overlap = result.reduce((sum, previous) => sum
          + Math.max(0, ROUTE_BUBBLE_WIDTH + 10 - Math.abs(x - previous.x))
          * Math.max(0, ROUTE_BUBBLE_HEIGHT + 10 - Math.abs(y - previous.y)), 0);
        const coveredRoad = paths.reduce((sum, points) => sum + points.filter(point =>
          Math.abs(point.x - x) < halfWidth + 4 && Math.abs(point.y - y) < halfHeight + 4).length, 0);
        const value = separation * .6 - Math.hypot(x - anchor.x, y - anchor.y) * .15
          - Math.abs(i / path.length - .5) * 8 - overlap * 20 - coveredRoad * 6;
        if (value > score) { score = value; best = { index, x, y, anchor }; }
      }
    }
    if (best) result.push(best);
  });
  return result;
}
