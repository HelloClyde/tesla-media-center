/** H5 positions may already be fused by the vehicle; do not assume a satellite source. */
export function createLivePositionGate() {
  let timestamp = 0;
  return {
    accept(fix: { timestamp: number; accuracy: number; latitude: number; longitude: number }, now: number) {
      if (![fix.timestamp, fix.accuracy, fix.latitude, fix.longitude].every(Number.isFinite)
        || fix.accuracy < 0 || Math.abs(fix.latitude) > 90 || Math.abs(fix.longitude) > 180
        || fix.timestamp <= 0 || fix.timestamp > now + 5000 || now - fix.timestamp > 15000)
        return { accepted: false, reason: 'invalid' as const, recovered: false };
      if (fix.timestamp <= timestamp) return { accepted: false, reason: 'duplicate' as const, recovered: false };
      const recovered = timestamp > 0 && fix.timestamp - timestamp > 15000;
      timestamp = fix.timestamp;
      return { accepted: true, reason: 'fresh' as const, recovered };
    },
  };
}
