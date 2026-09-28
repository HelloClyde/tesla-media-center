// @vitest-environment node
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';

const script = readFileSync(new URL('../../public/tts/worker.js', import.meta.url), 'utf8').replace('void init();', '');
it('reuses model bytes across workers through Cache Storage', async () => {
  const entries = new Map<string, Response>();
  const cache = { match: async (url: string) => entries.get(url)?.clone(), put: async (url: string, value: Response) => { entries.set(url, value); } };
  const fetch = vi.fn(async () => new Response(new Uint8Array([1, 2, 3])));
  const make = () => {
    const env: any = { self: {}, postMessage: vi.fn(), caches: { open: async () => cache }, fetch, Response, ArrayBuffer, Uint8Array };
    runInNewContext(script, env); return env;
  };
  await make().asset('model.data');
  const second = make();
  expect(new Uint8Array(await second.asset('model.data'))).toEqual(new Uint8Array([1, 2, 3]));
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('falls back to the database when Cache Storage fails and reports persistence failures', async () => {
  const stored = new Map<string, ArrayBuffer>();
  const fetch = vi.fn(async () => new Response(new Uint8Array([1, 2, 3])));
  const make = (fail = false) => {
    const env: any = { self: {}, postMessage: vi.fn(), caches: { open: async () => { throw Error('disabled'); } }, fetch, Response, ArrayBuffer, Uint8Array };
    runInNewContext(script, env);
    env.modelStore = async (url: string, data?: ArrayBuffer) => {
      if (fail) throw Error('quota');
      if (data) stored.set(url, data);
      return stored.get(url);
    };
    return env;
  };
  await make().asset('model.data');
  await make().asset('model.data');
  expect(fetch).toHaveBeenCalledTimes(1);
  const failed = make(true);
  await failed.asset('other.data');
  expect(failed.postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'cache', status: expect.stringContaining('未完整保存') }));
});
