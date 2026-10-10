// Drawing, decoded worker replies and disk-cache work share the same input
// priority. Downloads may finish during a gesture, but heavy main-thread work
// waits until every map surface has stopped interacting.
const owners = new Set<symbol>();
const listeners = new Set<(busy: boolean) => void>();
let settling: ReturnType<typeof setTimeout> | undefined;
let busy = false;
function publish(value: boolean) {
  if (busy === value) return;
  busy = value;
  for (const listener of [...listeners]) listener(value);
}
export function watchMapInteraction(listener: (busy: boolean) => void) {
  listeners.add(listener); listener(busy);
  return () => { listeners.delete(listener); };
}
export function createMapInteraction() {
  const owner = Symbol();
  let held = false;
  return {
    set(value: boolean) {
      if (held === value) return;
      held = value;
      if (settling !== undefined) clearTimeout(settling);
      settling = undefined;
      if (value) { owners.add(owner); publish(true); }
      else {
        owners.delete(owner);
        if (!owners.size && busy) settling = setTimeout(() => { settling = undefined; publish(false); }, 140);
      }
    },
    dispose() {
      held = false;
      owners.delete(owner);
      if (!owners.size) {
        if (settling !== undefined) clearTimeout(settling);
        settling = undefined; publish(false);
      }
    },
  };
}
export async function waitForMapIdle() {
  if (!busy) return;
  await new Promise<void>(resolve => {
    const release = watchMapInteraction(value => { if (!value) { release(); resolve(); } });
  });
}
