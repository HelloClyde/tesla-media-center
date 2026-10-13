// Small transactional IndexedDB test double; browser refresh is also checked
// against the real database during local UI verification.
export function navigationSessionTestDb() {
  const rows = new Map<string, unknown>();
  let routeWrites = 0, failWrite = false;
  const db = {
    close() {}, createObjectStore() {},
    transaction(_store: string, mode: string) {
      const pending = new Map(rows);
      let aborted = false;
      const tx: any = { error: null, abort() { aborted = true; } };
      tx.objectStore = () => ({
        get(key: string) {
          const request: any = {};
          queueMicrotask(() => { request.result = structuredClone(pending.get(key)); request.onsuccess?.(); });
          return request;
        },
        put(value: unknown, key: string) {
          if (failWrite) { failWrite = false; tx.error = new DOMException('full', 'QuotaExceededError'); aborted = true; return; }
          pending.set(key, structuredClone(value)); if (key === 'route') routeWrites++;
        },
        clear() { pending.clear(); },
      });
      queueMicrotask(() => queueMicrotask(() => {
        if (aborted) { tx.onabort?.(); return; }
        if (mode === 'readwrite') { rows.clear(); pending.forEach((value, key) => rows.set(key, value)); }
        tx.oncomplete?.();
      }));
      return tx;
    },
  };
  return { rows, get routeWrites() { return routeWrites; }, failNextWrite() { failWrite = true; },
    reset() { rows.clear(); routeWrites = 0; failWrite = false; },
    indexedDB: { open() { const request: any = { result: db }; queueMicrotask(() => request.onsuccess?.()); return request; } },
  };
}
