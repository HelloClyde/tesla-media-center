import { meters, type Point } from './amapNavigation';

export const normalizeHeading = (degrees: number) => ((degrees % 360) + 360) % 360;
export function bearingBetween(a: Point, b: Point) {
  const rad = Math.PI / 180;
  const delta = (b[0] - a[0]) * rad;
  return normalizeHeading(Math.atan2(Math.sin(delta) * Math.cos(b[1] * rad),
    Math.cos(a[1] * rad) * Math.sin(b[1] * rad) - Math.sin(a[1] * rad) * Math.cos(b[1] * rad) * Math.cos(delta)) / rad);
}
export function smoothHeading(previous: number | undefined, next: number) {
  if (previous === undefined) return normalizeHeading(next);
  const delta = normalizeHeading(next - previous + 180) - 180;
  return normalizeHeading(previous + delta * .4);
}
export function movementHeading(previous: Point | undefined, point: Point, accuracy: number,
  heading: number | null | undefined, speed: number | null | undefined) {
  // Stationary GPS headings are frequently null or noisy. Never treat null
  // as north, and retain the last direction until movement is meaningful.
  if (accuracy > 60) return undefined;
  if (typeof heading === 'number' && Number.isFinite(heading) && heading >= 0 && (speed == null || speed > 1))
    return normalizeHeading(heading);
  if (previous && meters(previous, point) >= Math.max(8, accuracy)) return bearingBetween(previous, point);
  return undefined;
}
