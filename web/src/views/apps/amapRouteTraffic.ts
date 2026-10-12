import { meters, type Point } from './amapNavigation';

/** Congestion on a verified App 5.1 route link, in measured route metres. */
export type CongestionTiming = { start: number; end: number; duration?: number | null };
export type CongestionRun = { status: 2 | 3 | 4; path: Point[]; start: number; end: number;
  duration?: number | null; timings?: CongestionTiming[] };
export type CongestionNotice = { status: 2 | 3 | 4; active: boolean; distance: number;
  length: number; duration: number | null };

function remainingCongestionTime(run: CongestionRun, progress: number): number | null {
  // A merged run may have very different speeds across its native links. Trim
  // each link's passTime individually instead of scaling the whole run by metres.
  const timings = run.timings?.length ? run.timings : [run];
  let seconds = 0;
  for (const timing of timings) {
    if (progress >= timing.end) continue;
    if (typeof timing.duration !== 'number' || !Number.isFinite(timing.duration)
        || timing.duration <= 0 || timing.end <= timing.start) return null;
    seconds += timing.duration * (timing.end - Math.max(progress, timing.start)) / (timing.end - timing.start);
  }
  return seconds;
}

/** One contiguous slow/jammed section ahead; its colour may change inside it. */
export function upcomingCongestion(runs: CongestionRun[], progress: number, lookAhead = 2000): CongestionNotice | undefined {
  if (!Number.isFinite(progress)) return;
  const index = runs.findIndex(run => run.end > progress);
  if (index < 0) return;
  const first = runs[index];
  if (first.start - progress > lookAhead) return;
  let end = first.end, status = first.status, duration = remainingCongestionTime(first, progress);
  for (let i = index + 1; i < runs.length; i++) {
    const run = runs[i];
    if (Math.abs(run.start - end) > .2) break;
    end = run.end;
    status = Math.max(status, run.status) as CongestionNotice['status'];
    const seconds = remainingCongestionTime(run, progress);
    duration = duration !== null && seconds !== null ? duration + seconds : null;
  }
  return { status, active: progress >= first.start, distance: Math.max(0, first.start - progress),
    length: end - Math.max(progress, first.start), duration };
}

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
