// @vitest-environment node
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it, vi } from 'vitest';

function setup() {
  const fetch = vi.fn();
  const self = { importScripts() {}, postMessage: vi.fn() };
  const context = vm.createContext({ self, fetch, AbortController, setTimeout, clearTimeout,
    Logger: class {}, kFileData: 2 });
  vm.runInContext(readFileSync(new URL('../../public/downloader.js', import.meta.url), 'utf8'), context);
  const downloader = (self as any).downloader;
  Object.assign(downloader, { sources: ['https://cdn.test/video', '/api/relay'], sourceIndex: 0 });
  return { downloader, fetch, self };
}
function range(start: number, end: number, total = 100, length = end - start + 1) {
  return new Response(new Uint8Array(length), { status: 206, headers: { 'Content-Range': `bytes ${start}-${end}/${total}` } });
}
it('keeps direct reads, then switches the failing range and subsequent seeks to relay', async () => {
  const { downloader: d, fetch } = setup();
  fetch.mockResolvedValueOnce(range(0, 0));
  expect((await d.readRange(0, 0)).total).toBe(100);
  expect(fetch.mock.calls[0][0]).toBe('https://cdn.test/video');
  fetch.mockRejectedValueOnce(new TypeError('CORS')).mockResolvedValueOnce(range(1, 4));
  expect((await d.readRange(1, 4)).data.byteLength).toBe(4);
  expect(fetch.mock.calls[1][1].headers.Range).toBe('bytes=1-4');
  expect(fetch.mock.calls[2][0]).toBe('/api/relay');
  expect(fetch.mock.calls[2][1].headers.Range).toBe('bytes=1-4');
  fetch.mockResolvedValueOnce(range(90, 99));
  await d.readRange(90, 99);
  expect(fetch.mock.calls[3][0]).toBe('/api/relay');
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', referrerPolicy: 'no-referrer', mode: 'cors' });
});
it.each(['403', 'wrong range', 'short body', 'long body', 'changed size'])('falls back on %s without feeding invalid data to the decoder', async reason => {
  const { downloader: d, fetch } = setup();
  d.sourceSize = 100;
  const bad = reason === '403' ? new Response('', { status: 403 }) :
    reason === 'wrong range' ? range(2, 5) : reason === 'short body' ? range(0, 3, 100, 2) :
    reason === 'long body' ? range(0, 3, 100, 5) : range(0, 3, 101);
  fetch.mockResolvedValueOnce(bad).mockResolvedValueOnce(range(0, 3));
  expect((await d.readRange(0, 3)).data.byteLength).toBe(4);
  expect(d.sourceIndex).toBe(1);
});
it('reports final range failure with its sequence instead of hanging', async () => {
  const { downloader: d, fetch, self } = setup();
  fetch.mockRejectedValue(new Error('offline'));
  d.downloadFileByHttp('unused', 0, 3, 7);
  await vi.waitFor(() => expect(self.postMessage).toHaveBeenCalledWith({ t: 2, q: 7, error: expect.any(String) }));
});
it('aborts a stalled CDN request before retrying the relay', async () => {
  vi.useFakeTimers();
  try {
    const { downloader: d, fetch } = setup();
    fetch.mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('timeout')));
    })).mockResolvedValueOnce(range(0, 0));
    const pending = d.readRange(0, 0);
    await vi.advanceTimersByTimeAsync(8000);
    expect((await pending).total).toBe(100);
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    expect(fetch.mock.calls[1][0]).toBe('/api/relay');
  } finally { vi.useRealTimers(); }
});
