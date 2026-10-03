import { describe, expect, it } from 'vitest';
import { findParallelRoute } from './amapParallelRoad';
import type { AppRoute } from './amapNavigation';

const origin: [number, number] = [120, 30];
function route(id: number, road: string, offset = 0): AppRoute {
  return { id, path: [[120 + offset, 30], [120 + offset, 30.01]],
    steps: [{ start: 0, end: 1, road }], breaks: [], distance: 1110, labels: [] };
}

describe('manual parallel road correction', () => {
  it('chooses an explicitly labelled side road near the vehicle', () => {
    const main = route(0, '主路'), side = route(1, 'XX路辅路', .00015);
    expect(findParallelRoute([main, side], main, origin, 'side')).toBe(1);
  });
  it('can return from a side road to an unlabelled main road', () => {
    const main = route(0, 'XX路'), side = route(1, 'XX路辅路', .00015);
    expect(findParallelRoute([main, side], side, origin, 'main')).toBe(0);
  });
  it('distinguishes stacked elevated and ground routes by road name', () => {
    const elevated = route(0, 'XX高架'), ground = route(1, 'XX路地面道路');
    expect(findParallelRoute([elevated, ground], elevated, origin, 'ground')).toBe(1);
    expect(findParallelRoute([elevated, ground], ground, origin, 'elevated')).toBe(0);
  });
  it('does not pretend an unlabelled or distant road is a known alternative', () => {
    const current = route(0, 'XX路'), unknown = route(1, 'YY路', .00015);
    expect(findParallelRoute([current, unknown], current, origin, 'side')).toBe(-1);
    expect(findParallelRoute([current, route(2, 'XX路辅路', .002)], current, origin, 'side')).toBe(-1);
  });
  it('rejects a nearby opposite-direction carriageway', () => {
    const current = route(0, '主路');
    const reverse = route(1, 'XX路辅路', .0001);
    reverse.path.reverse();
    expect(findParallelRoute([current, reverse], current, origin, 'side')).toBe(-1);
  });
});
