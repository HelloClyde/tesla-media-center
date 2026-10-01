export type Point = [number, number];
export interface RouteStep { start: number; end: number; road: string; serviceArea?: string; maneuver?: 'left' | 'right' | 'bear-left' | 'bear-right' }
export interface AppRoute { id: number; path: Point[]; steps: RouteStep[]; breaks: number[]; distance: number; labels: string[]; duration?: number | null; tolls?: number | null; tollCurrency?: string | null }
export const meters = (a: Point, b: Point) => {
  const rad = Math.PI / 180, lat = (a[1] + b[1]) * rad / 2;
  return Math.hypot((b[0] - a[0]) * Math.cos(lat), b[1] - a[1]) * rad * 6371000;
};
export function cumulative(route: AppRoute) {
  const values = [0], breaks = new Set(route.breaks);
  for (let i = 1; i < route.path.length; i++) values.push(values[i - 1] + (breaks.has(i) ? 0 : meters(route.path[i - 1], route.path[i])));
  return values;
}
export function matchPosition(route: AppRoute, position: Point, previous = 0, reacquire = false) {
  const lengths = cumulative(route), breaks = new Set(route.breaks);
  let best = { distance: Infinity, progress: 0, index: 0, point: route.path[0] };
  const scale = Math.cos(position[1] * Math.PI / 180);
  for (let i = 0; i < route.path.length - 1; i++) {
    if (breaks.has(i + 1) || (!reacquire && lengths[i + 1] < previous - 50)) continue;
    const a = route.path[i], b = route.path[i + 1];
    const dx = (b[0] - a[0]) * scale, dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, (((position[0] - a[0]) * scale * dx) + (position[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    const point: Point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const distance = meters(point, position), progress = lengths[i] + (lengths[i + 1] - lengths[i]) * t;
    // Nearby overlapping roads favour the current section instead of jumping ahead.
    const score = distance + (reacquire ? 0 : Math.max(0, progress - previous - 150) * .03);
    const bestScore = best.distance + (reacquire ? 0 : Math.max(0, best.progress - previous - 150) * .03);
    if (score < bestScore) best = { distance, progress, index: i, point };
  }
  return best;
}
export function pointAt(route: AppRoute, progress: number): Point {
  const values = cumulative(route);
  for (let i = 1; i < values.length; i++) {
    if (values[i] >= progress && values[i] > values[i - 1]) {
      const t = Math.max(0, (progress - values[i - 1]) / (values[i] - values[i - 1]));
      return [route.path[i - 1][0] + (route.path[i][0] - route.path[i - 1][0]) * t,
        route.path[i - 1][1] + (route.path[i][1] - route.path[i - 1][1]) * t];
    }
  }
  return route.path[route.path.length - 1];
}
export function instruction(route: AppRoute, progress: number) {
  const values = cumulative(route);
  const stepIndex = route.steps.findIndex(step => values[step.end] > progress + 5);
  const step = route.steps[stepIndex < 0 ? route.steps.length - 1 : stepIndex];
  const next = route.steps[stepIndex + 1];
  if (!next || stepIndex < 0) return { text: '到达目的地附近', arrow: '⚑', road: step.road, distance: Math.max(0, values[values.length - 1] - progress), key: route.steps.length };
  const a = route.path[Math.max(step.start, step.end - 1)], b = route.path[step.end];
  const c = route.path[next.start], d = route.path[Math.min(next.end, next.start + 1)];
  const bearing = (a: Point, b: Point) => Math.atan2((b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), b[1] - a[1]) * 180 / Math.PI;
  const angle = ((bearing(c, d) - bearing(a, b) + 540) % 360) - 180;
  const text = step.maneuver === 'left' ? '左转' : step.maneuver === 'right' ? '右转'
    : step.maneuver === 'bear-left' ? '靠左行驶' : step.maneuver === 'bear-right' ? '靠右行驶'
    : Math.abs(angle) > 150 ? '掉头' : angle > 35 ? '右转' : angle < -35 ? '左转' : '继续直行';
  return { text, arrow: text === '右转' || text === '靠右行驶' ? '↱' : text === '左转' || text === '靠左行驶' ? '↰' : text === '掉头' ? '↶' : '↑', road: next.road,
    distance: Math.max(0, values[step.end] - progress), key: stepIndex };
}
