import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { clearBrowserMapCache, readMapTiles, storeMapTiles, updateBrowserMapCacheConfig } from './amapBrowserTileCache';

const tile = (x = 1) => ({level: 14, x, y: 2, collection: {features: []}});
beforeEach(async () => {
  vi.stubGlobal('indexedDB', undefined);
  localStorage.clear();
  await clearBrowserMapCache();
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('shares decoded tiles immediately before asynchronous persistence completes', async () => {
  const value = tile();
  const saving = storeMapTiles('full', [value]);
  expect((await readMapTiles('full', [[14, 1, 2]])).get('14/1/2')?.tile).toBe(value);
  await saving;
});
it('expires the shared window using the configured cache time', async () => {
  vi.useFakeTimers(); vi.setSystemTime(100_000);
  await storeMapTiles('full', [tile()]);
  await updateBrowserMapCacheConfig(1, 16);
  vi.setSystemTime(100_000 + 3600001);
  expect((await readMapTiles('full', [[14, 1, 2]])).size).toBe(0);
});
it('clears memory even when persistent browser storage is unavailable', async () => {
  const saving = storeMapTiles('full', [tile()]);
  await clearBrowserMapCache(); await saving;
  expect((await readMapTiles('full', [[14, 1, 2]])).size).toBe(0);
});
it('bounds the shared window and excludes partial or failed data', async () => {
  await storeMapTiles('full', Array.from({length: 10}, (_, x) => tile(x)));
  expect((await readMapTiles('full', Array.from({length: 10}, (_, x) => [14, x, 2]))).size).toBe(8);
  await storeMapTiles('full', [{...tile(20), missingLayers: ['surfaces']}, {...tile(21), error: 'unavailable'}]);
  expect((await readMapTiles('full', [[14, 20, 2], [14, 21, 2]])).size).toBe(0);
});
it('keeps rendered, full and lane entries separate', async () => {
  await storeMapTiles('full', [tile()]);
  expect((await readMapTiles('rendered', [[14, 1, 2]])).size).toBe(0);
  expect((await readMapTiles('lanes', [[14, 1, 2]])).size).toBe(0);
});
