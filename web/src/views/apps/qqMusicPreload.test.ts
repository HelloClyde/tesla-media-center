// @vitest-environment node
import { expect, it, vi } from 'vitest';
import { NextTrackPreload } from './qqMusicPreload';

function setup() {
  const audio = { preload: '' as HTMLAudioElement['preload'], muted: false, crossOrigin: null as string | null, src: '',
    load: vi.fn(), pause: vi.fn(), removeAttribute: vi.fn(), play: vi.fn() };
  const create = vi.fn(() => audio);
  const now = { value: 0 };
  return { audio, create, now, cache: new NextTrackPreload(create, () => now.value) };
}

it('warms silently and reuses the resolved source including alternate CDNs', async () => {
  const { cache, audio } = setup();
  const resolve = vi.fn(async () => ({ url: '/one', urls: ['/one', '/two'] }));
  cache.prepare('song-quality-account', resolve, true);
  cache.prepare('song-quality-account', resolve, true);
  const lease = cache.take('song-quality-account')!;
  expect(await lease.result).toEqual({ url: '/one', urls: ['/one', '/two'] });
  expect(resolve).toHaveBeenCalledTimes(1);
  expect(audio.src).toBe('/one');
  expect(audio.crossOrigin).toBe('anonymous');
  expect(audio.preload).toBe('auto');
  expect(audio.muted).toBe(true);
  expect(audio.play).not.toHaveBeenCalled();
  lease.release();
  expect(audio.removeAttribute).toHaveBeenCalledWith('src');
});

it('does not load stale results after invalidation', async () => {
  const { cache, create } = setup();
  let complete!: (value: { url: string }) => void;
  const pending = new Promise<{ url: string }>(resolve => { complete = resolve; });
  cache.prepare('old', () => pending, false);
  await Promise.resolve();
  cache.clear();
  complete({ url: '/old' });
  await pending;
  await Promise.resolve();
  expect(create).not.toHaveBeenCalled();
  expect(cache.take('old')).toBeUndefined();
});

it('drops old quality/account sources and expires signed URLs', () => {
  const { cache, now } = setup();
  cache.prepare('standard', async () => ({ url: '/old' }), false);
  expect(cache.take('lossless')).toBeUndefined();
  cache.prepare('new', async () => ({ url: '/new' }), false);
  now.value = 120001;
  expect(cache.take('new')).toBeUndefined();
});

it('returns an empty result on failure so foreground playback can retry normally', async () => {
  const { cache, create } = setup();
  cache.prepare('denied', async () => { throw new Error('VIP required'); }, false);
  const lease = cache.take('denied')!;
  expect(await lease.result).toBeUndefined();
  expect(create).not.toHaveBeenCalled();
  lease.release();
});

it('releases a pending foreground lease without starting stale media loading', async () => {
  const { cache, create } = setup();
  cache.prepare('song', async () => ({ url: '/song' }), false);
  const lease = cache.take('song')!;
  lease.release();
  expect(await lease.result).toBeUndefined();
  expect(create).not.toHaveBeenCalled();
});
