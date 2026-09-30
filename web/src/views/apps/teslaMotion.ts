const WHEEL_RADIUS_METERS = 0.4;
const LOW_SPEED_BLEND_KMH = 30;

/** Travel speed used by the stationary vehicle viewer's road and wheels. */
export function visualTravelSpeedMps(speedKmh: number): number {
  if (!Number.isFinite(speedKmh) || speedKmh <= 0) return 0;
  // A wheel can look too busy at walking pace when the car stays centered.
  // Blend the road and wheels together back to real travel speed by 30 km/h.
  const lowSpeedFactor = 0.5 + 0.5 * Math.min(speedKmh / LOW_SPEED_BLEND_KMH, 1);
  return speedKmh / 3.6 * lowSpeedFactor;
}

/** Angular speed in radians per second for the Model Y's 0.4 m wheel radius. */
export function wheelAngularSpeed(speedKmh: number): number {
  return visualTravelSpeedMps(speedKmh) / WHEEL_RADIUS_METERS;
}
