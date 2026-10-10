export type GeometryBounds = [west: number, south: number, east: number, north: number];
const remembered = new WeakMap<object, GeometryBounds>();
export function geometryBounds(coordinates: any[]): GeometryBounds {
  const saved = remembered.get(coordinates);
  if (saved) return saved;
  const bounds: GeometryBounds = [Infinity, Infinity, -Infinity, -Infinity];
  function visit(values: any[]) {
    if (typeof values[0] === 'number') {
      bounds[0] = Math.min(bounds[0], values[0]); bounds[2] = Math.max(bounds[2], values[0]);
      bounds[1] = Math.min(bounds[1], values[1]); bounds[3] = Math.max(bounds[3], values[1]);
    } else for (const child of values) visit(child);
  }
  visit(coordinates); remembered.set(coordinates, bounds); return bounds;
}
export function geometryInView(coordinates: any[], view: GeometryBounds, bounds?: GeometryBounds) {
  const b = bounds || geometryBounds(coordinates);
  return b[0] <= view[2] && b[2] >= view[0] && b[1] <= view[3] && b[3] >= view[1];
}
export function prepareMapGeometryBounds(tile: any) {
  for (const feature of tile.collection?.features || []) feature.bbox = geometryBounds(feature.geometry.coordinates);
  for (const surface of tile.surfaces || []) surface.bounds = geometryBounds(surface.rings);
  return tile;
}
