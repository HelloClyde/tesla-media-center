import {afterEach, beforeEach, expect, it, vi} from 'vitest';

vi.mock('./amapMapWorker', () => ({
  encodeBrowserMapTile: async (tile: unknown) => {
    const payload = JSON.stringify(tile);
    return {payload, encoding: 'json', bytes: payload.length};
  },
  decodeBrowserMapTile: async (row: any) => JSON.parse(row.payload),
}));
let cache: typeof import('./amapBrowserTileCache');
const rows = new Map<string, any>();
const removed: string[] = [];
let stalledRead = false, failWrite = false;
const estimate = vi.fn(), persisted = vi.fn(), persist = vi.fn();

function database() {
  return {
    objectStoreNames: {contains: () => true}, close() {},
    transaction(_name: string, mode: string) {
      let cursorActive = false, waiting = false, aborted = false;
      const tx: any = {error: null, abort() {aborted = true; queueMicrotask(() => tx.onabort?.());}};
      const store = {
        get(key: string) {
          const request: any = {};
          if (stalledRead) waiting = true;
          else queueMicrotask(() => {request.result = rows.get(key); request.onsuccess?.();});
          return request;
        },
        put(row: any) {
          if (failWrite) {failWrite = false; tx.error = new DOMException('full', 'QuotaExceededError'); return;}
          rows.set(row.key, row);
        },
        delete(key: string) {removed.push(key); rows.delete(key);},
        clear() {rows.clear();},
        index() {return {openKeyCursor() {
          cursorActive = true;
          const metadata = [...rows.values()].sort((a,b) => a.touchedAt-b.touchedAt);
          const request: any = {}; let at = 0;
          const step = () => queueMicrotask(() => {
            const row = metadata[at++];
            request.result = row ? {primaryKey: row.key, key: [row.touchedAt,row.bytes,row.fetchedAt], continue: step} : null;
            request.onsuccess?.(); if (!row) tx.oncomplete?.();
          });
          step(); return request;
        }};},
      };
      tx.objectStore = () => store;
      queueMicrotask(() => {
        if (aborted || cursorActive || waiting) return;
        if (tx.error) tx.onabort?.(); else tx.oncomplete?.();
      });
      return tx;
    },
  };
}
beforeEach(async () => {
  vi.resetModules(); rows.clear(); removed.length = 0; stalledRead = false; failWrite = false;
  localStorage.clear(); estimate.mockReset(); persisted.mockReset(); persist.mockReset();
  estimate.mockResolvedValue({quota: 20 * 1073741824, usage: 0}); persisted.mockResolvedValue(false);
  vi.stubGlobal('navigator', {storage: {estimate, persisted, persist}});
  vi.stubGlobal('indexedDB', {open() {
    const request: any = {result: database()};
    queueMicrotask(() => request.onsuccess?.()); return request;
  }});
  cache = await import('./amapBrowserTileCache');
});
afterEach(() => {vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear();});

it('defaults to 1 GiB and accepts 8 GiB without exceeding the configured range', async () => {
  expect((await cache.browserMapCacheStats()).maxMB).toBe(1024);
  expect(await cache.updateBrowserMapCacheConfig(168, 8192)).toBe(true);
  expect((await cache.browserMapCacheStats()).maxMB).toBe(8192);
  expect(await cache.updateBrowserMapCacheConfig(168, 8193)).toBe(false);
});
it('upgrades the old 96-MB default, preserves other old choices, and supports an explicit new 96-MB choice', async () => {
  localStorage.setItem('tmc-amap-browser-cache-settings-v1', JSON.stringify({ttlHours: 24,maxMB: 96}));
  expect(await cache.browserMapCacheStats()).toMatchObject({ttlHours:24,maxMB:1024});
  localStorage.setItem('tmc-amap-browser-cache-settings-v1', JSON.stringify({ttlHours: 24,maxMB: 256}));
  expect((await cache.browserMapCacheStats()).maxMB).toBe(256);
  await cache.updateBrowserMapCacheConfig(24, 96);
  expect((await cache.browserMapCacheStats()).maxMB).toBe(96);
});
it('leaves headroom for other origin storage and reports a real quota without assuming zero on failure', async () => {
  estimate.mockResolvedValue({quota: 300 * 1048576,usage: 225 * 1048576});
  rows.set('old', {key:'old',bytes:27*1048576,touchedAt:1,fetchedAt:Date.now()});
  expect(await cache.browserMapCacheStats()).toMatchObject({maxMB:1024,effectiveMaxMB:42,
    quotaBytes:300*1048576,usageBytes:225*1048576,persistent:false});
  estimate.mockRejectedValue(new Error('unsupported'));
  expect(await cache.browserMapCacheStats()).toMatchObject({quotaBytes:null,usageBytes:null,effectiveMaxMB:1024});
});
it('evicts old map resources before writing near a quota and preserves the newly cached tile', async () => {
  estimate.mockResolvedValue({quota: 20*1048576,usage: 16*1048576});
  rows.set('old', {key:'old',bytes:16*1048576,touchedAt:1,fetchedAt:Date.now()});
  const tile = {level:14,x:1,y:2,collection:{features:[]}};
  await cache.storeMapTiles('full', [tile]);
  expect(removed).toContain('old');
  expect(rows.get('full/14/1/2').payload).toContain('features');
});
it('recovers an actual quota write failure with eviction instead of rejecting navigation', async () => {
  rows.set('old', {key:'old',bytes:5*1048576,touchedAt:1,fetchedAt:Date.now()});
  failWrite = true;
  await expect(cache.storeMapTiles('full', [{level:14,x:1,y:2}])).resolves.toBeUndefined();
  expect(removed).toContain('old'); expect(rows.has('full/14/1/2')).toBe(true);
});
it('requests persistence only when explicitly invoked and exposes the grant', async () => {
  expect(persist).not.toHaveBeenCalled();
  persist.mockResolvedValue(true); persisted.mockResolvedValue(true);
  expect(await cache.requestBrowserMapPersistence()).toBe(true);
  expect((await cache.browserMapCacheStats()).persistent).toBe(true);
});
it('treats a stalled disk read as a miss after a bounded wait', async () => {
  vi.useFakeTimers(); stalledRead = true;
  const done = vi.fn();
  const read = cache.readMapTiles('full', [[14,1,2]]).then(value => {done(); return value;});
  await vi.advanceTimersByTimeAsync(1799); expect(done).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect((await read).size).toBe(0);
});
it('does not resurrect a pending persistent write after clearing the cache', async () => {
  let release!: (value: StorageEstimate) => void;
  estimate.mockImplementationOnce(() => new Promise(resolve => {release = resolve;}));
  const saving = cache.storeMapTiles('full', [{level:14,x:1,y:2}]);
  await vi.waitFor(() => expect(release).toBeDefined());
  await cache.clearBrowserMapCache();
  release({quota:20*1073741824,usage:0}); await saving;
  expect(rows.size).toBe(0);
  expect((await cache.readMapTiles('full', [[14,1,2]])).size).toBe(0);
});
