import {afterEach, expect, it, vi} from 'vitest';
afterEach(() => {vi.unstubAllGlobals(); localStorage.clear();});
it('upgrades old cache rows and scans only metadata keys for size and eviction', async () => {
  vi.resetModules();
  const now = Date.now(), removed: string[] = [], createIndex = vi.fn();
  const rows = [['a', [1, 12 * 1048576, now]], ['b', [2, 12 * 1048576, now]], ['c', [3, 3 * 1048576, now]]] as const;
  const scan = vi.fn(), fullCursor = vi.fn(() => {throw new Error('large payload should not be deserialized');});
  const db: any = {
    objectStoreNames: {contains: () => true}, close() {},
    transaction(_name: string, mode: string) {
      const tx: any = {objectStore: () => ({
        index: () => ({openKeyCursor() {
          scan(); const request: any = {}; let index = 0;
          const step = () => queueMicrotask(() => {
            if (index === rows.length) {request.result = null; request.onsuccess(); tx.oncomplete(); return;}
            const row = rows[index++];
            request.result = {primaryKey: row[0], key: row[1], continue: step,
              get value() {throw new Error('metadata scan accessed payload');}};
            request.onsuccess();
          }); step(); return request;
        }}),
        openCursor: fullCursor,
        delete(key: string) {removed.push(key); if (mode === 'readwrite') queueMicrotask(() => tx.oncomplete?.());},
      })};
      return tx;
    },
  };
  const opening = vi.fn((_name, version) => {
    expect(version).toBe(2);
    const request: any = {result: db, transaction: {objectStore: () => ({indexNames: {contains: () => false}, createIndex})}};
    queueMicrotask(() => {request.onupgradeneeded(); request.onsuccess();}); return request;
  });
  vi.stubGlobal('indexedDB', {open: opening});
  const cache = await import('./amapBrowserTileCache');
  expect(await cache.browserMapCacheStats()).toMatchObject({available: true, count: 3, usedBytes: 27 * 1048576});
  expect(createIndex).toHaveBeenCalledWith('metadata', ['touchedAt', 'bytes', 'fetchedAt']);
  expect(await cache.updateBrowserMapCacheConfig(168, 16)).toBe(true);
  expect(removed).toEqual(['a']);
  expect(scan).toHaveBeenCalledTimes(2); expect(fullCursor).not.toHaveBeenCalled();
});
