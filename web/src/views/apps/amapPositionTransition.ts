import { meters, type Point } from './amapNavigation';

export interface DisplayPosition { point: Point; heading: number }
export function createPositionTransition() {
  let from: DisplayPosition | undefined, target: DisplayPosition | undefined;
  let started = 0, duration = 0, lastUpdate: number | undefined;
  function sample(now: number): DisplayPosition | undefined {
    if (!target || !from) return target;
    const t = duration ? Math.max(0, Math.min(1, (now - started) / duration)) : 1;
    const eased = t * t * (3 - 2 * t);
    const angle = ((target.heading - from.heading + 540) % 360) - 180;
    return { point: [from.point[0] + (target.point[0] - from.point[0]) * eased,
      from.point[1] + (target.point[1] - from.point[1]) * eased],
      heading: (from.heading + angle * eased + 360) % 360 };
  }
  return {
    sample,
    move(next: DisplayPosition, now: number, snap = false) {
      from = sample(now) || next;
      const interval = lastUpdate === undefined ? 600 : now - lastUpdate;
      duration = !target || snap || meters(from.point, next.point) > 250 ? 0 : Math.max(100, Math.min(900, interval));
      target = { point: [...next.point], heading: next.heading };
      started = now; lastUpdate = now;
    },
    done: (now: number) => now >= started + duration,
  };
}
