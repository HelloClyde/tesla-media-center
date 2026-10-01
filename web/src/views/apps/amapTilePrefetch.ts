import { cumulative, pointAt, type AppRoute } from './amapNavigation';

// One geographic-grid ring, nearest to the view first. Low-detail overview
// tiles already cover huge areas; only prefetch the two detailed source levels.
export function surroundingTiles(visible: number[][], limit = 16) {
  const seen = new Set(visible.map(tile => tile.join('/')));
  const result: number[][] = [];
  for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0], [-1, -1], [1, -1], [1, 1], [-1, 1]]) {
    for (const [level, x, y] of visible) {
      if (level < 12) continue;
      const tile = [level, x + dx, y + dy], key = tile.join('/');
      if (tile[1] < 0 || tile[2] < 0 || tile[1] >= 2 ** level || tile[2] >= 2 ** level || seen.has(key)) continue;
      seen.add(key); result.push(tile);
      if (result.length >= limit) return result;
    }
  }
  return result;
}

// Sample only the next eight kilometres of the selected route. Centre tiles
// come first; adjacent tiles cover turns near a grid boundary. The fixed cap
// prevents a long route from triggering a city-scale download.
export function routeCorridorTiles(route: AppRoute, progress = 0, limit = 32, lookaheadMeters = 8000) {
  if (route.path.length < 2 || limit <= 0) return [];
  const lengths = cumulative(route);
  const total = lengths[lengths.length - 1] || 0;
  if (!Number.isFinite(total) || !total) return [];
  const start = Math.max(0, Math.min(Number.isFinite(progress) ? progress : 0, total));
  const end = Math.min(total, start + lookaheadMeters);
  const size = 2 ** 14;
  const centers: number[][] = [], result: number[][] = [];
  const seen = new Set<string>();
  const add = (x: number, y: number, target: number[][]) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const key = `${x}/${y}`;
    if (seen.has(key)) return;
    seen.add(key); target.push([14, x, y]);
  };
  for (let distance = start; distance <= end; distance += 500) {
    const [lon, lat] = pointAt(route, distance);
    add(Math.floor((lon + 180) / 360 * size), Math.floor((90 - lat) / 180 * size), centers);
  }
  const [lon, lat] = pointAt(route, end);
  add(Math.floor((lon + 180) / 360 * size), Math.floor((90 - lat) / 180 * size), centers);
  result.push(...centers.slice(0, limit));
  if (result.length >= limit) return result;
  for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
    for (const [, x, y] of centers) {
      add(x + dx, y + dy, result);
      if (result.length >= limit) return result;
    }
  }
  return result;
}

/** The 3D ground consumes decoded level-14 roads and level-15 buildings. */
export function route3DTiles(route: AppRoute, progress = 0) {
  if (route.path.length < 2) return [];
  const roads = routeCorridorTiles(route, progress, 8, 2500);
  const lengths = cumulative(route);
  const total = lengths[lengths.length - 1] || 0;
  if (!total) return roads;
  const start = Math.max(0, Math.min(Number.isFinite(progress) ? progress : 0, total));
  const end = Math.min(total, start + 1500);
  const size = 2 ** 15;
  const buildings: number[][] = [], centers: number[][] = [], seen = new Set<string>();
  const add = (x: number, y: number, target: number[][]) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    const key = `${x}/${y}`;
    if (seen.has(key)) return;
    seen.add(key); target.push([15, x, y]);
  };
  for (let distance = start; distance <= end; distance += 250) {
    const [lon, lat] = pointAt(route, distance);
    add(Math.floor((lon + 180) / 360 * size), Math.floor((90 - lat) / 180 * size), centers);
  }
  const [lon, lat] = pointAt(route, end);
  add(Math.floor((lon + 180) / 360 * size), Math.floor((90 - lat) / 180 * size), centers);
  buildings.push(...centers.slice(0, 12));
  for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
    for (const [, x, y] of centers) {
      if (buildings.length >= 12) return [...roads, ...buildings];
      add(x + dx, y + dy, buildings);
    }
  }
  return [...roads, ...buildings];
}
