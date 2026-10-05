import type { Point } from './amapNavigation';

export type Place = { id: string; name: string; address: string; location: Point; entrance?: Point };

export function placeNavigationPoint(place: Place): Point {
  return place.entrance || place.location;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Validates TMC's own search contract, not an upstream provider's response. */
export function parseSearchPlaces(response: unknown): Place[] {
  if (!record(response) || response.status !== 'ok') {
    throw new Error(record(response) && typeof response.message === 'string'
      ? response.message : '地点搜索暂不可用');
  }
  const data = response.data;
  if (!record(data) || !Array.isArray(data.places)) throw new Error('地点搜索返回格式异常');
  if (data.coordinateSystem !== 'GCJ-02') throw new Error('地点搜索返回的坐标系不受支持');
  const places: Place[] = [], ids = new Set<string>();
  for (const item of data.places) {
    if (!record(item) || (item.item_type !== undefined && item.item_type !== 'poi')) continue;
    const { id, name, location } = item;
    if (typeof id !== 'string' || !id.trim() || typeof name !== 'string' || !name.trim()) continue;
    if (!Array.isArray(location) || location.length !== 2 ||
      !location.every(v => typeof v === 'number' && Number.isFinite(v)) ||
      Math.abs(location[0]) > 180 || Math.abs(location[1]) > 85) continue;
    if (ids.has(id.trim())) continue;
    ids.add(id.trim());
    const entrance = item.entrance;
    const validEntrance = Array.isArray(entrance) && entrance.length === 2 &&
      entrance.every(v => typeof v === 'number' && Number.isFinite(v)) &&
      Math.abs(entrance[0]) <= 180 && Math.abs(entrance[1]) <= 85;
    places.push({ id: id.trim(), name: name.trim(),
      address: typeof item.address === 'string' ? item.address.trim() : '',
      location: [location[0], location[1]],
      ...(validEntrance ? { entrance: [entrance[0], entrance[1]] as Point } : {}) });
  }
  if (data.places.length && !places.length) throw new Error('搜索结果中没有可用于导航的地点');
  return places;
}
