import { describe, expect, it } from 'vitest';
import { advanceDemoProgress, demoCruiseSpeed } from './amapSimulation';

describe('speed-limit simulation', () => {
  it('shows the legal speed while advancing distance at twice real time', () => {
    const sections = [{ start: 0, end: 1000, limit: 60 }];
    expect(demoCruiseSpeed(sections, 0)).toBe(60);
    const result = advanceDemoProgress(sections, 0, 1000);
    expect(result.speedKmh).toBe(60);
    expect(result.progress).toBeCloseTo(60 / 3.6 * 2, 5);
  });

  it('changes to the next limit during a tick and uses a known fallback outside covered sections', () => {
    const sections = [{ start: 0, end: 10, limit: 36 }, { start: 10, end: 100, limit: 72 }];
    expect(advanceDemoProgress(sections, 0, 1000)).toEqual({ progress: 30, speedKmh: 72 });
    expect(advanceDemoProgress(undefined, 0, 1000)).toEqual({ progress: 50 / 3.6 * 2, speedKmh: 50 });
  });
});
