/** Accept the latest returned fix regardless of the vehicle's timestamp behavior. */
export function createLivePositionGate() {
  return {
    accept(fix: { timestamp: number; accuracy: number; latitude: number; longitude: number }) {
      const valid = [fix.accuracy, fix.latitude, fix.longitude].every(Number.isFinite)
        && fix.accuracy >= 0 && Math.abs(fix.latitude) <= 90 && Math.abs(fix.longitude) <= 180;
      return { accepted: valid, reason: valid ? 'valid' : 'invalid', recovered: false };
    },
  };
}
