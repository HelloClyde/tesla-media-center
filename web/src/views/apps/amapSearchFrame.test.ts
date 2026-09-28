// @vitest-environment node
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';
const script = readFileSync(new URL('../../../public/amap-search.html', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)![1];
const poi = (id: string) => ({ id, name: id, location: { getLng: () => 116.4, getLat: () => 39.9 } });
async function run(center?: number[], nearStatus = 'complete', nationalStatus = 'complete') {
  const parent = { postMessage: vi.fn() };
  let receive: Function;
  const window: any = { addEventListener: (_: string, fn: Function) => { receive = fn; } };
  const search = vi.fn((_: string, callback: Function) => callback(nationalStatus, nationalStatus === 'complete' ? { poiList: { pois: [poi('shared'), poi('distant')] } } : 'INVALID_USER_KEY'));
  const searchNearBy = vi.fn((_: string, _center: number[], _radius: number, callback: Function) => callback(nearStatus, nearStatus === 'complete' ? { poiList: { pois: [poi('near'), poi('shared')] } } : 'NEARBY_ERROR'));
  runInNewContext(script, { window, parent, location: { origin: 'https://tmc.test' }, document: { createElement: () => ({}), head: { appendChild: () => {} } }, setTimeout, clearTimeout,
    AMap: { PlaceSearch: function () { return { search, searchNearBy }; } } });
  receive!({ source: parent, origin: 'https://tmc.test', data: { type: 'tmc-search', keywords: 'coffee', key: 'test', center } });
  await window.tmcSearchReady();
  return { search, searchNearBy, result: parent.postMessage.mock.calls[parent.postMessage.mock.calls.length - 1][0] };
}
it('passes map coordinates to nearby search and keeps deduplicated national matches', async () => {
  const { searchNearBy, result } = await run([116.4, 39.9]);
  expect(searchNearBy).toHaveBeenCalledWith('coffee', [116.4, 39.9], 30000, expect.any(Function));
  expect(result.data.places.map((p: any) => p.id)).toEqual(['near', 'shared', 'distant']);
});
it('uses national search when no valid position is available', async () => {
  for (const center of [undefined, [200, 90]]) {
    const { searchNearBy, search, result } = await run(center);
    expect(searchNearBy).not.toHaveBeenCalled(); expect(search).toHaveBeenCalledTimes(1);
    expect(result.status).toBe('ok');
  }
});
it('retains national matches when nearby search fails', async () => {
  const { result } = await run([116.4, 39.9], 'error');
  expect(result.data.places.map((p: any) => p.id)).toEqual(['shared', 'distant']);
});
it('preserves errors when no search succeeds', async () => {
  const { result } = await run(undefined, 'error', 'error');
  expect(result.status).toBe('error'); expect(result.message).toContain('INVALID_USER_KEY');
});
