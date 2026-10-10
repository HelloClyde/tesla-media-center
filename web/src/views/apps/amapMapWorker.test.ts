import {afterEach, beforeEach, expect, it, vi} from 'vitest';
const workers: FakeWorker[] = [];
class FakeWorker {
  onmessage?: (event: any) => void;
  onerror?: () => void;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() { workers.push(this); queueMicrotask(() => this.onmessage?.({data: {ready: true}})); }
}
beforeEach(() => { vi.resetModules(); vi.useFakeTimers(); workers.length = 0; vi.stubGlobal('Worker', FakeWorker); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
it('keeps serialization out of the input task and uses a reusable worker', async () => {
  const {createMapInteraction} = await import('./amapMapWork');
  const {encodeBrowserMapTile} = await import('./amapMapWorker');
  const input = createMapInteraction(); input.set(true);
  const work = encodeBrowserMapTile({level: 14});
  await vi.advanceTimersByTimeAsync(0); expect(workers).toHaveLength(0);
  input.set(false); await vi.advanceTimersByTimeAsync(140);
  const worker = workers[0], job = worker.postMessage.mock.calls.find(call => call[0].operation === 'encode')![0];
  worker.onmessage!({data: {id: job.id, complete: true}});
  await vi.advanceTimersByTimeAsync(0);
  expect(worker.postMessage).toHaveBeenCalledWith({deliver: job.id});
  worker.onmessage!({data: {id: job.id, value: {encoding: 'json', payload: '{}', bytes: 2}}});
  expect(await work).toMatchObject({bytes: 2});
  const next = encodeBrowserMapTile({level: 15}); await vi.advanceTimersByTimeAsync(0);
  expect(workers).toHaveLength(1);
  const nextJob = worker.postMessage.mock.calls.filter(call => call[0].operation === 'encode')[1][0];
  worker.onmessage!({data: {id: nextJob.id, value: {encoding: 'json', payload: '{}', bytes: 2}}});
  await next; input.dispose();
});
it('holds a completed large reply while a gesture starts during decoding', async () => {
  const {createMapInteraction} = await import('./amapMapWork');
  const {decodeBrowserMapTile} = await import('./amapMapWorker');
  const input = createMapInteraction();
  const work = decodeBrowserMapTile({payload: '{}', encoding: 'json'});
  await vi.advanceTimersByTimeAsync(0);
  const worker = workers[0], job = worker.postMessage.mock.calls.find(call => call[0].operation === 'decode')![0];
  input.set(true);
  worker.onmessage!({data: {id: job.id, complete: true}});
  await vi.advanceTimersByTimeAsync(31000);
  expect(worker.terminate).not.toHaveBeenCalled();
  expect(worker.postMessage.mock.calls.some(call => call[0].deliver)).toBe(false);
  input.set(false); await vi.advanceTimersByTimeAsync(140);
  expect(worker.postMessage).toHaveBeenCalledWith({deliver: job.id});
  worker.onmessage!({data: {id: job.id, value: {level: 14}}});
  expect(await work).toMatchObject({level: 14}); input.dispose();
});
it('persists newly decoded BMD without cloning its geometry back to the worker', async () => {
  const {decodeAppMapTiles, encodeBrowserMapTile} = await import('./amapMapWorker');
  const decoding = decodeAppMapTiles([], {}); await vi.advanceTimersByTimeAsync(0);
  const worker = workers[0], job = worker.postMessage.mock.calls.find(call => call[0].operation === 'bmd')![0];
  const tile = {level: 14, x: 1, y: 2, collection: {features: []}};
  worker.onmessage!({data: {id: job.id, value: {tiles: [tile], sources: ['1/42']}}});
  const decoded = await decoding;
  const encoding = encodeBrowserMapTile(decoded[0]); await vi.advanceTimersByTimeAsync(0);
  const cacheJob = worker.postMessage.mock.calls.find(call => call[0].operation === 'encode')![0];
  expect(cacheJob.payload).toEqual({source: '1/42'});
  worker.onmessage!({data: {id: cacheJob.id, value: {encoding: 'json', payload: '{}', bytes: 2}}});
  await encoding;
});
