import { describe, expect, it } from 'vitest';
import { congestionSegmentProgresses, remainingCongestionPath, upcomingCongestion, type CongestionRun } from './amapRouteTraffic';

describe('APK route congestion', () => {
  const run: CongestionRun = {
    status: 4, start: 20, end: 100,
    path: [[116.4, 39.9], [116.4004, 39.9], [116.4008, 39.9]],
  };

  it('retains native route-link geometry and trims already driven congestion', () => {
    expect(remainingCongestionPath(run, 10)).toEqual(run.path);
    expect(remainingCongestionPath(run, 100)).toEqual([]);
    const ahead = remainingCongestionPath(run, 60);
    expect(ahead[0][0]).toBeGreaterThan(run.path[0][0]);
    expect(ahead[ahead.length - 1]).toEqual(run.path[run.path.length - 1]);
  });

  it('keeps 2D and 3D progress anchored to the decoded interval despite rounded geometry', () => {
    const spans = congestionSegmentProgresses(run);
    expect(spans[0].start).toBe(20);
    expect(spans[spans.length - 1].end).toBeCloseTo(100, 8);
    expect(spans[0].end).toBeCloseTo(60, 1);
    const nearlyFinished = remainingCongestionPath(run, 99);
    expect(nearlyFinished).toHaveLength(2);
    expect(nearlyFinished[0][0]).toBeGreaterThan(run.path[1][0]);
    expect(nearlyFinished[0][0]).toBeLessThan(run.path[2][0]);
    expect(remainingCongestionPath(run, 100)).toEqual([]);
  });

  const timed: CongestionRun = { ...run, duration: 330, timings: [
    { start: 20, end: 60, duration: 30 }, { start: 60, end: 100, duration: 300 },
  ] };

  it('shows the pass time ahead and trims different link speeds independently', () => {
    expect(upcomingCongestion([timed], 0)).toMatchObject({ active: false, distance: 20, length: 80, duration: 330 });
    expect(upcomingCongestion([timed], 40)).toMatchObject({ active: true, distance: 0, length: 60, duration: 315 });
    expect(upcomingCongestion([timed], 80)?.duration).toBe(150);
    expect(upcomingCongestion([timed], 100)).toBeUndefined();
  });

  it('groups adjoining colours but leaves a clear road between jams separate', () => {
    const next = { ...timed, status: 3 as const, start: 100, end: 200, duration: 120, timings: undefined };
    const later = { ...next, start: 250, end: 350, duration: 90 };
    expect(upcomingCongestion([timed, next, later], 0)).toMatchObject({ status: 4, length: 180, duration: 450 });
    expect(upcomingCongestion([timed, next, later], 100)).toMatchObject({ status: 3, active: true, length: 100, duration: 120 });
    expect(upcomingCongestion([timed, next, later], 220)).toMatchObject({ active: false, distance: 30, duration: 90 });
  });

  it('does not guess missing times, and can use known times after an unknown link is passed', () => {
    const unknown = { ...timed, duration: null, timings: [
      { start: 20, end: 60, duration: null }, { start: 60, end: 100, duration: 300 },
    ] };
    expect(upcomingCongestion([unknown], 20)?.duration).toBeNull();
    expect(upcomingCongestion([unknown], 80)?.duration).toBe(150);
    expect(upcomingCongestion([run], 20)?.duration).toBeNull();
  });

  it('hides distant or completed jams and keeps stopped-vehicle estimates stable', () => {
    expect(upcomingCongestion([timed], -2000)).toBeUndefined();
    expect(upcomingCongestion([], 0)).toBeUndefined();
    expect(upcomingCongestion([timed], NaN)).toBeUndefined();
    expect(upcomingCongestion([timed], 40)).toEqual(upcomingCongestion([timed], 40));
  });
});
