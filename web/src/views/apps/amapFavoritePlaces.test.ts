import { expect, it } from 'vitest';
import { clearBrowserFavoritePlaces, loadBrowserFavoritePlaces } from './amapFavoritePlaces';
import type { Place } from './amapSearch';

const airport: Place = { id: 'airport', name: '杭州萧山国际机场', address: '机场路', location: [120.43, 30.23], entrance: [120.431, 30.231] };

it('keeps a navigable entrance and ignores broken or repeated saved places', () => {
  const storage = { getItem: () => JSON.stringify([
    { ...airport, unexpected: 'discarded' },
    { ...airport, name: '重复地点' },
    { id: 'invalid', name: '错误坐标', location: [999, 30] },
  ]), removeItem: () => {} };
  expect(loadBrowserFavoritePlaces(storage)).toEqual([airport]);
});

it('removes legacy browser data only when migration calls clear', () => {
  let saved: string | null = JSON.stringify([airport]);
  const storage = { getItem: () => saved, removeItem: () => { saved = null; } };
  expect(loadBrowserFavoritePlaces(storage)).toEqual([airport]);
  expect(clearBrowserFavoritePlaces(storage)).toBe(true);
  expect(loadBrowserFavoritePlaces(storage)).toEqual([]);
});
