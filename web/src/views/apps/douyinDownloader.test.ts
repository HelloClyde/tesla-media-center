// @vitest-environment node
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';

it('serves file info and the first chunk from prefetched bytes without a second request', async () => {
  const code = readFileSync(new URL('../../../public/downloader.js', import.meta.url), 'utf8');
  const fetchMock = vi.fn(async () => ({
    status: 206,
    headers: new Headers({ 'Content-Range': 'bytes 1024-2047/2048' }),
    body: new Response(new Uint8Array(1024)).body,
  }));
  const self = { importScripts: () => {}, postMessage: () => {}, location: { search: '' }, downloader: null as any };
  runInNewContext(code, { self, Logger: class {}, fetch: fetchMock, AbortController,
    setTimeout, clearTimeout, console, Uint8Array, ArrayBuffer, Number, Error, TypeError });
  const downloader = self.downloader;
  downloader.sources = ['/api/douyin/media/token'];
  downloader.sourceIndex = 0;
  downloader.sourceSize = 2048;
  downloader.prefetchedRange = { data: new Uint8Array(1024).fill(7).buffer, total: 2048 };

  expect((await downloader.readRange(0, 0)).data.byteLength).toBe(1);
  expect(new Uint8Array((await downloader.readRange(0, 1023)).data)[1023]).toBe(7);
  expect(fetchMock).not.toHaveBeenCalled();
  expect((await downloader.readRange(1024, 2047)).data.byteLength).toBe(1024);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(downloader.prefetchedRange).toBeNull();
});
