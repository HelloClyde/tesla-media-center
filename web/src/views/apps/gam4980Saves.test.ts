import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { readSave, uploadSave } from './gam4980Saves';

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());
const key = 'tmc:gam4980:save:100-1-2';
const ok = () => new Response(JSON.stringify({ status: 'ok' }));
describe('server GAM saves', () => {
  it('migrates a browser save only when no server save exists', async () => {
    localStorage.setItem(key, btoa('\x03'.repeat(0x14000)));
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 404 })).mockResolvedValueOnce(ok());
    vi.stubGlobal('fetch', fetcher);
    expect((await readSave(key))?.[0]).toBe(3);
    expect(fetcher.mock.calls[1][1].method).toBe('PUT');
    expect(localStorage.getItem(key + ':pending')).toBeNull();
  });
  it('does not treat an unavailable server as an empty save', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 503 }));
    vi.stubGlobal('fetch', fetcher);
    await expect(readSave(key)).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('retains failed writes and retries the local snapshot before loading', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(Error('offline')).mockResolvedValueOnce(ok());
    vi.stubGlobal('fetch', fetcher);
    await expect(uploadSave(key, new Uint8Array(0x14000).fill(9))).rejects.toThrow();
    expect(localStorage.getItem(key + ':pending')).toBe('1');
    expect((await readSave(key))?.[0]).toBe(9);
    expect(localStorage.getItem(key + ':pending')).toBeNull();
  });
  it('serializes writes so the newest snapshot reaches the server last', async () => {
    let release!: (response: Response) => void;
    const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { release = resolve; })).mockResolvedValueOnce(ok());
    vi.stubGlobal('fetch', fetcher);
    const first = uploadSave(key, new Uint8Array(0x14000).fill(1));
    const second = uploadSave(key, new Uint8Array(0x14000).fill(2));
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    release(ok()); await Promise.all([first, second]);
    expect(fetcher.mock.calls[1][1].body[0]).toBe(2);
    expect(localStorage.getItem(key + ':pending')).toBeNull();
  });
});
