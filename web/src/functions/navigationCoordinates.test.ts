import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { wgs84togcj02 } from 'coordtransform';
beforeEach(() => { localStorage.clear(); vi.resetModules(); });
afterEach(() => vi.restoreAllMocks());
it('defaults to unchanged browser coordinates', async () => {
  const m = await import('./navigationCoordinates');
  expect(m.navigationCoordinateMode.value).toBe('direct');
  expect(m.browserNavigationPoint(116.397, 39.908)).toEqual([116.397, 39.908]);
});
it('converts only when selected and preserves the setting after reload', async () => {
  let m = await import('./navigationCoordinates');
  m.setNavigationCoordinateMode('wgs84');
  expect(m.browserNavigationPoint(116.397, 39.908)).toEqual(wgs84togcj02(116.397, 39.908));
  vi.resetModules(); m = await import('./navigationCoordinates');
  expect(m.navigationCoordinateMode.value).toBe('wgs84');
  m.setNavigationCoordinateMode('direct');
  expect(m.browserNavigationPoint(116.397, 39.908)).toEqual([116.397, 39.908]);
});
it('falls back to direct for invalid storage and keeps working without storage access', async () => {
  localStorage.setItem('tmc:navigation-coordinate-mode', 'invalid');
  const m = await import('./navigationCoordinates');
  expect(m.navigationCoordinateMode.value).toBe('direct');
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
  expect(() => m.setNavigationCoordinateMode('wgs84')).not.toThrow();
  expect(m.browserNavigationPoint(116.397, 39.908)).toEqual(wgs84togcj02(116.397, 39.908));
});
