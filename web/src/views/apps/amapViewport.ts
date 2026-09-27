// App BMD uses a geographic grid, not Web Mercator XYZ tiles. Source levels
// are sparse: level 3 supplies the overview surfaces; level 6 adds trunk roads.
export function viewportTiles(zoom: number, west: number, north: number, east: number, south: number) {
  const tiles: number[][] = [];
  for (const level of [3, 6, 8, 10, 12, 14]) {
    if (level > zoom && level !== 3) continue;
    const size = 2 ** level;
    const x = (v: number) => Math.max(0, Math.min(size - 1, Math.floor((v + 180) / 360 * size)));
    const y = (v: number) => Math.max(0, Math.min(size - 1, Math.floor((90 - v) / 180 * size)));
    if ((x(east) - x(west) + 1) * (y(south) - y(north) + 1) > 24) continue;
    for (let xx = x(west); xx <= x(east); xx++)
      for (let yy = y(north); yy <= y(south); yy++) tiles.push([level, xx, yy]);
  }
  return tiles;
}
