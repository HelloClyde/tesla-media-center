import { cumulative, matchPosition, type AppRoute, type Point } from './amapNavigation';

export interface LiveTrafficLight {
  point: Point;
  phases: { start: number; end: number; color: 'red' | 'green' | 'yellow' }[];
}

export function upcomingTrafficSignal(route: AppRoute, progress: number, lights: LiveTrafficLight[],
                                      updatedAt: number, nowMs: number) {
  if (!route.path.length || nowMs - updatedAt > 45_000 || updatedAt - nowMs > 15_000) return null;
  const lengths = cumulative(route);
  const now = nowMs / 1000;
  let best: { point: Point; color: LiveTrafficLight['phases'][number]['color']; seconds: number; distance: number } | null = null;
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
                                                  seconds, distance: Math.max(0, ahead) };
  }
  return best;
}
