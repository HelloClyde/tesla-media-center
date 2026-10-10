import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {flushPromises} from '@vue/test-utils';
const mocks = vi.hoisted(() => ({post: vi.fn(), saved: new Map<string, any>(), reads: vi.fn(), memoryReads: vi.fn(), buildings: vi.fn(), contexts: new Map<number, any>()}));
vi.mock('axios', () => ({default: {post: mocks.post}}));
vi.mock('./amapViewport', () => ({viewportTiles: (zoom: number) => zoom <= 12 ? [[12, 1, 1], [3, 0, 0]] : [[14, 1, 1]], mapTileDistance: () => 0}));
vi.mock('./amapBrowserTileCache', () => ({
  browserMapTileTtlMs: () => 7 * 24 * 3600000,
  readMapTiles: mocks.reads,
  readMemoryMapTiles: mocks.memoryReads,
  storeMapTiles: vi.fn(async () => {}),
}));
vi.mock('./teslaBuildings', () => ({createBuildingMeshes: mocks.buildings}));
vi.mock('./teslaRoadLevels', () => ({roadSpans: () => [], roadDeckGeometry: vi.fn(), roadWidth: vi.fn(), nearestRoadHeight: () => 0}));
import { createTeslaMapGround } from './teslaMapGround';
import {groundPoint} from './teslaMapCoordinates';

const road = {level: 14, x: 1, y: 1, collection: {features: [
  {properties: {}, geometry: {type: 'LineString', coordinates: [[120.2, 30.2], [120.201, 30.2]]}},
]}};
beforeEach(() => {
  mocks.post.mockReset(); mocks.saved.clear(); mocks.reads.mockReset();
  mocks.memoryReads.mockReset(); mocks.memoryReads.mockReturnValue(new Map());
  mocks.buildings.mockReset(); mocks.buildings.mockReturnValue({count: 0, mesh: undefined});
  mocks.reads.mockImplementation(async (_kind: string, tiles: number[][]) =>
    new Map(tiles.flatMap(tile => mocks.saved.has(tile.join('/')) ? [[tile.join('/'), mocks.saved.get(tile.join('/'))]] : [])));
  mocks.contexts.clear();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function(this: HTMLCanvasElement) {
    const context = {fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), closePath: vi.fn(), fill: vi.fn()};
    mocks.contexts.set(this.width, context); return context as any;
  });
});
afterEach(() => vi.restoreAllMocks());

it('shows roads before a delayed building request completes', async () => {
  mocks.post.mockImplementation((_path: string, payload: {level: number; tiles: number[][]}) => payload.level === 15
    ? new Promise(() => {})
    : Promise.resolve({status: 200, data: {status: 'ok', data: {tiles: payload.level === 14 ? [road] : payload.tiles.map(([x,y]) => ({level: payload.level,x,y}))}}}));
  const report = vi.fn(), ground = createTeslaMapGround(report);
  ground.update([120.2, 30.2], 0, 0);
  await vi.waitFor(() => expect(mocks.post.mock.calls.some(call => call[1].level === 15)).toBe(true));
  expect(ground.group.visible).toBe(true);
  expect(report.mock.calls.some(call => call[1] === true)).toBe(true);
  expect(mocks.post.mock.calls.map(call => call[1].level)).toEqual([14,12,3,15]);
  expect(mocks.reads.mock.calls[0][1]).toEqual([[14,1,1]]);
  ground.dispose();
});
it('shows roads from the shared cache without waiting for any map response', async () => {
  mocks.saved.set('14/1/1', {tile: road, at: Date.now()});
  mocks.post.mockImplementation(() => new Promise(() => {}));
  const report = vi.fn(), ground = createTeslaMapGround(report);
  ground.update([120.2, 30.2], 0, 0);
  await vi.waitFor(() => expect(ground.group.visible).toBe(true));
  expect(mocks.post).toHaveBeenCalledTimes(1);
  expect(mocks.post.mock.calls[0][1].level).toBe(12);
  expect(report.mock.calls.some(call => call[1] === true)).toBe(true);
  ground.dispose();
});
it('paints roads beyond the local 600 m patch before a stalled building response', async () => {
  const center: [number, number] = [120.2,30.2];
  const outerRoad = {level: 12,x: 1,y: 1,collection: {features: [{properties: {},geometry: {
    type: 'LineString',coordinates: [groundPoint(center,700,-500),groundPoint(center,1000,-500)],
  }}]}};
  mocks.post.mockImplementation(async (_path: string, batch) => {
    if (batch.level === 15) return new Promise(() => {});
    return {status: 200,data: {status: 'ok',data: {tiles: batch.level === 14 ? [road] : batch.level === 12 ? [outerRoad]
      : batch.tiles.map(([x,y]: number[]) => ({level: batch.level,x,y}))}}};
  });
  const ground = createTeslaMapGround(vi.fn());
  ground.update(center,0,0);
  await vi.waitFor(() => expect(mocks.post.mock.calls.some(call => call[1].level === 15)).toBe(true));
  const backdrop = mocks.contexts.get(1024), detail = mocks.contexts.get(2048);
  const outerX = 512 + 700 * 1024 / 6000;
  expect(backdrop.moveTo.mock.calls.some(([x]: number[]) => Math.abs(x-outerX) < .01)).toBe(true);
  expect(detail.moveTo.mock.calls.every(([x]: number[]) => x >= 0 && x <= 2048)).toBe(true);
  expect(ground.group.visible).toBe(true);
  ground.dispose();
});
it('shows shared in-memory roads even while IndexedDB reads are blocked', () => {
  mocks.memoryReads.mockReturnValue(new Map([['14/1/1', {tile: road, at: Date.now()}]]));
  mocks.reads.mockImplementation(() => new Promise(() => {}));
  const ground = createTeslaMapGround(vi.fn());
  ground.update([120.2, 30.2], 0, 0);
  expect(ground.group.visible).toBe(true);
  expect(mocks.post).not.toHaveBeenCalled();
  ground.dispose();
});
it('shows a disk-cached road while decoding the other cached layers is blocked', async () => {
  mocks.reads.mockImplementation((_kind: string, keys: number[][]) => keys[0][0] === 14
    ? Promise.resolve(new Map([['14/1/1',{tile: road,at: Date.now()}]])) : new Promise(() => {}));
  const ground = createTeslaMapGround(vi.fn());
  ground.update([120.2,30.2],0,0);
  await vi.waitFor(() => expect(mocks.reads).toHaveBeenCalledTimes(2));
  expect(ground.group.visible).toBe(true);
  expect(mocks.post).not.toHaveBeenCalled();
  ground.dispose();
});
it('coalesces arriving map layers until a zoom/pinch gesture finishes', async () => {
  mocks.post.mockImplementation(async (_path, batch) => ({status: 200, data: {status: 'ok', data: {
    tiles: batch.level === 14 ? [road] : batch.tiles.map(([x, y]: number[]) => ({level: batch.level, x, y})),
  }}}));
  const ground = createTeslaMapGround(vi.fn());
  ground.setInteracting(true); ground.update([120.2, 30.2], 0, 0);
  await flushPromises();
  expect(mocks.post).toHaveBeenCalledTimes(1);
  expect(ground.revision()).toBe(0);
  expect(mocks.buildings).not.toHaveBeenCalled();
  ground.setInteracting(false);
  await vi.waitFor(() => expect(ground.group.visible).toBe(true));
  await vi.waitFor(() => expect(mocks.post.mock.calls.some(call => call[1].level === 3)).toBe(true));
  await flushPromises();
  expect(ground.revision()).toBe(1);
  expect(mocks.buildings).toHaveBeenCalledTimes(1);
  ground.setInteracting(false);
  expect(ground.revision()).toBe(1);
  ground.dispose();
});
it('discards a deferred map presentation when leaving the 3D page', () => {
  mocks.memoryReads.mockReturnValue(new Map([['14/1/1', {tile: road, at: Date.now()}]]));
  mocks.reads.mockImplementation(() => new Promise(() => {}));
  const ground = createTeslaMapGround(vi.fn());
  ground.setInteracting(true); ground.update([120.2, 30.2], 0, 0);
  ground.dispose(); ground.setInteracting(false);
  expect(mocks.buildings).not.toHaveBeenCalled();
});
it('keeps geographic alignment while deferring new geometry during manual panning', async () => {
  mocks.memoryReads.mockReturnValue(new Map([['14/1/1', {tile: road, at: Date.now()}]]));
  mocks.reads.mockImplementation(() => new Promise(() => {}));
  const ground = createTeslaMapGround(vi.fn()), center: [number, number] = [120.2, 30.2];
  ground.update(center, -180, 0);
  const revision = ground.revision();
  const roadRevision = ground.roadRevision();
  mocks.buildings.mockClear();
  ground.setInteracting(true);
  ground.update(groundPoint(center, 150, 40), -180, 0);
  expect(ground.group.position.x).toBeCloseTo(-150, 2);
  expect(ground.group.position.z).toBeCloseTo(-40, 2);
  expect(ground.revision()).toBe(revision);
  // A landmark arrival can suppress ordinary buildings; postpone that rebuild.
  ground.setLandmarkBounds([[120, 30.4, 120.4, 30]]);
  expect(mocks.buildings).not.toHaveBeenCalled();
  ground.setInteracting(false);
  expect(mocks.buildings).toHaveBeenCalledTimes(1);
  expect(ground.roadRevision()).toBe(roadRevision);
  ground.dispose();
});
