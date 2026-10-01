import { GPS_SPEED_MAX_AGE_MS, speedFromGpsFix } from './teslaMotion';

export interface GpsSpeedFix {
  latitude: number;
  longitude: number;
  accuracy: number;
  speed: number | null;
  timestamp: number;
}

const POSITION_WINDOW_MS = 12000;
const MIN_POSITION_INTERVAL_MS = 4000;
const MAX_POSITION_ACCURACY_METERS = 30;

function distanceMeters(a: GpsSpeedFix, b: GpsSpeedFix) {
  const radians = Math.PI / 180;
  const latitude = (b.latitude - a.latitude) * radians;
  const longitude = (b.longitude - a.longitude) * radians;
  const haversine = Math.sin(latitude / 2) ** 2 +
    Math.cos(a.latitude * radians) * Math.cos(b.latitude * radians) * Math.sin(longitude / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

/** Prefer device speed; infer it from several seconds of GPS positions when absent. */
export function createGpsSpeedTracker() {
  let fixes: GpsSpeedFix[] = [];
  return {
    accept(fix: GpsSpeedFix, now = Date.now()): number | null {
      if (!Number.isFinite(fix.timestamp) || fix.timestamp <= 0 || fix.timestamp > now + 5000 ||
          now - fix.timestamp > GPS_SPEED_MAX_AGE_MS ||
          !Number.isFinite(fix.latitude) || Math.abs(fix.latitude) > 90 ||
          !Number.isFinite(fix.longitude) || Math.abs(fix.longitude) > 180 ||
          !Number.isFinite(fix.accuracy) || fix.accuracy < 0 ||
          (fixes.length > 0 && fix.timestamp <= fixes[fixes.length - 1].timestamp)) return null;

      fixes = fixes.filter(previous => fix.timestamp - previous.timestamp <= POSITION_WINDOW_MS);
      fixes.push(fix);
      const deviceSpeed = speedFromGpsFix(fix.speed, fix.timestamp, now);
      if (deviceSpeed !== null) return deviceSpeed;
      if (fix.accuracy > MAX_POSITION_ACCURACY_METERS) return null;

      const anchor = fixes.find(previous => previous.accuracy <= MAX_POSITION_ACCURACY_METERS &&
        fix.timestamp - previous.timestamp >= MIN_POSITION_INTERVAL_MS);
      if (!anchor) return null;
      const elapsed = (fix.timestamp - anchor.timestamp) / 1000;
      const distance = distanceMeters(anchor, fix);
      const noise = Math.max(3, Math.min(8, Math.max(anchor.accuracy, fix.accuracy) * .6));
      if (distance <= noise * 2) return 0;
      const speed = Math.max(0, distance - noise) / elapsed * 3.6;
      return speed <= 250 ? speed : null;
    },
    reset() { fixes = []; },
  };
}
