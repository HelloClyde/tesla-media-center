import {isNavigationManeuver, navigationManeuvers, type NavigationManeuver} from '@/components/navigationArrow';
export type Point = [number, number];
export interface RouteStep { start: number; end: number; road: string; serviceArea?: string; roundaboutExit?: number; maneuver?: NavigationManeuver }
export interface AppRoute { id: number; path: Point[]; steps: RouteStep[]; breaks: number[]; distance: number; labels: string[]; duration?: number | null; tolls?: number | null; tollCurrency?: string | null; trafficLights?: Point[]; trafficLightCount?: number; trafficRuns?: import('./amapRouteTraffic').CongestionRun[]; speedLimits?: import('./amapSpeedLimit').SpeedLimitSection[]; speedCameras?: import('./amapSpeedLimit').SpeedLimitCamera[]; laneGuides?: import('./amapLaneGuidance').LaneGuide[] }
export const meters = (a: Point, b: Point) => {
  const rad = Math.PI / 180, lat = (a[1] + b[1]) * rad / 2;
  return Math.hypot((b[0] - a[0]) * Math.cos(lat), b[1] - a[1]) * rad * 6371000;
};
export function cumulative(route: AppRoute) {
  const values = [0], breaks = new Set(route.breaks);
  for (let i = 1; i < route.path.length; i++) values.push(values[i - 1] + (breaks.has(i) ? 0 : meters(route.path[i - 1], route.path[i])));
  return values;
}
export interface MatchMotion { heading?: number | null; speed?: number | null; accuracy?: number }
export function matchPosition(route: AppRoute, position: Point, previous = 0, reacquire = false, motion?: MatchMotion) {
  const lengths = cumulative(route), breaks = new Set(route.breaks);
  let best = { distance: Infinity, progress: 0, index: 0, point: route.path[0] };
  const scale = Math.cos(position[1] * Math.PI / 180);
  let bestScore = Infinity;
  const motionHeading = typeof motion?.heading === 'number' && Number.isFinite(motion.heading) ? motion.heading : undefined;
  const motionSpeed = typeof motion?.speed === 'number' && Number.isFinite(motion.speed) ? Math.max(0, motion.speed) : 0;
  const motionAccuracy = typeof motion?.accuracy === 'number' && Number.isFinite(motion.accuracy) ? Math.max(0, motion.accuracy) : 0;
  const headingValid = motionHeading !== undefined && motionSpeed > 2;
  const behind = motion ? Math.max(50, Math.min(120, motionSpeed * 3 + motionAccuracy * 2)) : 50;
  for (let i = 0; i < route.path.length - 1; i++) {
    if (breaks.has(i + 1) || (!reacquire && lengths[i + 1] < previous - behind)) continue;
    const a = route.path[i], b = route.path[i + 1];
    const dx = (b[0] - a[0]) * scale, dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, (((position[0] - a[0]) * scale * dx) + (position[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    const point: Point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const distance = meters(point, position), progress = lengths[i] + (lengths[i + 1] - lengths[i]) * t;
    // Loop ramps bring distant/opposing parts of the route close together.
    // Motion and along-route continuity distinguish them without hiding the
    // actual perpendicular distance used by the departure detector.
    const continuity = reacquire ? 0 : motion ? Math.abs(progress - previous) * .12
      : Math.max(0, progress - previous - 150) * .03;
    const segmentHeading = headingValid ? Math.atan2(dx, dy) * 180 / Math.PI : 0;
    const angle = headingValid ? Math.abs((((motionHeading! - segmentHeading + 540) % 360 + 360) % 360) - 180) : 0;
    const direction = headingValid ? 30 * (angle / 180) ** 2 : 0;
    const score = distance + continuity + direction;
    if (score < bestScore) { best = { distance, progress, index: i, point }; bestScore = score; }
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
  return instructionAtStep(route, progress, values, stepIndex);
}

/** The second action's distance starts at the first action, not at the car. */
export function upcomingInstructions(route: AppRoute, progress: number) {
  const values = cumulative(route);
  const stepIndex = route.steps.findIndex(step => values[step.end] > progress + 5);
  const first = instructionAtStep(route, progress, values, stepIndex);
  if (stepIndex < 0 || stepIndex >= route.steps.length - 1) return [first];
  return [first, instructionAtStep(route, values[route.steps[stepIndex].end], values, stepIndex + 1)];
}

function instructionAtStep(route: AppRoute, progress: number, values: number[], stepIndex: number) {
  const step = route.steps[stepIndex < 0 ? route.steps.length - 1 : stepIndex];
  const next = route.steps[stepIndex + 1];
  if (!next || stepIndex < 0) return { text: navigationManeuvers.destination.text, arrow: 'destination', maneuver: 'destination', road: step.road, distance: Math.max(0, values[values.length - 1] - progress), key: route.steps.length };
  if (step.maneuver === 'roundabout-enter' || step.maneuver === 'roundabout-exit') {
    const entering = step.maneuver === 'roundabout-enter';
    const candidate = entering && next.maneuver === 'roundabout-exit' ? next.roundaboutExit : step.roundaboutExit;
    const exit = typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 1 && candidate <= 16 ? candidate : undefined;
    return { text: entering ? `进入环岛${exit ? `，从第${exit}出口驶出` : ''}`
      : exit ? `从第${exit}出口驶出环岛` : '驶出环岛', arrow: step.maneuver, road: next.road,
      distance: Math.max(0, values[step.end] - progress), key: stepIndex, maneuver: step.maneuver };
  }
  const a = route.path[Math.max(step.start, step.end - 1)], b = route.path[step.end];
  const c = route.path[next.start], d = route.path[Math.min(next.end, next.start + 1)];
  const bearing = (a: Point, b: Point) => Math.atan2((b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), b[1] - a[1]) * 180 / Math.PI;
  const angle = ((bearing(c, d) - bearing(a, b) + 540) % 360) - 180;
  // Explicit route actions survive even when a loop's final two edges do not
  // reflect its overall turn. Geometry is used only for an unknown action.
  const fallback: NavigationManeuver = Math.abs(angle) > 150 ? (angle > 0 ? 'uturn-right' : 'uturn-left')
    : angle > 120 ? 'sharp-right' : angle < -120 ? 'sharp-left'
    : angle > 35 ? 'right' : angle < -35 ? 'left' : 'straight';
  const maneuver = step.maneuver && isNavigationManeuver(step.maneuver) ? step.maneuver : fallback;
  return { text: navigationManeuvers[maneuver].text, arrow: maneuver, maneuver, road: next.road,
    distance: Math.max(0, values[step.end] - progress), key: stepIndex };
}
