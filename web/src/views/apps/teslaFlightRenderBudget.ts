/** Reduce pixel work only after sustained slow frames, without resizing repeatedly. */
export function createFlightRenderBudget() {
  let scale = 1;
  let warmup = 0;
  let sampleTime = 0;
  let samples = 0;
  let cooldown = 0;
  return {
    get scale() { return scale; },
    sample(frameMs: number) {
      // Tab suspension and isolated shader/GC stalls are not a sustained GPU limit.
      if (!Number.isFinite(frameMs) || frameMs <= 0 || frameMs > 150) return scale;
      warmup += frameMs;
      if (warmup < 800 || scale === .7) return scale;
      if (cooldown > 0) { cooldown -= frameMs; return scale; }
      sampleTime += frameMs;
      samples++;
      if (sampleTime < 500 || samples < 8) return scale;
      const average = sampleTime / samples;
      sampleTime = samples = 0;
      if (average > (scale === 1 ? 28 : 35)) {
        scale = scale === 1 ? .85 : .7;
        cooldown = 750;
      }
      return scale;
    },
    reset() { scale = 1; warmup = sampleTime = samples = cooldown = 0; },
  };
}
