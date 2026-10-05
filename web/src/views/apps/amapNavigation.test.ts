import { describe, expect, it } from 'vitest';
import { cumulative, instruction, matchPosition, pointAt, type AppRoute } from './amapNavigation';
const route: AppRoute = { id: 0, path: [[116, 39], [116, 39.001], [116.001, 39.001]], steps: [
  { start: 0, end: 1, road: '甲路' }, { start: 1, end: 2, road: '乙路' },
], breaks: [], distance: 198, labels: [] };
describe('navigation geometry', () => {
  it('reacquires a real position behind stale progress after signal recovery', () => {
    const result = matchPosition(route, [116, 39.0001], 180, true);
    expect(result.distance).toBeLessThan(.01);
    expect(result.progress).toBeCloseTo(11.1, 0);
  });
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
  it('uses the route maneuver for shallow forks instead of saying straight', () => {
    const fork: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.00005, 39.002]],
      steps: [{ start: 0, end: 1, road: '主路', maneuver: 'bear-right' }, { start: 1, end: 2, road: '右侧岔路' }] };
    expect(instruction(fork, 30).text).toBe('靠右行驶');
    fork.steps[0].maneuver = 'bear-left';
    expect(instruction(fork, 30).text).toBe('靠左行驶');
    fork.steps[0].maneuver = undefined;
    expect(instruction(fork, 30).text).toBe('继续直行');
  });
  it('distinguishes the three branches from a straight road', () => {
    const fork: AppRoute = { ...route, steps: [{ start: 0, end: 1, road: '主路', maneuver: 'fork-middle' },
      { start: 1, end: 2, road: '中间岔路' }] };
    expect(instruction(fork, 30).text).toBe('走中间岔路');
    fork.steps[0].maneuver = 'fork-left';
    expect(instruction(fork, 30).text).toBe('走左侧岔路');
    fork.steps[0].maneuver = 'fork-right';
    expect(instruction(fork, 30).text).toBe('走右侧岔路');
    const straight: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116, 39.002]] };
    expect(instruction(straight, 30).text).toBe('继续直行');
  });
  it('does not match or interpolate an omitted junction connector', () => {
    const disconnected: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.01, 39.001], [116.011, 39.001]], breaks: [2] };
    const lengths = cumulative(disconnected);
    expect(lengths[2]).toBe(lengths[1]);
    expect(matchPosition(disconnected, [116.005, 39.001]).distance).toBeGreaterThan(400);
    expect(pointAt(disconnected, lengths[1] + 1)[0]).toBeGreaterThanOrEqual(116.01);
  });
  it('announces the ring exit before entering and inside the ring despite a right-turn angle', () => {
    const ring: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.001, 39.001], [116.001, 39.002]],
      steps: [{ start: 0, end: 1, road: '入口路', maneuver: 'roundabout-enter' },
        { start: 1, end: 2, road: '环岛', maneuver: 'roundabout-exit', roundaboutExit: 4 },
        { start: 2, end: 3, road: '出口路' }] };
    expect(instruction(ring, 30)).toMatchObject({ text: '进入环岛，从第4出口驶出', arrow: '⟳', road: '环岛' });
    expect(instruction(ring, 120)).toMatchObject({ text: '从第4出口驶出环岛', arrow: '⟳', road: '出口路' });
    delete ring.steps[1].roundaboutExit;
    expect(instruction(ring, 30).text).toBe('进入环岛');
    expect(instruction(ring, 120).text).toBe('驶出环岛');
  });
  it('clamps replay at the destination', () => {
    expect(pointAt(route, 10000)).toEqual(route.path[2]);
  });
});
