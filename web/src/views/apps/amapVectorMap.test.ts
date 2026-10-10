import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
const mocks = vi.hoisted(() => ({ zoom: 16, tiles: [[16, 1, 1]], post: vi.fn(), created: [] as any[], saved: new Map<string, any>(), handlers: new Map<string, () => void>() }));
vi.mock('axios', () => ({ default: { post: mocks.post } }));
vi.mock('./amapBrowserTileCache', () => ({
  browserMapTileTtlMs: () => 7*24*3600000,
  readMemoryMapTiles: () => new Map(),
  readMapTiles: vi.fn(async (kind: string, tiles: number[][]) => kind === 'full'
    ? new Map(tiles.map(tile => [tile.join('/'), mocks.saved.get(tile.join('/'))] as const).filter(entry => entry[1]))
    : new Map()),
  storeMapTiles: vi.fn(async () => undefined),
}));
vi.mock('./amapViewport', async importOriginal => ({
  ...await importOriginal<typeof import('./amapViewport')>(), viewportTiles: () => mocks.tiles,
}));
vi.mock('./mapRenderQueue', () => ({ createMapRenderQueue: () => ({ start: (work: Iterator<void>) => { while (!work.next().done) {} }, cancel: () => {} }) }));
vi.mock('leaflet', () => {
  const layer = (_data?: any, options?: any) => {
    const result = { data: _data, options, removed: false,
      setStyle: vi.fn((style: any) => { Object.assign(options.style || options, style); }),
      addTo(group: any) { group.addLayer?.(result); return result; }, remove() { result.removed = true; } };
    mocks.created.push(result); return result;
  };
  return { default: {
    canvas: () => ({ remove() {} }),
    layerGroup: () => ({ addTo() { return this; }, addLayer() {}, clearLayers() {}, removeLayer(item: any) { item.removed = true; }, remove() {} }),
    geoJSON: layer, polygon: layer, marker: layer, divIcon: (x: any) => x,
  } };
});
import { attachAppMap } from './amapVectorMap';
import { waitForMapIdle } from './amapMapWork';
const tile = (x: number) => ({ level: 16, x, y: 1, collection: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { style: 18 << 5, name: '' }, geometry: { type: 'LineString', coordinates: [[116, 39], [116.1, 39]] } }] } });
const response = (tiles: any[]) => ({ status: 200, data: { status: 'ok', data: { tiles } } });
const map = () => ({ getPane: () => undefined, createPane: () => ({ style: {} }), getZoom: () => mocks.zoom,
  getCenter: () => ({ lng: 116.5, lat: 39.5 }),
  getBounds: () => ({ getWest: () => 116, getEast: () => 117, getNorth: () => 40, getSouth: () => 39 }),
  getSize: () => ({ x: 800, y: 600 }), on(events: string, handler: () => void) { events.split(' ').forEach(event => mocks.handlers.set(event, handler)); }, off() {},
}) as any;
beforeEach(() => { mocks.created.length = 0; mocks.saved.clear(); mocks.handlers.clear(); mocks.zoom = 16; mocks.tiles = [[16, 1, 1]]; mocks.post.mockReset(); });
afterEach(() => vi.unstubAllGlobals());
it('does not block 3D loading when the inactive 2D map follows its centre and zoom', async () => {
  mocks.post.mockImplementation(() => new Promise(() => {}));
  const app = attachAppMap(map(), vi.fn());
  try {
    app.setFollowing(false);
    app.setActive(false);
    // The 3D view keeps the hidden Leaflet map in sync. Those programmatic
    // movements must not acquire the interaction gate used by both views.
    for (const event of ['movestart', 'moveend', 'zoomstart', 'zoomend'])
      mocks.handlers.get(event)!();
    let ready = false;
    void waitForMapIdle().then(() => { ready = true; });
    await vi.waitFor(() => expect(ready).toBe(true), { timeout: 500 });
  } finally {
    app.dispose();
  }
});
it('releases an unfinished 2D gesture on switching to 3D and can load 2D again', async () => {
  mocks.tiles = [[3, 1, 1]];
  mocks.post.mockImplementation((_url, _payload, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  }));
  const app = attachAppMap(map(), vi.fn());
  try {
    await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    mocks.handlers.get('zoomstart')!();
    let ready = false;
    void waitForMapIdle().then(() => { ready = true; });
    await flushPromises();
    expect(ready).toBe(false);
    app.setActive(false);
    mocks.handlers.get('movestart')!();
    mocks.handlers.get('moveend')!();
    await vi.waitFor(() => expect(ready).toBe(true), { timeout: 500 });
    mocks.post.mockResolvedValue(response([{ ...tile(1), level: 3 }]));
    // Allow the aborted request to finish its bookkeeping before 2D resumes.
    await flushPromises();
    mocks.handlers.get('zoomstart')!();
    app.setActive(true);
    await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  } finally {
    app.dispose();
  }
});
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
it('culls off-screen roads and refreshes them when panning within the same source tile', async () => {
  mocks.tiles = [[3, 1, 1]];
  const data = {...tile(1), level: 3};
  const distant = {...data.collection.features[0], geometry: {type: 'LineString', coordinates: [[118, 39], [118.1, 39]]}};
  data.collection.features.push(distant);
  mocks.saved.set('3/1/1', {tile: data, at: Date.now()});
  for (const [x,y] of [[1,0],[2,1],[1,2],[0,1],[0,0],[2,0],[2,2],[0,2]])
    mocks.saved.set(`3/${x}/${y}`, {tile: {level: 3, x, y, collection: {features: []}}, at: Date.now()});
  const view = map(); let west = 116;
  view.getBounds = () => ({getWest: () => west, getEast: () => west + 1, getSouth: () => 39, getNorth: () => 40});
  const app = attachAppMap(view, vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  await flushPromises();
  expect(mocks.post).not.toHaveBeenCalled();
  const original = mocks.created[0];
  west = 118; mocks.handlers.get('moveend')!();
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  expect(mocks.created[1].data).toBe(distant);
  expect(original.removed).toBe(true);
  app.dispose();
});
it('pauses drawing immediately on wheel input before Leaflet starts its delayed zoom', async () => {
  mocks.tiles = [[3, 1, 1]];
  let finish!: (data: any) => void;
  mocks.post.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  const container = document.createElement('div'), view = map(); view.getContainer = () => container;
  const app = attachAppMap(view, vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  container.dispatchEvent(new WheelEvent('wheel'));
  finish(response([{...tile(1), level: 3}])); await flushPromises();
  expect(mocks.created).toHaveLength(0);
  // At a zoom bound Leaflet might never emit zoomstart/zoomend. The input
  // quiet timer must still resume the map instead of leaving it paused.
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  app.dispose();
});
it('keeps an overlapping wheel and two-pointer drag paused until both pointers lift', async () => {
  mocks.tiles = [[3, 1, 1]];
  let finish!: (data: any) => void;
  mocks.post.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  const container = document.createElement('div'), view = map(); view.getContainer = () => container;
  const app = attachAppMap(view, vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  const pointer = (type: string, id: number) => {const event = new Event(type); Object.defineProperty(event, 'pointerId', {value: id}); return event;};
  container.dispatchEvent(pointer('pointerdown', 1)); container.dispatchEvent(pointer('pointerdown', 2));
  container.dispatchEvent(new WheelEvent('wheel'));
  finish(response([{...tile(1), level: 3}]));
  await new Promise(resolve => setTimeout(resolve, 220));
  expect(mocks.created).toHaveLength(0);
  window.dispatchEvent(pointer('pointerup', 1)); await flushPromises();
  expect(mocks.created).toHaveLength(0);
  window.dispatchEvent(pointer('pointerup', 2));
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  app.dispose();
});
it('loads current street detail before waiting on distant overview layers', async () => {
  mocks.tiles = [[3, 0, 0], [6, 1, 1], [14, 1, 1]];
  mocks.post.mockImplementation(() => new Promise(() => {}));
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  expect(mocks.post.mock.calls[0][1]).toEqual({level: 14, tiles: [[1, 1]]});
  app.dispose();
});
it('limits the first visible batch and places the view-centre tile first', async () => {
  const x = Math.floor((116.5 + 180) / 360 * 2 ** 14);
  const y = Math.floor((90 - 39.5) / 180 * 2 ** 14);
  mocks.tiles = Array.from({length: 10}, (_, index) => [14, x + 9 - index, y]);
  mocks.post.mockImplementation(() => new Promise(() => {}));
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  expect(mocks.post.mock.calls[0][1].tiles).toHaveLength(4);
  expect(mocks.post.mock.calls[0][1].tiles[0]).toEqual([x, y]);
  app.dispose();
});
it('restores cached tiles again after leaving and re-entering the map page', async () => {
  mocks.tiles = [[3, 1, 1]];
  mocks.saved.set('3/1/1', {tile: {...tile(1), level: 3}, at: Date.now()});
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
  app.setActive(false); app.releaseMemory(); app.setActive(true);
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  expect(mocks.post).not.toHaveBeenCalled();
  app.dispose();
});
it('interrupts background prefetch when navigation changes to a missing viewport', async () => {
  let backgroundSignal: AbortSignal | undefined;
  mocks.post.mockResolvedValueOnce(response([tile(1)]))
    .mockImplementationOnce((_path, _payload, options) => new Promise((_resolve, reject) => {
      backgroundSignal = options.signal;
      backgroundSignal!.addEventListener('abort', () => reject(new Error('cancelled')));
    }))
    .mockImplementationOnce(() => new Promise(() => {}));
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(backgroundSignal).toBeDefined());
  app.setFollowing(true);
  const coordinates = mocks.post.mock.calls[1][1].tiles[0];
  // The cancelled prefetch tile immediately becomes visible. Cancellation is
  // not a failure and must not put this newly needed tile in retry backoff.
  mocks.tiles = [[16, ...coordinates]];
  mocks.handlers.get('zoomstart')!(); mocks.handlers.get('zoomend')!();
  expect(backgroundSignal!.aborted).toBe(true);
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(3));
  expect(mocks.post.mock.calls[2][1].tiles).toEqual([coordinates]);
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
  expect(mocks.created.map(layer => layer.options.pane)).toEqual(['appRoads', 'appRoadFills']);
  app.dispose();
});
it('reuses road and surface geometry on zoom, updating only changed paint including opacity', async () => {
  mocks.tiles = [[3, 1, 1]];
  const data: any = {...tile(1), level: 3};
  data.collection.features[0].properties.paintKey = 'road';
  const paint = {minZoom: 16, maxZoom: 16, outerWidth: 40, innerWidth: 30,
    outer: {color: '#abc', opacity: 1}, inner: {color: '#fff', opacity: 1}};
  data.roadPaints = {day: {road: [paint, {...paint, minZoom: 17, maxZoom: 18,
    outerWidth: 50, inner: {...paint.inner, opacity: .5}}]}};
  data.surfaces = [{minZoom: 3, maxZoom: 18, rings: [[[116, 39], [116.1, 39], [116.1, 39.1]]],
    paints: {day: [{minZoom: 3, maxZoom: 18, color: '#ddd', opacity: .8}]}}];
  mocks.saved.set('3/1/1', {tile: data, at: Date.now()});
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(3));
  const [surface, casing, fill] = mocks.created;
  mocks.handlers.get('zoomstart')!(); mocks.zoom = 17; mocks.handlers.get('zoomend')!();
  await vi.waitFor(() => expect(casing.options.style.weight).toBe(5));
  expect(fill.options.style.opacity).toBe(.5);
  expect(mocks.created).toHaveLength(3);
  expect(mocks.created.every(layer => !layer.removed)).toBe(true);
  expect(surface.setStyle).not.toHaveBeenCalled();
  app.dispose();
});
it('keeps source feature identity when another road disappears at a zoom boundary', async () => {
  mocks.tiles = [[3, 1, 1]];
  const data = {...tile(1), level: 3};
  const retained = data.collection.features[0];
  data.collection.features.unshift({...retained, properties: {style: 16 << 5, name: ''}});
  mocks.saved.set('3/1/1', {tile: data, at: Date.now()});
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.created).toHaveLength(2));
  const original = mocks.created.find(layer => layer.data === retained);
  mocks.handlers.get('zoomstart')!(); mocks.zoom = 17; mocks.handlers.get('zoomend')!();
  await vi.waitFor(() => expect(mocks.created[0].removed).toBe(true));
  expect(original.removed).toBe(false);
  expect(mocks.created).toHaveLength(2);
  app.dispose();
});
it('does not draw an arriving tile or start new downloads during a followed zoom gesture', async () => {
  mocks.tiles = [[3, 1, 1]];
  let finish!: (data: any) => void;
  mocks.post.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  const app = attachAppMap(map(), vi.fn());
  await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  app.setFollowing(true); mocks.handlers.get('zoomstart')!();
  finish(response([{...tile(1), level: 3}])); await flushPromises();
  // moveend can arrive before zoomend; it must not restart drawing early.
  mocks.handlers.get('moveend')!();
  await new Promise(resolve => setTimeout(resolve, 200));
  expect(mocks.created).toHaveLength(0);
  expect(mocks.post).toHaveBeenCalledTimes(1);
  mocks.handlers.get('zoomend')!();
  await vi.waitFor(() => expect(mocks.created).toHaveLength(1));
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
