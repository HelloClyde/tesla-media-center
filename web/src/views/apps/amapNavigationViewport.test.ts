import { describe, expect, it } from 'vitest';
import { navigationViewport } from './amapNavigationViewport';

describe('speed-aware navigation viewport', () => {
  it('keeps local streets close and positions the vehicle below center', () => {
    expect(navigationViewport(25)).toEqual({ zoom: 17, vehicleY: .62 });
  });
  it('shows substantially more road ahead at highway speed', () => {
    const city = navigationViewport(50);
    const highway = navigationViewport(120);
    expect(highway.zoom).toBe(15.5);
    expect(highway.zoom).toBeLessThan(city.zoom);
    expect(highway.vehicleY).toBeGreaterThan(city.vehicleY);
  });
  it('bounds invalid and extreme speed values', () => {
    expect(navigationViewport(null)).toEqual(navigationViewport(0));
    expect(navigationViewport(Number.NaN)).toEqual(navigationViewport(0));
    expect(navigationViewport(250)).toEqual(navigationViewport(120));
  });
});
