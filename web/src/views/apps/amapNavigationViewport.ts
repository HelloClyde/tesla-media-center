/** In heading-up navigation, show farther ahead as speed increases. */
export function navigationViewport(speedKmh: number | null) {
  const speed = speedKmh !== null && Number.isFinite(speedKmh) ? Math.max(0, speedKmh) : 0;
  const t = Math.max(0, Math.min(1, (speed - 35) / 85));
  const blend = t * t * (3 - 2 * t);
  return { zoom: 17 - 1.5 * blend, vehicleY: .62 + .07 * blend };
}
