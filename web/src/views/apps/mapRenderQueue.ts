/** Run small geometry batches between browser input/paint opportunities. */
export function createMapRenderQueue(onError: (error: unknown) => void, budgetMs = 4, maxSteps = 256) {
  let frame: number | undefined;
  let generation = 0;
  let active: Iterator<void> | undefined, paused = false;
  let executing: Iterator<void> | undefined;
  let resume: (() => void) | undefined;
  function cancel() {
    generation++; if (frame !== undefined) cancelAnimationFrame(frame); frame = undefined;
    const previous = active; active = undefined; resume = undefined;
    // Staged Three geometries own buffers even before they enter the scene.
    // Returning the iterator runs its finally block when a viewport is replaced.
    if (previous !== executing) previous?.return?.();
  }
  function start(work: Iterator<void>) {
    cancel();
    active = work;
    const id = generation;
    const run = () => {
      frame = undefined;
      if (id !== generation || paused) return;
      const started = performance.now();
      try {
        for (let count = 0; count < maxSteps && id === generation; count++) {
          executing = work;
          let step: IteratorResult<void>;
          try { step = work.next(); }
          finally {
            executing = undefined;
            if (active !== work) work.return?.();
          }
          if (id !== generation) return;
          if (step.done) { active = undefined; resume = undefined; return; }
          if (performance.now() - started >= budgetMs) break;
        }
      } catch (error) { if (id === generation) { cancel(); onError(error); } return; }
      // At most one bounded batch per display frame. Repeated zero-delay
      // timers used to compete with wheel/pinch events before the next paint.
      if (id === generation && !paused) frame = requestAnimationFrame(run);
    };
    resume = run;
    if (!paused) frame = requestAnimationFrame(run);
  }
  function setPaused(value: boolean) {
    if (paused === value) return;
    paused = value;
    if (paused && frame !== undefined) { cancelAnimationFrame(frame); frame = undefined; }
    else if (!paused && resume && frame === undefined) frame = requestAnimationFrame(resume);
  }
  return { start, cancel, setPaused };
}
