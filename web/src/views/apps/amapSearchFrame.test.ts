// @vitest-environment node
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';
const script = readFileSync(new URL('../../../public/amap-search.html', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)![1];
const poi = (id: string) => ({ id, name: id, location: { getLng: () => 116.4, getLat: () => 39.9 } });
async function run(center?: number[], nearStatus = 'complete', nationalStatus = 'complete', city = '杭州市', emptyCity = false) {
  const parent = { postMessage: vi.fn() };
  let receive: Function;
  const window: any = { addEventListener: (_: string, fn: Function) => { receive = fn; } };
  const options: any[] = [];
  const geocode = vi.fn((_: number[], cb: Function) => { if (city !== 'timeout') cb(city ? 'complete' : 'error', { regeocode: { addressComponent: { city } } }); });
  const search = vi.fn((_: string, callback: Function) => callback(nationalStatus, nationalStatus === 'complete' ? { poiList: { pois: (emptyCity && options[options.length - 1].city !== '全国' ? [] : [poi('shared'), poi('distant')]) } } : 'INVALID_USER_KEY'));
  const searchNearBy = vi.fn((_: string, _center: number[], _radius: number, callback: Function) => callback(nearStatus, nearStatus === 'complete' ? { poiList: { pois: [poi('near'), poi('shared')] } } : 'NEARBY_ERROR'));
  runInNewContext(script, { window, parent, location: { origin: 'https://tmc.test' }, document: { createElement: () => ({}), head: { appendChild: () => {} } }, setTimeout, clearTimeout,
    AMap: { Geocoder: function () { return { getAddress: geocode }; }, PlaceSearch: function (opts: any) { options.push(opts); return { search, searchNearBy }; } } });
  receive!({ source: parent, origin: 'https://tmc.test', data: { type: 'tmc-search', keywords: 'coffee', key: 'test', center } });
  await window.tmcSearchReady();
  return { search, searchNearBy, options, geocode, result: parent.postMessage.mock.calls[parent.postMessage.mock.calls.length - 1][0] };
}
it('uses one keyword request with or without positioning and never calls nearby search', async () => {
  for (const center of [undefined, [118.75, 32.02], [116.4, 39.9], [200, 90]]) {
    const { searchNearBy, search, result } = await run(center);
    expect(searchNearBy).not.toHaveBeenCalled();
    expect(search).toHaveBeenCalledExactlyOnceWith('coffee', expect.any(Function));
    expect(result.status).toBe('ok');
    expect(result.data.places.map((p: any) => p.id)).toEqual(['shared', 'distant']);
  }
});
it('returns keyword results even when the nearby service is unavailable', async () => {
  const { searchNearBy, result } = await run([118.75, 32.02], 'error');
  expect(searchNearBy).not.toHaveBeenCalled();
  expect(result.data.places.map((p: any) => p.id)).toEqual(['shared', 'distant']);
});
it('preserves errors when no search succeeds', async () => {
  const { result } = await run(undefined, 'error', 'error');
  expect(result.status).toBe('error'); expect(result.message).toContain('INVALID_USER_KEY');
});

it('passes the resolved current city to keyword search without imposing a city boundary', async () => {
  const { options, geocode } = await run([120.15, 30.27]);
  expect(geocode).toHaveBeenCalledWith([120.15, 30.27], expect.any(Function));
  expect(options).toEqual([expect.objectContaining({ city: '杭州市', citylimit: false })]);
});
it('falls back to national search only when the city query has no results', async () => {
  const { options, result } = await run([120.15, 30.27], 'complete', 'complete', '杭州市', true);
  expect(options.map(o => o.city)).toEqual(['杭州市', '全国']);
  expect(result.data.places).toHaveLength(2);
});
it('still searches when city resolution fails', async () => {
  const { options, result } = await run([120.15, 30.27], 'complete', 'complete', '');
  expect(options[0].city).toBe('全国');
  expect(result.status).toBe('ok');
});
it('limits waiting for city resolution to two seconds', async () => {
  vi.useFakeTimers();
  try {
    const pending = run([120.15, 30.27], 'complete', 'complete', 'timeout');
    await vi.advanceTimersByTimeAsync(2000);
    const { options, result } = await pending;
    expect(options[0].city).toBe('全国');
    expect(result.status).toBe('ok');
  } finally { vi.useRealTimers(); }
});
