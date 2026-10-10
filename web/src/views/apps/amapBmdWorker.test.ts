import {afterEach, expect, it, vi} from 'vitest';
import {flushPromises} from '@vue/test-utils';
afterEach(() => vi.unstubAllGlobals());
it('requires an idle delivery grant even if a pause arrived during synchronous decoding', async () => {
  vi.resetModules(); vi.stubGlobal('CompressionStream', undefined);
  const scope = {postMessage: vi.fn(), onmessage: undefined as any};
  vi.stubGlobal('self', scope);
  await import('./amapBmdWorker');
  const tile = {level: 14, x: 1, y: 2, collection: {features: []}};
  scope.onmessage({data: {id: 1, operation: 'encode', payload: {tile}}});
  await flushPromises();
  expect(scope.postMessage).toHaveBeenCalledWith({id: 1, complete: true});
  expect(scope.postMessage.mock.calls.some(call => call[0].value)).toBe(false);
  scope.onmessage({data: {paused: true}});
  scope.onmessage({data: {deliver: 1}});
  expect(scope.postMessage.mock.calls.some(call => call[0].value)).toBe(false);
  scope.onmessage({data: {paused: false}});
  const result = scope.postMessage.mock.calls.find(call => call[0].value)![0];
  expect(JSON.parse(result.value.payload)).toEqual(tile);
});
it('parses old disk JSON in the worker and prepares geographic bounds before delivery', async () => {
  vi.resetModules();
  const scope = {postMessage: vi.fn(), onmessage: undefined as any}; vi.stubGlobal('self', scope);
  await import('./amapBmdWorker');
  scope.onmessage({data: {id: 2, operation: 'decode', payload: {encoding: 'json', payload: JSON.stringify({collection: {features: [
    {geometry: {coordinates: [[120, 30], [120.2, 29.8]]}},
  ]}})}}});
  await flushPromises(); scope.onmessage({data: {deliver: 2}});
  const result = scope.postMessage.mock.calls.find(call => call[0].value)![0];
  expect(result.value.collection.features[0].bbox).toEqual([120, 29.8, 120.2, 30]);
});
it('reuses a decoded BMD source for cache encoding and then releases that source', async () => {
  vi.resetModules(); vi.stubGlobal('CompressionStream', undefined);
  const scope = {postMessage: vi.fn(), onmessage: undefined as any}; vi.stubGlobal('self', scope);
  await import('./amapBmdWorker');
  scope.onmessage({data: {id: 3, operation: 'bmd', payload: {tiles: [{level: 14, x: 1, y: 2}], paints: {}, epoch: 5}}});
  await flushPromises(); scope.onmessage({data: {deliver: 3}});
  const decoded = scope.postMessage.mock.calls.find(call => call[0].id === 3 && call[0].value)![0].value;
  expect(decoded.sources).toEqual(['5/1']);
  scope.onmessage({data: {id: 4, operation: 'encode', payload: {source: '5/1'}}});
  await flushPromises(); scope.onmessage({data: {deliver: 4}});
  const encoded = scope.postMessage.mock.calls.find(call => call[0].id === 4 && call[0].value)![0].value;
  expect(JSON.parse(encoded.payload)).toMatchObject({level: 14, x: 1, y: 2});
  scope.onmessage({data: {id: 5, operation: 'encode', payload: {source: '5/1'}}});
  await flushPromises(); scope.onmessage({data: {deliver: 5}});
  expect(scope.postMessage.mock.calls.find(call => call[0].id === 5 && call[0].value)![0].value).toEqual({missingSource: true});
});
