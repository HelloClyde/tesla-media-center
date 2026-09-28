// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest';
import { NextTrackPreload, warmMediaRequest } from './qqMusicPreload';

function setup() {
  const warm = vi.fn(async (_url: string, _signal: AbortSignal) => {});
  const now = { value: 0 };
  return { warm, now, cache: new NextTrackPreload(warm, () => now.value) };
}

it('warms silently and reuses the resolved source including alternate CDNs', async () => {
  const { cache, warm } = setup();
  const resolve = vi.fn(async () => ({ url: '/one', urls: ['/one', '/two'] }));
  cache.prepare('song-quality-account', resolve);
  cache.prepare('song-quality-account', resolve);
  const lease = cache.take('song-quality-account')!;
  expect(await lease.result).toEqual({ url: '/one', urls: ['/one', '/two'] });
  expect(resolve).toHaveBeenCalledTimes(1);
  expect(warm).toHaveBeenCalledWith('/one', expect.any(AbortSignal));
  const signal = warm.mock.calls[0][1];
  expect(signal.aborted).toBe(false);
  lease.release();
  expect(signal.aborted).toBe(true);
});

it('does not load stale results after invalidation', async () => {
  const { cache, warm } = setup();
  let complete!: (value: { url: string }) => void;
  const pending = new Promise<{ url: string }>(resolve => { complete = resolve; });
  cache.prepare('old', () => pending);
  await Promise.resolve();
  cache.clear();
  complete({ url: '/old' });
  await pending;
  await Promise.resolve();
  expect(warm).not.toHaveBeenCalled();
  expect(cache.take('old')).toBeUndefined();
});

it('drops old quality/account sources and expires signed URLs', () => {
  const { cache, now } = setup();
  cache.prepare('standard', async () => ({ url: '/old' }));
  expect(cache.take('lossless')).toBeUndefined();
  cache.prepare('new', async () => ({ url: '/new' }));
  now.value = 120001;
  expect(cache.take('new')).toBeUndefined();
});

it('returns an empty result on failure so foreground playback can retry normally', async () => {
  const { cache, warm } = setup();
  cache.prepare('denied', async () => { throw new Error('VIP required'); });
  const lease = cache.take('denied')!;
  expect(await lease.result).toBeUndefined();
  expect(warm).not.toHaveBeenCalled();
  lease.release();
});

it('releases a pending foreground lease without starting stale media loading', async () => {
  const { cache, warm } = setup();
  cache.prepare('song', async () => ({ url: '/song' }));
  const lease = cache.take('song')!;
  lease.release();
  expect(await lease.result).toBeUndefined();
  expect(warm).not.toHaveBeenCalled();
});


afterEach(() => vi.unstubAllGlobals());

it('keeps the resolved URL usable when CDN CORS blocks warming', async () => {
  const cache = new NextTrackPreload(async () => { throw new TypeError('Failed to fetch'); });
  cache.prepare('song', async () => ({ url: '/song' }));
  const lease = cache.take('song')!;
  expect(await lease.result).toEqual({ url: '/song' });
  lease.release();
});

it('bounds network warming even when the server ignores Range', async () => {
  const cancel = vi.fn(async () => {});
  const read = vi.fn(async () => ({ done: false, value: new Uint8Array(128 * 1024) }));
  const fetchMock = vi.fn(async () => ({ ok: true, body: { getReader: () => ({ read, cancel }) } }));
  vi.stubGlobal('fetch', fetchMock);
  const signal = new AbortController().signal;
  await warmMediaRequest('/song', signal);
  expect(fetchMock).toHaveBeenCalledWith('/song', { signal, headers: { Range: 'bytes=0-262143' } });
  expect(read).toHaveBeenCalledTimes(2);
  expect(cancel).toHaveBeenCalledTimes(1);
});
