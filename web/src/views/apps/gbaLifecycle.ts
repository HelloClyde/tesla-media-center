// Each page/load owns its emulator; stale async work must never restart it.
export function createGbaLifetime() {
  let version = 0, disposed = false;
  return {
    next: () => ++version,
    current: (token: number) => !disposed && token === version,
    active: () => !disposed,
    dispose: () => { disposed = true; ++version; }
  };
}
export function destroyGba(gba: any) {
  if (!gba) return;
  const safely = (work: () => void) => { try { work(); } catch {} };
  safely(() => gba.pause());
  gba.paused = true;
  safely(() => { gba.keypad.eatInput = false; gba.keypad.currentDown = 0x03ff; gba.keypad.unregisterHandlers?.(); });
  safely(() => { gba.audio.jsAudio.onaudioprocess = null; gba.audio.jsAudio.disconnect(); });
  safely(() => { const ctx = gba.audio?.context; if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => {}); });
  safely(() => gba.video?.renderPath?.worker?.terminate());
}
