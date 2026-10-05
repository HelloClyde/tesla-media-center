import { speedLimitAt, type SpeedLimitSection } from './amapSpeedLimit';

export const DEMO_TIME_SCALE = 2;
const FALLBACK_SPEED_KMH = 50;

export function demoCruiseSpeed(sections: SpeedLimitSection[] | undefined, progress: number): number {
  return speedLimitAt(sections, progress)?.limit ?? FALLBACK_SPEED_KMH;
}

/** Advance route metres at the road limit while playback time runs at 2×. */
export function advanceDemoProgress(sections: SpeedLimitSection[] | undefined, progress: number,
  elapsedMs: number): { progress: number; speedKmh: number } {
  if (!Number.isFinite(progress) || !Number.isFinite(elapsedMs) || elapsedMs <= 0)
    return { progress, speedKmh: demoCruiseSpeed(sections, progress) };
  let remaining = elapsedMs * DEMO_TIME_SCALE / 1000;
  let current = progress;
  const valid = (sections || []).filter(section => Number.isFinite(section.start) && Number.isFinite(section.end)
    && section.end > section.start && Number.isInteger(section.limit) && section.limit >= 5 && section.limit <= 160);
  // A tick may cross a speed-limit boundary; spend the remaining simulated
  // time at the new limit rather than applying the old limit to the full tick.
  for (let crossed = 0; remaining > 0 && crossed <= valid.length * 2 + 1; crossed++) {
    const active = speedLimitAt(valid, current);
    const speed = active?.limit ?? FALLBACK_SPEED_KMH;
    const boundary = active?.end ?? valid.reduce((next, section) =>
      section.start > current ? Math.min(next, section.start) : next, Infinity);
    const possible = speed / 3.6 * remaining;
    if (!Number.isFinite(boundary) || current + possible <= boundary) {
      current += possible;
      remaining = 0;
    } else {
      remaining -= (boundary - current) * 3.6 / speed;
      current = boundary;
    }
  }
  return { progress: current, speedKmh: demoCruiseSpeed(valid, current) };
}
