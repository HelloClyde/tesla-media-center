import { expect, it } from 'vitest';
import { routeCorridorTiles, surroundingTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';

it('warms nearby detail tiles without duplicates or overview downloads', () => {
  const view = [[3, 1, 1], [14, 10, 10], [14, 11, 10]];
  const tiles = surroundingTiles(view);
  expect(tiles.length).toBeGreaterThan(0);
  expect(tiles.length).toBeLessThanOrEqual(16);
  expect(new Set(tiles.map(t => t.join('/'))).size).toBe(tiles.length);
  expect(tiles.every(t => t[0] === 14 && !view.some(v => v.join('/') === t.join('/')))).toBe(true);
  expect(tiles).toContainEqual([14, 10, 9]);
});
it('respects geographic grid bounds', () => {
  expect(surroundingTiles([[14, 0, 0]])).toEqual([[14, 1, 0], [14, 0, 1], [14, 1, 1]]);
  expect(surroundingTiles([[3, 1, 1]])).toEqual([]);
});
it('bounds route warm-up to nearby level 14 tiles and advances with progress', () => {
  const route: AppRoute = { id: 1, path: [[120.1, 30.2], [120.2, 30.2]],
    breaks: [], steps: [], distance: 10000, labels: [] };
  const start = routeCorridorTiles(route);
  const later = routeCorridorTiles(route, 6000);
  expect(start.length).toBeGreaterThan(1);
  expect(start.length).toBeLessThanOrEqual(32);
  expect(new Set(start.map(tile => tile.join('/'))).size).toBe(start.length);
  expect(start.every(tile => tile[0] === 14)).toBe(true);
  expect(later[0][1]).toBeGreaterThan(start[0][1]);
  expect(routeCorridorTiles({ ...route, path: [[120.1, 30.2]] })).toEqual([]);
});
