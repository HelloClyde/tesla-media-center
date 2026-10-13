import { toRaw } from 'vue';
import { cumulative, type AppRoute, type Point } from './amapNavigation';

const DATABASE = 'tmc-amap-navigation-v1', STORE = 'navigation';
const MAX_AGE = 24 * 60 * 60 * 1000;
export interface NavigationRouteSession {
  id: string; routes: AppRoute[]; token: string;
  origin: Point; destination: Point; originName: string; destinationName: string;
}
export interface NavigationCheckpoint {
  id: string; updatedAt: number; mode: 'live' | 'demo'; selected: number; progress: number;
  use3D: boolean; muted: boolean; trafficEnabled: boolean; theme: 'day' | 'night';
}
export type SavedNavigation = { route: NavigationRouteSession; checkpoint: NavigationCheckpoint };
let opening: Promise<IDBDatabase | undefined> | undefined;
let writes = Promise.resolve(true);
let generation = 0;

function open() {
  if (opening) return opening;
  opening = new Promise(resolve => {
    if (typeof indexedDB === 'undefined') { resolve(undefined); return; }
    let settled = false;
    const finish = (db?: IDBDatabase) => {
      if (settled) { db?.close(); return; }
      settled = true; clearTimeout(timer); resolve(db);
    };
    const timer = setTimeout(() => finish(), 1500);
    try {
      const request = indexedDB.open(DATABASE, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => finish(request.result);
      request.onerror = request.onblocked = () => finish();
    } catch { finish(); }
  });
  return opening;
}
function complete(tx: IDBTransaction) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      try { tx.abort(); } catch { /* Already closed. */ }
      reject(new Error('navigation storage timeout'));
    }, 2000);
    tx.oncomplete = () => { clearTimeout(timer); resolve(); };
    tx.onerror = tx.onabort = () => { clearTimeout(timer); reject(tx.error); };
  });
}
// Strip Vue proxies only when the route changes, never on each GPS update.
function plain<T>(value: T): T {
  if (!value || typeof value !== 'object') return value;
  const raw = toRaw(value);
  return (Array.isArray(raw) ? raw.map(plain)
    : Object.fromEntries(Object.entries(raw).map(([key, item]) => [key, plain(item)]))) as T;
}
function write(action: (store: IDBObjectStore) => void, expected = generation, invalidateOnFailure = false) {
  const work = writes.then(async () => {
    const db = await open();
    if (!db || generation !== expected) return false;
    let success = false;
    try {
      const tx = db.transaction(STORE, 'readwrite'), done = complete(tx);
      try { action(tx.objectStore(STORE)); }
      catch { tx.abort(); await done.catch(() => {}); throw new Error('navigation write failed'); }
      await done; success = true;
    } catch { /* Failed storage must not interrupt navigation. */ }
    // A failed replacement must not resume a different, previously saved trip.
    // Keep cleanup inside the write queue so it cannot erase a later save.
    if (!success && invalidateOnFailure && generation === expected) {
      try {
        const tx = db.transaction(STORE, 'readwrite'), done = complete(tx);
        tx.objectStore(STORE).clear(); await done;
      } catch { /* The UI reports that persistence is unavailable. */ }
    }
    return success;
  });
  writes = work.catch(() => false);
  return writes;
}
export function saveNavigationSession(route: NavigationRouteSession, checkpoint: NavigationCheckpoint) {
  const snapshot = plain(route);
  return write(store => { store.put({ version: 1, ...snapshot }, 'route'); store.put({ ...checkpoint }, 'checkpoint'); }, generation, true);
}
export function saveNavigationCheckpoint(checkpoint: NavigationCheckpoint) {
  return write(store => store.put({ ...checkpoint }, 'checkpoint'));
}
export function clearNavigationSession() {
  const expected = ++generation;
  return write(store => store.clear(), expected);
}
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const point = (value: unknown): value is Point => Array.isArray(value) && value.length === 2
  && number(value[0]) && number(value[1]) && Math.abs(value[0]) <= 180 && Math.abs(value[1]) <= 85;
function validRoute(route: AppRoute) {
  return route && number(route.id) && number(route.distance) && route.distance >= 0
    && Array.isArray(route.path) && route.path.length >= 2 && route.path.length <= 200000 && route.path.every(point)
    && Array.isArray(route.breaks) && route.breaks.every(index => Number.isInteger(index) && index > 0 && index < route.path.length)
    && Array.isArray(route.labels) && route.labels.every(label => typeof label === 'string')
    && Array.isArray(route.steps) && route.steps.length > 0 && route.steps.every(step => step
      && Number.isInteger(step.start) && Number.isInteger(step.end) && step.start >= 0 && step.start <= step.end
      && step.end < route.path.length && typeof step.road === 'string');
}
export async function loadNavigationSession(): Promise<SavedNavigation | undefined> {
  await writes;
  const db = await open();
  if (!db) return;
  try {
    const tx = db.transaction(STORE, 'readonly'), done = complete(tx), store = tx.objectStore(STORE);
    const routeRequest = store.get('route'), checkpointRequest = store.get('checkpoint');
    await done;
    const route = routeRequest.result, checkpoint = checkpointRequest.result;
    if (!route && !checkpoint) return;
    if (route?.version !== 1 || typeof route.id !== 'string' || typeof route.token !== 'string'
      || !point(route.origin) || !point(route.destination) || typeof route.originName !== 'string' || typeof route.destinationName !== 'string'
      || !Array.isArray(route.routes) || !route.routes.length || route.routes.length > 10 || !route.routes.every(validRoute)
      || !checkpoint || checkpoint.id !== route.id || !number(checkpoint.updatedAt)
      || Date.now() - checkpoint.updatedAt > MAX_AGE || checkpoint.updatedAt > Date.now() + 60000
      || !['live', 'demo'].includes(checkpoint.mode) || !Number.isInteger(checkpoint.selected)
      || !route.routes[checkpoint.selected] || !number(checkpoint.progress) || checkpoint.progress < 0
      || !['use3D', 'muted', 'trafficEnabled'].every(key => typeof checkpoint[key] === 'boolean')
      || !['day', 'night'].includes(checkpoint.theme)) {
      await clearNavigationSession(); return;
    }
    const lengths = cumulative(route.routes[checkpoint.selected]);
    checkpoint.progress = Math.min(checkpoint.progress, lengths[lengths.length - 1]);
    return { route, checkpoint };
  } catch { return; }
}
