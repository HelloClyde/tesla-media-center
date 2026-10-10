/** Run small geometry batches between browser input/paint opportunities. */
export function createMapRenderQueue(onError: (error: unknown) => void) {
  let frame: number | undefined;
  let generation = 0;
  function cancel() { generation++; if (frame !== undefined) cancelAnimationFrame(frame); frame = undefined; }
  function start(work: Iterator<void>) {
    cancel();
    const id = generation;
    const run = () => {
      frame = undefined;
      if (id !== generation) return;
      const started = performance.now();
      try {
        for (let count = 0; count < 256 && id === generation; count++) {
          if (work.next().done) return;
          if (performance.now() - started >= 4) break;
        }
      } catch (error) { if (id === generation) onError(error); return; }
      // At most one bounded batch per display frame. Repeated zero-delay
      // timers used to compete with wheel/pinch events before the next paint.
      if (id === generation) frame = requestAnimationFrame(run);
    };
    frame = requestAnimationFrame(run);
  }
  return { start, cancel };
}
