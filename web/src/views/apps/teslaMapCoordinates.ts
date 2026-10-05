import { wgs84togcj02 } from 'coordtransform';
export type MapPoint = [number, number];
const METERS = 111319.49079327358;
export function vehicleMapPoint(sample: any): MapPoint | undefined {
  if (sample?.longitude == null || sample?.latitude == null) return;
  const lng = Number(sample.longitude), lat = Number(sample.latitude);
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 85 || (!lng && !lat)) return;
  return /gcj/i.test(String(sample.coord_type)) ? [lng, lat] : wgs84togcj02(lng, lat) as MapPoint;
}
// Local metric coordinates: east / south, matching a north-up Three.js ground plane.
export function groundOffset(point: number[], origin: MapPoint): MapPoint {
  return [(point[0] - origin[0]) * METERS * Math.cos(origin[1] * Math.PI / 180), (origin[1] - point[1]) * METERS];
}
export function groundPoint(origin: MapPoint, east: number, south: number): MapPoint {
  return [origin[0] + east / (METERS * Math.cos(origin[1] * Math.PI / 180)), origin[1] - south / METERS];
}
export function groundBounds(origin: MapPoint, radius: number) {
  const dx = radius / (METERS * Math.cos(origin[1] * Math.PI / 180)), dy = radius / METERS;
  return [origin[0] - dx, origin[1] + dy, origin[0] + dx, origin[1] - dy] as const;
}
