import {decodeBmdOnMainThread, TransientBmdDecodeError, transferableBmdBuffers} from './amapBmdTransport';
import {encodeMapTile, decodeCachedMapTile, type EncodedMapTile} from './amapTileCodec';
import {waitForMapIdle, watchMapInteraction} from './amapMapWork';
import type {RawMapTile} from './amapBmdDecode';

type Operation = 'bmd' | 'encode' | 'decode';
let worker: Worker | undefined, starting: Promise<Worker | undefined> | undefined, unavailable = false;
let nextId = 0, workerEpoch = 0;
const jobs = new Map<number, {resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>}>();
const tileSources = new WeakMap<object, string>();
function stop() {
  worker?.terminate(); worker = undefined; starting = undefined;
  for (const job of jobs.values()) { clearTimeout(job.timer); job.reject(new TransientBmdDecodeError('map worker failed')); }
  jobs.clear();
}
watchMapInteraction(paused => worker?.postMessage({paused}));
function getWorker() {
  if (starting) return starting;
  if (unavailable || typeof Worker === 'undefined') return Promise.resolve(undefined);
  starting = new Promise<Worker | undefined>(resolve => {
    let ready = false;
    const failed = () => { clearTimeout(timer); unavailable = true; stop(); if (!ready) resolve(undefined); };
    const timer = setTimeout(failed, 1200);
    try { worker = new Worker(new URL('./amapBmdWorker.ts', import.meta.url), {type: 'module'}); workerEpoch++; }
    catch { failed(); return; }
    worker.onerror = failed;
    worker.onmessage = event => {
      if (event.data.ready) { ready = true; clearTimeout(timer); resolve(worker); return; }
      const job = jobs.get(event.data.id);
      if (!job) return;
      // A small completion notification stops the decode deadline. The large
      // object stays in the worker while input is active, however long it lasts.
      clearTimeout(job.timer);
      if (event.data.complete) {
        void waitForMapIdle().then(() => {
          if (jobs.get(event.data.id) === job) worker?.postMessage({deliver: event.data.id});
        });
        return;
      }
      jobs.delete(event.data.id);
      if (event.data.error) job.reject(new Error(event.data.error));
      else job.resolve(event.data.value);
    };
  });
  return starting;
}
async function run(operation: Operation, payload: any, fallback: () => Promise<any> | any, transfers: Transferable[] = []) {
  await waitForMapIdle();
  const target = await getWorker();
  await waitForMapIdle();
  if (!target || target !== worker) return fallback();
  return new Promise<any>((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => stop(), 30000);
    jobs.set(id, {resolve, reject, timer});
    try { target.postMessage({id, operation, payload: operation === 'bmd' ? {...payload, epoch: workerEpoch} : payload}, transfers); }
    catch { jobs.delete(id); clearTimeout(timer); unavailable = true; stop(); resolve(fallback()); }
  });
}
export async function decodeAppMapTiles(tiles: RawMapTile[], paints: Record<string, Record<string, any[]>>): Promise<any[]> {
  const result = await run('bmd', {tiles, paints}, () => decodeBmdOnMainThread(tiles, paints), transferableBmdBuffers(tiles));
  if (Array.isArray(result)) return result;
  for (let i = 0; i < result.tiles.length; i++) tileSources.set(result.tiles[i], result.sources[i]);
  return result.tiles;
}
export async function encodeBrowserMapTile(tile: object): Promise<EncodedMapTile> {
  const source = tileSources.get(tile);
  // The BMD decoder already owns this large object. Reuse that reference in
  // the same worker instead of structured-cloning it back from the UI thread.
  if (source !== undefined) {
    const encoded = await run('encode', {source}, () => encodeMapTile(tile));
    if (!encoded.missingSource) return encoded;
  }
  return run('encode', {tile}, () => encodeMapTile(tile));
}
export function decodeBrowserMapTile(row: {payload: string | Uint8Array; encoding: string}): Promise<any> {
  // IDB owns the cached bytes: no transfer/detach of the in-memory row.
  return run('decode', row, () => decodeCachedMapTile(row));
}
