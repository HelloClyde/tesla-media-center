import { expect, it } from 'vitest';
import { surroundingTiles } from './amapTilePrefetch';

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
