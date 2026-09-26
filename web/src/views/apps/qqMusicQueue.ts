export type PlayMode = 'order' | 'loop' | 'single' | 'shuffle';
export function nextIndex(length: number, current: number, delta: number, mode: PlayMode, ended = false, random = Math.random): number {
  if (!length) return -1;
  if (mode === 'shuffle' && length === 1) return 0;
  if (ended && mode === 'single' && current >= 0) return current;
  if (mode === 'shuffle' && length > 1) return (Math.max(0, current) + 1 + Math.floor(random() * (length - 1))) % length;
  const next = current + delta;
  if (mode === 'loop' || mode === 'single') return (next + length) % length;
  return next >= 0 && next < length ? next : -1;
}
