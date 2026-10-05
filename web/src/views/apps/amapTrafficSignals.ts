import { cumulative, matchPosition, type AppRoute, type Point } from './amapNavigation';

export interface LiveTrafficLight {
  point: Point;
  phases: { start: number; end: number; color: 'red' | 'green' | 'yellow' }[];
  /** Timestamp of the ETA frame that actually contained this light. */
  observedAt?: number;
}

export interface UpcomingTrafficSignal {
  point: Point;
  color: LiveTrafficLight['phases'][number]['color'];
  seconds: number;
  distance: number;
  phases: LiveTrafficLight['phases'];
  observedAt: number;
}

/** The APK has a dedicated red-three-seconds status; only announce it when
 * the live phase plan actually changes from red to green near the car. */
export function nearGreenReminder(signal: UpcomingTrafficSignal | null, nowMs: number) {
  if (!signal || signal.color !== 'red' || signal.distance > 200
      || signal.seconds < 1 || signal.seconds > 3
      || nowMs - signal.observedAt > 20_000 || signal.observedAt - nowMs > 1_000) return null;
  const now = nowMs / 1000;
  const red = signal.phases.find(phase => phase.color === 'red' && phase.start <= now && now < phase.end);
  const green = signal.phases.find(phase => phase.color === 'green' && red
    && phase.start >= red.end && phase.start - red.end <= 1 && phase.end > phase.start);
  if (!red || !green || red.end - now > 3 || red.end <= now) return null;
  return { point: signal.point, phaseEnd: red.end, text: '红灯即将变绿' };
}

/** Route link flags identify signalized crossings even when no live phase is available. */
const routeLightIndexes = new WeakMap<AppRoute, { lights?: Point[]; path: Point[]; positions: { point: Point; at: number }[] }>();
export function upcomingRouteTrafficLight(route: AppRoute, progress: number, horizon = 450) {
  if (!Number.isFinite(progress) || !route.path.length) return null;
  let indexed = routeLightIndexes.get(route);
  if (!indexed || indexed.lights !== route.trafficLights || indexed.path !== route.path) {
    const lengths = cumulative(route), byCoordinate = new Map<string, number[]>();
    route.path.forEach((point, index) => {
      const key = point.join(',');
      const positions = byCoordinate.get(key) || [];
      positions.push(lengths[index]); byCoordinate.set(key, positions);
    });
    const positions: { point: Point; at: number }[] = [];
    for (const point of route.trafficLights || []) {
      if (!Array.isArray(point) || point.length !== 2) continue;
      const exact = byCoordinate.get(point.join(','));
      if (exact) for (const at of exact) positions.push({ point, at });
      else {
        const matched = matchPosition(route, point, 0, true);
        if (matched.distance <= 25) positions.push({ point, at: matched.progress });
      }
    }
    indexed = { lights: route.trafficLights, path: route.path, positions };
    routeLightIndexes.set(route, indexed);
  }
  let nearest: { point: Point; distance: number } | null = null;
  for (const { point, at } of indexed.positions) {
    const ahead = at - progress;
    if (ahead < -15 || ahead > horizon) continue;
    if (!nearest || ahead < nearest.distance) nearest = { point, distance: Math.max(0, ahead) };
  }
  return nearest;
}

/** Live phases should only be tied to a recent, confidently matched car fix. */
export function trustedTrafficSignalFix(accuracy: number,
                                        fusion?: { state: string; estimated?: boolean }) {
  return Number.isFinite(accuracy) && accuracy >= 0 && accuracy <= 25
    && (!fusion || (fusion.state === 'tracking' && !fusion.estimated));
}

/** A brief positioning correction must not erase an already received phase plan. */
export function recentTrafficSignalFix(lastTrustedAt: number, nowMs: number, stationary = false) {
  return lastTrustedAt > 0 && nowMs - lastTrustedAt <= (stationary ? 90_000 : 20_000)
    && lastTrustedAt - nowMs <= 1_000;
}

/** An empty or partial ETA refresh must not cancel a phase whose end is still known. */
export function mergeTrafficSignalLights(previous: LiveTrafficLight[], incoming: LiveTrafficLight[],
                                         updatedAt: number, nowMs: number): LiveTrafficLight[] {
  const byPoint = new Map<string, LiveTrafficLight>();
  const key = (light: LiveTrafficLight) => light.point.map(value => value.toFixed(6)).join(',');
  for (const light of previous) {
    const observedAt = light.observedAt ?? updatedAt;
    if (nowMs - observedAt <= 90_000 && light.phases.some(phase => phase.end * 1000 > nowMs)) {
      byPoint.set(key(light), { ...light, observedAt });
    }
  }
  for (const light of incoming) byPoint.set(key(light), { ...light, observedAt: updatedAt });
  return [...byPoint.values()];
}

export function upcomingTrafficSignal(route: AppRoute, progress: number, lights: LiveTrafficLight[],
                                      updatedAt: number, nowMs: number) {
  // The server accepts App ETA frames up to 90 seconds old. The absolute
  // phase end still bounds the countdown; never invent time beyond that plan.
  if (!route.path.length) return null;
  const lengths = cumulative(route);
  const now = nowMs / 1000;
  let best: UpcomingTrafficSignal | null = null;
  for (const light of lights) {
    if (!Array.isArray(light.point) || light.point.length !== 2) continue;
    const observedAt = light.observedAt ?? updatedAt;
    if (nowMs - observedAt > 90_000 || observedAt - nowMs > 15_000) continue;
    const matched = matchPosition(route, light.point, 0, true);
    const ahead = matched.progress - progress;
    if (matched.distance > 25 || ahead < -15 || ahead > 450 || matched.progress > lengths[lengths.length - 1] + 1) continue;
    const phase = light.phases.find(item => item.start <= now && now < item.end);
    if (!phase) continue;
    const seconds = Math.ceil(phase.end - now);
    if (seconds < 1 || seconds > 300) continue;
    if (!best || ahead < best.distance) best = { point: light.point, color: phase.color,
                                                  seconds, distance: Math.max(0, ahead), phases: light.phases, observedAt };
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
