import { meters, type Point } from './amapNavigation';

export interface DisplayPosition { point: Point; heading: number }
export function createPositionTransition() {
  let from: DisplayPosition | undefined, target: DisplayPosition | undefined;
  let started = 0, duration = 0, lastUpdate: number | undefined, cadence: number | undefined;
  let startVelocity = [0, 0, 0];
  const angleDelta = (a: number, b: number) => ((b - a + 540) % 360) - 180;
  function state(now: number) {
    if (!target || !from) return { position: target, velocity: [0, 0, 0] };
    const t = duration ? Math.max(0, Math.min(1, (now - started) / duration)) : 1;
    const delta = [target.point[0] - from.point[0], target.point[1] - from.point[1], angleDelta(from.heading, target.heading)];
    const values = delta.map((distance, index) => {
      // Monotone Hermite interpolation preserves the current velocity when
      // retargeted, while bounding the curve between the two received fixes.
      const slope = distance ? Math.max(0, Math.min(3, startVelocity[index] * duration / distance)) * distance : 0;
      const value = (-2*t*t*t + 3*t*t)*distance + (t*t*t - 2*t*t + t)*slope + (t*t*t - t*t)*distance;
      const velocity = t >= 1 || !duration ? 0 : ((-6*t*t + 6*t)*distance
        + (3*t*t - 4*t + 1)*slope + (3*t*t - 2*t)*distance) / duration;
      return { value, velocity };
    });
    return { position: { point: [from.point[0] + values[0].value, from.point[1] + values[1].value] as Point,
      heading: (from.heading + values[2].value + 360) % 360 }, velocity: values.map(value => value.velocity) };
  }
  return {
    sample: (now: number) => state(now).position,
    move(next: DisplayPosition, now: number, snap = false) {
      // Duplicate GPS/fusion callbacks must not restart an unfinished move or
      // shorten the cadence to the interval between copies of the same fix.
      if (!snap && target && meters(target.point, next.point) < .03
          && Math.abs(angleDelta(target.heading, next.heading)) < .05) return;
      const current = state(now);
      from = current.position || next;
      startVelocity = current.velocity;
      const interval = lastUpdate === undefined ? 600 : now - lastUpdate;
      const boundedInterval = Math.max(100, Math.min(2000, interval));
      cadence = cadence === undefined ? boundedInterval : cadence * .75 + boundedInterval * .25;
      // Filter irregular callback spacing instead of changing speed abruptly
      // after every GPS callback. Hold the last fix when callbacks stop.
      duration = !target || snap || meters(from.point, next.point) > 250 ? 0
        : Math.max(160, Math.min(2200, cadence * 1.3));
      if (!duration) { startVelocity = [0, 0, 0]; cadence = undefined; }
      target = { point: [...next.point], heading: next.heading };
      started = now; lastUpdate = now;
    },
    done: (now: number) => now >= started + duration,
  };
}
