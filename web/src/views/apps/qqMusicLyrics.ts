export interface LyricLine { time: number; text: string; translation?: string; words?: { time: number; duration: number; text: string }[] }
export function parseLrc(raw: string): LyricLine[] {
  const offset = Number(raw.match(/\[offset:([+-]?\d+)\]/i)?.[1] || 0) / 1000;
  return raw.split(/\r?\n/).flatMap(line => {
    const stamps = [...line.matchAll(/\[(\d+):(\d{2})(?:\.(\d{1,3}))?\]/g)];
    const text = line.replace(/\[[^\]]*\]/g, '').trim();
    return stamps.map(m => ({ time: Math.max(0, Number(m[1]) * 60 + Number(m[2]) + Number('0.' + (m[3] || '0')) + offset), text }));
  }).sort((a, b) => a.time - b.time);
}
export function lyricIndex(lines: LyricLine[], elapsed: number): number {
  let lo = 0, hi = lines.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (lines[mid].time <= elapsed) lo = mid + 1; else hi = mid; }
  return lo - 1;
}

// QQ Music QRC timestamps use milliseconds, including word timestamps.
export function parseQrc(raw: string): LyricLine[] {
  return raw.split(/\r?\n/).flatMap(line => {
    const stamp = line.match(/\[(\d+),(\d+)\]/);
    if (!stamp) return [];
    const content = line.slice(line.indexOf(stamp[0]) + stamp[0].length);
    const words = [...content.matchAll(/([^()]+)\((\d+),(\d+)\)/g)].map(m => ({ text: m[1], time: Number(m[2]) / 1000, duration: Number(m[3]) / 1000 }));
    return words.length ? [{ time: Number(stamp[1]) / 1000, text: words.map(w => w.text).join(''), words }] : [];
  }).sort((a, b) => a.time - b.time);
}
