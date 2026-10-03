import { cumulative, matchPosition, type AppRoute, type Point } from './amapNavigation';

export interface LiveTrafficLight {
  point: Point;
  phases: { start: number; end: number; color: 'red' | 'green' | 'yellow' }[];
}

export interface UpcomingTrafficSignal {
  point: Point;
  color: LiveTrafficLight['phases'][number]['color'];
  seconds: number;
  distance: number;
  phases: LiveTrafficLight['phases'];
}

export function upcomingTrafficSignal(route: AppRoute, progress: number, lights: LiveTrafficLight[],
                                      updatedAt: number, nowMs: number) {
  if (!route.path.length || nowMs - updatedAt > 45_000 || updatedAt - nowMs > 15_000) return null;
  const lengths = cumulative(route);
  const now = nowMs / 1000;
  let best: UpcomingTrafficSignal | null = null;
  for (const light of lights) {
    if (!Array.isArray(light.point) || light.point.length !== 2) continue;
    const matched = matchPosition(route, light.point, 0, true);
    const ahead = matched.progress - progress;
    if (matched.distance > 25 || ahead < -15 || ahead > 450 || matched.progress > lengths[lengths.length - 1] + 1) continue;
    const phase = light.phases.find(item => item.start <= now && now < item.end);
    if (!phase) continue;
    const seconds = Math.ceil(phase.end - now);
    if (seconds < 1 || seconds > 300) continue;
    if (!best || ahead < best.distance) best = { point: light.point, color: phase.color,
                                                  seconds, distance: Math.max(0, ahead), phases: light.phases };
  }
  return best;
}

// The App supplies signal phases, but not a verified road speed limit. Treat
// this as an arrival-time reference; the UI must always defer to posted limits.
export function greenWaveSpeedWindow(signal: UpcomingTrafficSignal | null, nowMs: number,
                                     currentSpeedKmH: number | null) {
  if (!signal || signal.distance < 80 || signal.distance > 450) return null;
  const now = nowMs / 1000;
  const green = signal.phases.filter(phase => phase.color === 'green' && phase.end - now >= 6)
    .sort((a, b) => a.start - b.start)[0];
  if (!green) return null;
  // Leave three seconds at either edge for GPS and signal clock uncertainty.
  const start = Math.max(1, green.start - now + 3), end = green.end - now - 3;
  if (end <= start) return null;
  const min = Math.ceil(signal.distance / end * 3.6);
  const max = Math.floor(signal.distance / start * 3.6);
  const low = Math.max(10, min), high = Math.min(60, max);
  if (low > high) return null;
  const atCurrentSpeed = currentSpeedKmH !== null && Number.isFinite(currentSpeedKmH)
    && currentSpeedKmH >= low && currentSpeedKmH <= high;
  return { min: low, max: high, atCurrentSpeed };
}
