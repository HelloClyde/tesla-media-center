import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { reactive } from 'vue';
import { navigationSessionTestDb } from './navigationSessionTestDb';
import type { NavigationRouteSession, NavigationCheckpoint } from './amapNavigationSession';
let session: typeof import('./amapNavigationSession');
const database = navigationSessionTestDb();
const route = (): NavigationRouteSession => ({ id: 'trip', token: 'native-token', origin: [120,30], destination: [120,30.02],
  originName: '起点', destinationName: '终点', routes: [0,1,2].map(id => ({ id, path: [[120,30],[120,30.01],[120,30.02]],
    steps: [{ start:0,end:2,road:'测试路',maneuver:'straight' }], breaks:[], distance:2224, duration:240, labels:[],
    speedLimits: [{start:0,end:2200,limit:60}], trafficLights:[[120,30.01]], laneGuides:[], trafficRuns:[] })) });
const checkpoint = (): NavigationCheckpoint => ({ id:'trip', updatedAt:Date.now(), mode:'live', selected:2, progress:1000,
  use3D:true, muted:true, trafficEnabled:true, theme:'night' });
beforeEach(async () => {
  vi.resetModules(); database.reset(); vi.stubGlobal('indexedDB', database.indexedDB);
  session = await import('./amapNavigationSession');
});
afterEach(() => {vi.unstubAllGlobals(); vi.useRealTimers();});

it('saves complete routes and native indices without serializing Vue proxies', async () => {
  const source = reactive(route());
  const state = checkpoint();
  expect(await session.saveNavigationSession(source, state)).toBe(true);
  expect(await session.loadNavigationSession()).toEqual({ route:{version:1,...route()}, checkpoint:state });
});
it('updates a small progress checkpoint without rewriting route geometry', async () => {
  await session.saveNavigationSession(route(), checkpoint());
  await session.saveNavigationCheckpoint({...checkpoint(), progress:1400});
  expect(database.routeWrites).toBe(1);
  expect((await session.loadNavigationSession())?.checkpoint.progress).toBe(1400);
});
it('does not resurrect pending saves after explicitly clearing navigation', async () => {
  const writing = session.saveNavigationSession(route(), checkpoint());
  const clearing = session.clearNavigationSession();
  await Promise.all([writing,clearing]);
  expect(await session.loadNavigationSession()).toBeUndefined();
  expect(database.rows.size).toBe(0);
});
it.each([
  {selected:9}, {id:'other-route'}, {progress:NaN}, {progress:-1}, {mode:'idle'},
  {updatedAt:Date.now()-25*3600000}, {updatedAt:Date.now()+3600000},
])('rejects a corrupt or expired checkpoint %j', async change => {
  await session.saveNavigationSession(route(), {...checkpoint(), ...change} as NavigationCheckpoint);
  expect(await session.loadNavigationSession()).toBeUndefined();
  expect(database.rows.size).toBe(0);
});
it('rejects unusable route geometry rather than crashing guidance on reload', async () => {
  const source = route(); source.routes[2].steps[0].end = 2000;
  await session.saveNavigationSession(source, checkpoint());
  expect(await session.loadNavigationSession()).toBeUndefined();
});
it('bounds saved progress by the actual route length', async () => {
  await session.saveNavigationSession(route(), {...checkpoint(),progress:100000});
  expect((await session.loadNavigationSession())?.checkpoint.progress).toBeCloseTo(2223.9,0);
});
it('reports failed writes while leaving an already committed route usable', async () => {
  await session.saveNavigationSession(route(), checkpoint()); database.failNextWrite();
  expect(await session.saveNavigationCheckpoint({...checkpoint(),progress:2000})).toBe(false);
  expect((await session.loadNavigationSession())?.checkpoint.progress).toBe(1000);
});
it('does not resume a previous trip if persisting its replacement fails', async () => {
  await session.saveNavigationSession(route(), checkpoint()); database.failNextWrite();
  expect(await session.saveNavigationSession({...route(),id:'new-trip'}, {...checkpoint(),id:'new-trip'})).toBe(false);
  expect(await session.loadNavigationSession()).toBeUndefined();
});
it('handles browsers without IndexedDB without rejecting navigation', async () => {
  vi.stubGlobal('indexedDB',undefined);
  expect(await session.saveNavigationSession(route(),checkpoint())).toBe(false);
  expect(await session.loadNavigationSession()).toBeUndefined();
});
it('does not block startup forever when the browser never opens the database', async () => {
  vi.useFakeTimers(); vi.stubGlobal('indexedDB', {open: () => ({})});
  const loading = session.loadNavigationSession();
  await vi.advanceTimersByTimeAsync(1500);
  expect(await loading).toBeUndefined();
});
it('bounds a stalled database transaction during restoration', async () => {
  vi.useFakeTimers();
  const abort = vi.fn();
  vi.stubGlobal('indexedDB', {open: () => {
    const request: any = {result: {transaction: () => ({abort,objectStore: () => ({get: () => ({})})})}};
    queueMicrotask(() => request.onsuccess?.()); return request;
  }});
  const loading = session.loadNavigationSession();
  await vi.advanceTimersByTimeAsync(2000);
  expect(await loading).toBeUndefined(); expect(abort).toHaveBeenCalled();
});
