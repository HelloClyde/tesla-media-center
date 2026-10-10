import { afterEach, expect, it, vi } from 'vitest';
const { post, cancelDraw } = vi.hoisted(() => ({ post: vi.fn(), cancelDraw: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
vi.mock('leaflet', () => ({ default: {
  canvas: () => ({ remove() {} }),
  layerGroup: () => ({ addTo() { return this; }, remove() {} }),
} }));
vi.mock('./mapRenderQueue', () => ({ createMapRenderQueue: () => ({ start() {}, cancel: cancelDraw }) }));
vi.mock('./amapBrowserTileCache', () => ({
  browserMapTileTtlMs: () => 7 * 24 * 3600000,
  readMemoryMapTiles: () => new Map(), readMapTiles: async () => new Map(),
  storeMapTiles: async () => {},
}));
import { attachAppMap } from './amapVectorMap';
import type { AppRoute } from './amapNavigation';
afterEach(() => { vi.useRealTimers(); post.mockReset(); cancelDraw.mockReset(); });

function fakeMap() {
  const events: Record<string, () => void> = {};
  const map = {
    getPane() {}, createPane: () => ({ style: {} }), getZoom: () => 14,
    getCenter: () => ({lng: 120.0005, lat: 30.0005}),
    getBounds: () => ({ getWest: () => 120, getEast: () => 120.001, getNorth: () => 30.001, getSouth: () => 30 }),
    on(names: string, fn: () => void) { names.split(' ').forEach(name => events[name] = fn); }, off() {},
  };
  return { map: map as any, events };
}
it('keeps in-flight tiles during movement and aborts on disposal', async () => {
  vi.useFakeTimers();
  let resolve!: (value: unknown) => void;
  post.mockImplementationOnce(() => new Promise(r => resolve = r));
  const { map, events } = fakeMap();
  const layer = attachAppMap(map, vi.fn());
  await vi.advanceTimersByTimeAsync(0);
  const signal = post.mock.calls[0][2].signal;
  events.movestart(); events.moveend();
  await vi.advanceTimersByTimeAsync(150);
  expect(signal.aborted).toBe(false);
  expect(post).toHaveBeenCalledTimes(1);
  const batch = post.mock.calls[0][1];
  resolve({ status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]: number[]) => ({ level: batch.level, x, y })) } } });
  post.mockImplementation(() => new Promise(() => {}));
  await vi.advanceTimersByTimeAsync(150);
  expect(post).toHaveBeenCalledTimes(2);
  layer.dispose();
  expect(post.mock.calls[1][2].signal.aborted).toBe(true);
});
it('backs off failed tiles instead of looping on the same request', async () => {
  vi.useFakeTimers(); post.mockRejectedValue(new Error('offline'));
  const { map } = fakeMap(); const layer = attachAppMap(map, vi.fn());
  await vi.advanceTimersByTimeAsync(1000);
  const firstLevel = post.mock.calls[0][1].level;
  // A network error keeps BMD enabled and waits before retrying the tile.
  expect(post.mock.calls.filter(c => c[1].level === firstLevel)).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1500);
  expect(post.mock.calls.filter(c => c[1].level === firstLevel)).toHaveLength(2);
  layer.dispose();
});
it('loads street detail and intermediate levels before distant overview layers', async () => {
  vi.useFakeTimers();
  post.mockImplementation(async (_url, batch) => ({ status: 200, data: { status: 'ok', data: {
    tiles: batch.tiles.map(([x, y]: number[]) => ({ level: batch.level, x, y })),
  } } }));
  const { map } = fakeMap();
  const layer = attachAppMap(map, vi.fn());
  await vi.advanceTimersByTimeAsync(350);
  expect(post.mock.calls.slice(0, 4).map(call => call[1].level)).toEqual([14, 12, 10, 8]);
  layer.dispose();
});
it('warms route tiles only after the visible map and receives an empty response', async () => {
  vi.useFakeTimers();
  post.mockImplementation(async (url, batch) => url.endsWith('/prefetch')
    ? { status: 204, data: '' }
    : { status: 200, data: { status: 'ok', data: {
      tiles: batch.tiles.map(([x, y]: number[]) => ({ level: batch.level, x, y })),
    } } });
  const { map } = fakeMap();
  const layer = attachAppMap(map, vi.fn());
  const route: AppRoute = { id: 1, path: [[120.1, 30.2], [120.2, 30.2]],
    breaks: [], steps: [], distance: 10000, labels: [] };
  layer.setRoute(route);
  await vi.advanceTimersByTimeAsync(1500);
  const urls = post.mock.calls.map(call => call[0]);
  const firstWarm = urls.findIndex(url => url.endsWith('/prefetch'));
  expect(firstWarm).toBeGreaterThanOrEqual(6);
  expect(post.mock.calls[firstWarm][1].tiles.length).toBeLessThanOrEqual(2);
  expect(post.mock.calls[firstWarm][1].level).toBe(14);
  layer.dispose();
});
