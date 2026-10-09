import { describe, expect, it } from 'vitest';
import { cumulative, type AppRoute } from './amapNavigation';
import { mapSignsVisible, routeCameraSigns } from './amapMapSigns';
import { navigationViewport } from './amapNavigationViewport';
import { groundOffset } from './teslaMapCoordinates';

describe('native camera map signs', () => {
  it('hides road-level icons when zoomed out and always hides them in route overview', () => {
    expect(mapSignsVisible(17)).toBe(true);
    expect(mapSignsVisible(15.5)).toBe(true);
    expect(mapSignsVisible(15.25)).toBe(false);
    expect(mapSignsVisible(10)).toBe(false);
    expect(mapSignsVisible(17, true)).toBe(false);
    expect(mapSignsVisible(Number.NaN)).toBe(false);
    expect(mapSignsVisible(Infinity)).toBe(false);
  });
  it('keeps icons available throughout automatic navigation speed zooms', () => {
    for (const speed of [0, 50, 80, 100, 120, 160]) {
      expect(mapSignsVisible(navigationViewport(speed).zoom)).toBe(true);
    }
  });
  it('places verified camera limits at their App route distance and skips invalid records', () => {
    const route: AppRoute = { id: 1, path: [[120, 30], [120.001, 30], [120.002, 30]],
      steps: [], breaks: [], distance: 200, labels: [] };
    const halfFirstLink = cumulative(route)[1] / 2;
    route.speedCameras = [
      { at: halfFirstLink, type: 25, speed: [80, 255] },
      { at: halfFirstLink, type: 25, speed: [80] },
      { at: -1, type: 7, speed: [60] },
      { at: 10, type: 7, speed: [255] },
    ];
    const signs = routeCameraSigns(route);
    expect(signs).toHaveLength(1);
    expect(signs[0]).toMatchObject({ type: 25, limit: 80 });
    expect(signs[0].point[0]).toBeCloseTo(120.0005, 6);
    expect(signs[0].point[1]).toBeCloseTo(30, 6);
    const [east, south] = groundOffset(signs[0].displayPoint, signs[0].point);
    expect(east).toBeCloseTo(0, 1);
    expect(south).toBeCloseTo(18, 1);
  });
});
