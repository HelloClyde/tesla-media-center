import { describe, expect, it } from 'vitest';
import { cumulative, pointAt, type AppRoute, type Point } from './amapNavigation';
import { matchOverviewRoute, navigationRouteOptions, remainingRoutePreview, sameRemainingRoute } from './amapNavigationOverview';
import { routePreviewColor } from './amapRoutePreview';

const route = (path: Point[], id = 0): AppRoute => ({ id, path, breaks: [], steps: [{ start: 0, end: path.length - 1, road: '测试道路' }],
  labels: [], distance: 4000, duration: 1200, tolls: 0, tollCurrency: 'CNY' });
const a: Point = [120, 30], b: Point = [120, 30.01], end: Point = [120.03, 30.04];
const active = route([a, b, end]);

describe('navigation route overview', () => {
  it('pins the current route and keeps native indices when a refresh changes route order', () => {
    const travelled = cumulative(active)[1], here = pointAt(active, travelled);
    const refreshed = [route([here, [120.04, 30.01], end], 50), { ...route([here, end], 51), duration: 600 },
      route([here, [119.98, 30.03], end], 52)];
    const options = navigationRouteOptions([active], 0, 'old-session', travelled, refreshed, 'new-session');
    expect(options).toHaveLength(3);
    expect(options[0]).toMatchObject({ current: true, token: 'old-session', routeIndex: 0 });
    expect(options[0].routes[0]).toBe(active);
    expect(options[0].preview.path[0]).toEqual(here);
    expect(options[0].preview.duration).toBe(600);
    expect(options.slice(1).map(option => option.routeIndex)).toEqual([0, 2]);
    expect(options[2].routes).toBe(refreshed);
    expect(active.path[0]).toEqual(a);
  });
  it('does not infer route identity from equal session-local IDs or a common trunk', () => {
    const diverging = route([a, b, [119.99, 30.03], end]);
    expect(sameRemainingRoute(active, diverging)).toBe(false);
    const options = navigationRouteOptions([active], 0, 'old', 0, [diverging], 'fresh');
    expect(options).toHaveLength(2);
    expect(options.map(option => option.token)).toEqual(['old', 'fresh']);
  });
  it('keeps discontinuities and removes the already travelled geometry from the overview', () => {
    const split = { ...active, path: [a, b, [120.02, 30.02], end] as Point[], breaks: [2] };
    const preview = remainingRoutePreview(split, cumulative(split)[1] / 2);
    expect(preview.breaks).toEqual([2]);
    expect(preview.path[0][1]).toBeCloseTo(30.005);
    expect(preview.steps).toEqual([]);
    expect(preview.distance).toBeLessThan(split.distance);
  });
  it('compares the remainders after the car moved during a slow refresh', () => {
    const travelled = cumulative(active)[1] + 300;
    const options = navigationRouteOptions([active], 0, 'old', travelled, [{ ...active, id: 12, duration: 900 }], 'fresh');
    expect(options).toHaveLength(1);
    expect(options[0].preview.duration).toBeLessThan(900);
  });
  it('uses the latest vehicle position, and rejects passed forks or an opposite direction', () => {
    const here = pointAt(active, 700), match = matchOverviewRoute(active, here, 0, 50)!;
    expect(match.progress).toBeCloseTo(700, 2);
    expect(match.point[1]).toBeCloseTo(here[1]);
    expect(matchOverviewRoute(active, [119.98, 30.01], 0, 50)).toBeUndefined();
    expect(matchOverviewRoute(active, here, 180, 50)).toBeUndefined();
    expect(matchOverviewRoute(route([]), here)).toBeUndefined();
  });
  it('uses blue and gray during navigation independently of the planning palette', () => {
    expect(routePreviewColor(0, 0, true)).toBe('#1688ef');
    expect(routePreviewColor(1, 0, true)).toBe('#929ba6');
    expect(routePreviewColor(2, 0, true)).toBe('#929ba6');
    expect(routePreviewColor(0, 0)).toBe('#12bc87');
  });
});
