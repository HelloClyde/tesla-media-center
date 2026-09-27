import { describe, expect, it } from 'vitest';
import { cumulative, instruction, matchPosition, pointAt, type AppRoute } from './amapNavigation';
const route: AppRoute = { id: 0, path: [[116, 39], [116, 39.001], [116.001, 39.001]], steps: [
  { start: 0, end: 1, road: '甲路' }, { start: 1, end: 2, road: '乙路' },
], breaks: [], distance: 198, labels: [] };
describe('navigation geometry', () => {
  it('matches real coordinates to traveled distance', () => {
    const match = matchPosition(route, [116, 39.0005]);
    expect(match.distance).toBeLessThan(.01);
    expect(match.progress).toBeCloseTo(55.6, 0);
  });
  it('gives a right turn for north then east', () => {
    expect(instruction(route, 30).text).toBe('右转');
    expect(instruction(route, 30).road).toBe('乙路');
    expect(instruction(route, 150).text).toBe('到达目的地附近');
  });
  it('does not match or interpolate an omitted junction connector', () => {
    const disconnected: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.01, 39.001], [116.011, 39.001]], breaks: [2] };
    const lengths = cumulative(disconnected);
    expect(lengths[2]).toBe(lengths[1]);
    expect(matchPosition(disconnected, [116.005, 39.001]).distance).toBeGreaterThan(400);
    expect(pointAt(disconnected, lengths[1] + 1)[0]).toBeGreaterThanOrEqual(116.01);
  });
  it('clamps replay at the destination', () => {
    expect(pointAt(route, 10000)).toEqual(route.path[2]);
  });
});
