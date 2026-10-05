import { describe, expect, it } from 'vitest';
import { congestionSegmentProgresses, remainingCongestionPath, type CongestionRun } from './amapRouteTraffic';

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
});
