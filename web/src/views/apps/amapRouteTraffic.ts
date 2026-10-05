import { meters, type Point } from './amapNavigation';

/** Congestion on a verified App 5.1 route link, in measured route metres. */
export type CongestionRun = { status: 2 | 3 | 4; path: Point[]; start: number; end: number };

/** Map each drawn link segment onto the route interval returned by the decoder. */
export function congestionSegmentProgresses(run: CongestionRun): { start: number; end: number }[] {
  const lengths = run.path.slice(1).map((point, i) => meters(run.path[i], point));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  if (total <= 0 || run.end <= run.start) return [];
  let along = 0;
  return lengths.map(length => {
    const start = run.start + (run.end - run.start) * along / total;
    along += length;
    return { start, end: run.start + (run.end - run.start) * along / total };
  });
}

export function remainingCongestionPath(run: CongestionRun, progress: number): Point[] {
  if (progress <= run.start) return run.path;
  if (progress >= run.end) return [];
  const segments = congestionSegmentProgresses(run);
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    if (segment.end >= progress && segment.end > segment.start) {
      const a = run.path[i], b = run.path[i + 1];
      const t = Math.max(0, Math.min(1, (progress - segment.start) / (segment.end - segment.start)));
      return [[a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], ...run.path.slice(i + 1)];
    }
  }
  return [];
}
