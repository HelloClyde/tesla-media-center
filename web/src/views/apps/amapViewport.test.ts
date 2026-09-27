import { describe, expect, it } from 'vitest';
import { viewportTiles } from './amapViewport';

describe('App overview tiles', () => {
  it('covers Guangzhou to Beijing at long-route overview scale', () => {
    const tiles = viewportTiles(4.5, 95, 48, 135, 17);
    expect(tiles).toContainEqual([3, 6, 2]);
    expect(tiles).toContainEqual([3, 6, 3]);
    expect(new Set(tiles.map(t => t[0]))).toEqual(new Set([3]));
  });
  it('keeps overview surfaces when adding city detail', () => {
    const tiles = viewportTiles(16, 116.38, 39.92, 116.42, 39.89);
    expect(new Set(tiles.map(t => t[0]))).toEqual(new Set([3, 6, 8, 10, 12, 14]));
  });
  it('bounds each source batch and deduplicates grid coordinates', () => {
    const tiles = viewportTiles(12, 80, 55, 140, 15);
    for (const level of new Set(tiles.map(t => t[0])))
      expect(tiles.filter(t => t[0] === level).length).toBeLessThanOrEqual(24);
    expect(new Set(tiles.map(t => t.join('/'))).size).toBe(tiles.length);
  });
});
