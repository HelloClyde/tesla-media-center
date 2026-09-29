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
