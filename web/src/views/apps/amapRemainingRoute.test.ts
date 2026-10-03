import { describe, expect, it } from 'vitest';
import { cumulative, type AppRoute } from './amapNavigation';
import { remainingRouteSections } from './amapRemainingRoute';

const route: AppRoute = { id: 0, path: [[120, 30], [120, 30.001], [120, 30.002], [120.01, 30.01], [120.01, 30.011]],
  breaks: [3], steps: [], distance: 0, labels: [] };
const lengths = cumulative(route);

describe('remaining route geometry', () => {
  it('keeps the whole planned route before navigation', () => {
    expect(remainingRouteSections(route, 0)).toEqual([route.path.slice(0, 3), route.path.slice(3)]);
  });
  it('starts at the interpolated vehicle position and never joins a break', () => {
    const sections = remainingRouteSections(route, lengths[1] / 2);
    expect(sections[0][0][0]).toBeCloseTo(120, 8);
    expect(sections[0][0][1]).toBeCloseTo(30.0005, 8);
    expect(sections[0].slice(1)).toEqual(route.path.slice(1, 3));
    expect(sections[1]).toEqual(route.path.slice(3));
  });
  it('removes completed sections and the entire route at arrival', () => {
    expect(remainingRouteSections(route, lengths[2])).toEqual([[], route.path.slice(3)]);
    expect(remainingRouteSections(route, lengths[4])).toEqual([[], []]);
  });
});
