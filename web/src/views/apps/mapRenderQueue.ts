/** Run small geometry batches between browser input/paint opportunities. */
export function createMapRenderQueue(onError: (error: unknown) => void) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  function cancel() { generation++; clearTimeout(timer); timer = undefined; }
  function start(work: Iterator<void>) {
    cancel();
    const id = generation;
    const run = () => {
      if (id !== generation) return;
      const started = performance.now();
      try {
        for (let count = 0; count < 32 && id === generation; count++) {
          if (work.next().done) { timer = undefined; return; }
          if (performance.now() - started >= 4) break;
        }
      } catch (error) { if (id === generation) { timer = undefined; onError(error); } return; }
      if (id === generation) timer = setTimeout(run, 0);
    };
    timer = setTimeout(run, 0);
  }
  return { start, cancel };
}
