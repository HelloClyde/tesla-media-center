import { beforeEach, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
const mocks = vi.hoisted(() => ({ tiles: [[16, 1, 1]], post: vi.fn(), created: [] as any[] }));
vi.mock('axios', () => ({ default: { post: mocks.post } }));
vi.mock('./amapViewport', () => ({ viewportTiles: () => mocks.tiles }));
vi.mock('./mapRenderQueue', () => ({ createMapRenderQueue: () => ({ start: (work: Iterator<void>) => { while (!work.next().done) {} }, cancel: () => {} }) }));
vi.mock('leaflet', () => {
  const layer = () => {
    const result = { removed: false, addTo(group: any) { group.addLayer?.(result); return result; }, remove() { result.removed = true; } };
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
beforeEach(() => { mocks.created.length = 0; mocks.tiles = [[16, 1, 1]]; mocks.post.mockReset(); });
it('keeps existing geometry while another tile is pending and adds only new geometry', async () => {
  mocks.post.mockResolvedValueOnce(response([tile(1)]));
  const app = attachAppMap(map(), vi.fn()); await flushPromises();
  const original = mocks.created[0]; expect(mocks.created).toHaveLength(1);
  mocks.tiles = [[16, 1, 1], [16, 2, 1]];
  let finish!: (data: any) => void;
  mocks.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = app.retry(); await flushPromises();
  expect(original.removed).toBe(false); expect(mocks.created).toHaveLength(1);
  finish(response([tile(2)])); await pending;
  expect(original.removed).toBe(false); expect(mocks.created).toHaveLength(2);
  await app.retry(); expect(mocks.created).toHaveLength(2);
  app.dispose();
});
it('retains the loaded map when a new tile fails and prunes old tiles after replacement', async () => {
  mocks.post.mockResolvedValueOnce(response([tile(1)]));
  const app = attachAppMap(map(), vi.fn()); await flushPromises();
  const original = mocks.created[0];
  mocks.tiles = [[16, 2, 1]]; mocks.post.mockRejectedValueOnce(new Error('offline'));
  await app.retry(); expect(original.removed).toBe(false);
  mocks.post.mockResolvedValueOnce(response([tile(2)])); await app.retry();
  expect(original.removed).toBe(true); expect(mocks.created).toHaveLength(2);
  app.dispose();
});
