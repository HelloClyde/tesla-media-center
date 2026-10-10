/** Smooth button/wheel dolly without rebuilding map geometry on each input. */
export function createNavigationZoom(durationMs = 180) {
  let transition: { from: number; to: number; start: number } | undefined;
  return {
    get active() { return transition !== undefined; },
    start(distance: number, steps: number, now: number, min: number, max: number) {
      if (!Number.isFinite(distance) || distance <= 0 || !Number.isFinite(steps) || !Number.isFinite(now)) return;
      const from = Math.max(min, Math.min(max, distance));
      // Accumulate successive inputs at the pending destination, but start
      // from the displayed distance so reversing never snaps the camera.
      const to = Math.max(min, Math.min(max, (transition?.to ?? from) * 2 ** (-steps * .5)));
      transition = Math.abs(to - from) < .001 ? undefined : {from, to, start: now};
    },
    sample(now: number): number | undefined {
      if (!transition) return;
      const {from, to, start} = transition;
      const t = Math.max(0, Math.min(1, (now - start) / durationMs));
      // Respond on the first frame even when trackpad events keep retargeting;
      // restarting a slow ease-in on every event would stall a continuous zoom.
      const blend = 1 - (1 - t) ** 3;
      const value = Math.exp(Math.log(from) + (Math.log(to) - Math.log(from)) * blend);
      if (t === 1) { transition = undefined; return to; }
      return value;
    },
    cancel() { transition = undefined; },
  };
}
