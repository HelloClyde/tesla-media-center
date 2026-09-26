// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { freshRadioBatch } from './qqMusicRadio';

describe('radio batch continuation', () => {
  it('skips repeated batches and deduplicates fresh songs', async () => {
    const fetch = vi.fn().mockResolvedValueOnce([{ mid: 'old' }])
      .mockResolvedValueOnce([{ mid: 'old' }, { mid: 'new' }, { mid: 'new' }]);
    expect(await freshRadioBatch(fetch, ['old'])).toEqual([{ mid: 'new' }]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('bounds retries when upstream repeats songs', async () => {
    const fetch = vi.fn().mockResolvedValue([{ mid: 'old' }]);
    expect(await freshRadioBatch(fetch, ['old'])).toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it('stops on empty batches and propagates request failures', async () => {
    const empty = vi.fn().mockResolvedValue([]);
    expect(await freshRadioBatch(empty, [])).toEqual([]);
    expect(empty).toHaveBeenCalledTimes(1);
    await expect(freshRadioBatch(() => Promise.reject(new Error('offline')), [])).rejects.toThrow('offline');
  });
});
