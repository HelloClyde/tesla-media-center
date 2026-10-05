import { describe, expect, it } from 'vitest';
import { parseSearchPlaces, placeNavigationPoint } from './amapSearch';

const poi = { id: 'test', name: '测试地点', location: [116.4, 39.9] };
const response = (places: unknown[]) => ({ status: 'ok', data: { coordinateSystem: 'GCJ-02', places } });

describe('TMC search response validation', () => {
  it('keeps valid destinations and deduplicates their IDs', () => {
    expect(parseSearchPlaces(response([poi, { ...poi, name: '重复地点' }]))).toEqual([{ ...poi, address: '' }]);
  });
  it('routes to a valid POI entrance while retaining the displayed POI center', () => {
    const [place] = parseSearchPlaces(response([{...poi, entrance:[116.401,39.901]}]));
    expect(place.location).toEqual([116.4,39.9]);
    expect(placeNavigationPoint(place)).toEqual([116.401,39.901]);
    const [withoutEntrance] = parseSearchPlaces(response([{...poi, entrance:[NaN,39.901]}]));
    expect(placeNavigationPoint(withoutEntrance)).toEqual([116.4,39.9]);
  });
  it('excludes cards and invalid coordinates without inventing destinations', () => {
    const invalid = [null, { ...poi, id: 'card', item_type: 'advertisement' },
      { ...poi, id: 'nan', location: [NaN, 39] }, { ...poi, id: 'missing', location: null },
      { ...poi, id: 'string', location: ['116', '39'] }, { ...poi, id: 'range', location: [181, 39] }];
    expect(parseSearchPlaces(response([...invalid, poi]))).toEqual([{ ...poi, address: '' }]);
    expect(() => parseSearchPlaces(response(invalid))).toThrow('没有可用于导航');
  });
  it('distinguishes an empty result from errors or an unsupported coordinate system', () => {
    expect(parseSearchPlaces(response([]))).toEqual([]);
    expect(() => parseSearchPlaces('<html>blocked</html>')).toThrow();
    expect(() => parseSearchPlaces({ status: 'error', message: '服务暂不可用' })).toThrow('服务暂不可用');
    expect(() => parseSearchPlaces({ status: 'ok', data: {} })).toThrow('格式异常');
    for (const coordinateSystem of [undefined, 'WGS-84', 'BD-09']) {
      expect(() => parseSearchPlaces({ status: 'ok', data: { coordinateSystem, places: [poi] } })).toThrow('坐标系');
    }
  });
});
