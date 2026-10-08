import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
const mocks = vi.hoisted(() => ({ tiles: [[16, 1, 1]], post: vi.fn(), created: [] as any[], saved: new Map<string, any>() }));
vi.mock('axios', () => ({ default: { post: mocks.post } }));
vi.mock('./amapBrowserTileCache', () => ({
  browserMapTileTtlMs: () => 7*24*3600000,
  readMapTiles: vi.fn(async (kind: string, tiles: number[][]) => kind === 'full'
    ? new Map(tiles.map(tile => [tile.join('/'), mocks.saved.get(tile.join('/'))] as const).filter(entry => entry[1]))
    : new Map()),
  storeMapTiles: vi.fn(async () => undefined),
}));
vi.mock('./amapViewport', () => ({ viewportTiles: () => mocks.tiles }));
vi.mock('./mapRenderQueue', () => ({ createMapRenderQueue: () => ({ start: (work: Iterator<void>) => { while (!work.next().done) {} }, cancel: () => {} }) }));
vi.mock('leaflet', () => {
  const layer = (_data?: any, options?: any) => {
    const result = { options, removed: false, addTo(group: any) { group.addLayer?.(result); return result; }, remove() { result.removed = true; } };
    mocks.created.push(result); return result;
  };
  return { default: {
    canvas: () => ({ remove() {} }),
    layerGroup: () => ({ addTo() { return this; }, addLayer() {}, removeLayer(item: any) { item.removed = true; }, remove() {} }),
    geoJSON: layer, polygon: layer, marker: layer, divIcon: (x: any) => x,
  } };
});
import { attachAppMap } from './amapVectorMap';
const tile = (x: number) => ({ level: 16, x, y: 1, collection: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { style: 18 << 5, name: '' }, geometry: { type: 'LineString', coordinates: [[116, 39], [116.1, 39]] } }] } });
const response = (tiles: any[]) => ({ status: 200, data: { status: 'ok', data: { tiles } } });
const map = () => ({ getPane: () => undefined, createPane: () => ({ style: {} }), getZoom: () => 16,
  getBounds: () => ({ getWest: () => 116, getEast: () => 117, getNorth: () => 40, getSouth: () => 39 }),
  getSize: () => ({ x: 800, y: 600 }), on() {}, off() {},
}) as any;
beforeEach(() => { mocks.created.length = 0; mocks.saved.clear(); mocks.tiles = [[16, 1, 1]]; mocks.post.mockReset(); });
afterEach(() => vi.unstubAllGlobals());
it('restores a saved decoded tile without a network request', async () => {
  mocks.saved.set('16/1/1', {tile:tile(1),at:Date.now()});
  for(const [x,y] of [[1,0],[2,1],[1,2],[0,1],[0,0],[2,0],[2,2],[0,2]])
    mocks.saved.set(`16/${x}/${y}`,{tile:{...tile(x),y},at:Date.now()});
  const app=attachAppMap(map(),vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  await flushPromises();
  expect(mocks.post).not.toHaveBeenCalled();
  app.dispose();
});
it('uses the App road casing and fill styles in the 2D map', async () => {
  const styled: any = tile(1);
  styled.collection.features[0].properties.paintKey = '20001/1';
  const paints = { day: { '20001/1': [{ minZoom: 16, maxZoom: 16,
    outerWidth: 45, innerWidth: 30,
    outer: { color: '#bdcbd3', opacity: 1 }, inner: { color: '#eef6fc', opacity: .9 } }] } };
  mocks.post.mockRejectedValueOnce({response:{status:404}})
    .mockResolvedValueOnce(response([{ ...styled, roadPaints: paints }]));
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  expect(mocks.created.map(layer => layer.options.style.color)).toEqual(['#bdcbd3', '#eef6fc']);
  expect(mocks.created.map(layer => layer.options.style.weight)).toEqual([4.5, 3]);
  app.dispose();
});
it('keeps existing geometry while another tile is pending and adds only new geometry', async () => {
  mocks.post.mockRejectedValueOnce({response:{status:404}}).mockResolvedValueOnce(response([tile(1)]));
  const app = attachAppMap(map(), vi.fn()); await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  const original = mocks.created[0];
  mocks.tiles = [[16, 1, 1], [16, 2, 1]];
  let finish!: (data: any) => void;
  mocks.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = app.retry(); await flushPromises();
  expect(original.removed).toBe(false); expect(mocks.created).toHaveLength(1);
  finish(response([tile(2)])); await pending;
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  expect(original.removed).toBe(false);
  await app.retry(); expect(mocks.created).toHaveLength(2);
  app.dispose();
});
it('retains the loaded map when a new tile fails and prunes old tiles after replacement', async () => {
  mocks.post.mockRejectedValueOnce({response:{status:404}}).mockResolvedValueOnce(response([tile(1)]));
  const app = attachAppMap(map(), vi.fn()); await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  const original = mocks.created[0];
  mocks.tiles = [[16, 2, 1]]; mocks.post.mockRejectedValueOnce(new Error('offline'));
  await app.retry(); await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(3));
  expect(original.removed).toBe(false);
  mocks.post.mockResolvedValueOnce(response([tile(2)])); await app.retry();
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  expect(original.removed).toBe(true);
  app.dispose();
});
it('stops requesting tiles when the map session requires login', async () => {
  const report = vi.fn();
  mocks.post.mockResolvedValue({ status: 200, data: { status: 'need_login' } });
  const app = attachAppMap(map(), report);
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  await new Promise(resolve => setTimeout(resolve, 250));
  expect(mocks.post).toHaveBeenCalledTimes(1);
  expect(report).toHaveBeenCalledWith('TMC 登录已失效，请登录后重试地图');
  app.dispose();
});

it('does not switch to large JSON tiles after a temporary BMD gateway failure', async () => {
  mocks.post.mockRejectedValue({response:{status:502}});
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  await flushPromises();
  await new Promise(resolve => setTimeout(resolve, 250));
  expect(mocks.post).toHaveBeenCalledTimes(1);
  await app.retry();
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
  expect(mocks.post.mock.calls.map(call => call[0])).toEqual([
    '/api/amap-app/map/bmd', '/api/amap-app/map/bmd',
  ]);
  app.dispose();
});

it('keeps the compact BMD path when the 2D module Worker fails before ready', async () => {
  class StartupFailedWorker {
    onerror?: () => void;
    constructor() { queueMicrotask(() => this.onerror?.()); }
    terminate() {}
  }
  vi.stubGlobal('Worker', StartupFailedWorker);
  mocks.post.mockResolvedValue(response([tile(1)]));
  const app=attachAppMap(map(),vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  expect(mocks.post.mock.calls.map(call=>call[0])).toEqual(['/api/amap-app/map/bmd']);
  app.dispose();
});
