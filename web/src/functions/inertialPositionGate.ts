import type { InertialResult } from './inertialSession';

/** Navigation publication policy; timestamps use the capture's elapsed clock. */
export function createInertialPositionGate() {
  let timestamp = -1, missing = false;
  let expires = -Infinity;
  function fresh(now: number) { return Number.isFinite(now) && now < expires; }
  function accept(output: InertialResult['output'], elapsed: number | null, now: number) {
    if (!output || elapsed === null || !Number.isFinite(elapsed) || !Number.isFinite(now)
      || !Number.isFinite(output.timestamp) || output.timestamp <= timestamp
      || output.timestamp > elapsed + 2) return null;
    const age = Math.max(0, elapsed + 1 - output.timestamp);
    if (age >= 1500 || !Number.isFinite(output.estimated_accuracy)
      || output.estimated_accuracy! < 0 || output.estimated_accuracy! > 60
      || !Number.isFinite(output.speed) || output.speed! < 0
      || (output.heading != null && (!Number.isFinite(output.heading)
        || output.heading < 0 || output.heading >= 360))) return null;
    const recovered = missing && !output.missing_fix;
    missing = output.missing_fix; timestamp = output.timestamp;
    // Network delay consumes the freshness budget; receipt never resets age.
    expires = now + 1500 - age;
    return { output, recovered };
  }
  function reset() { timestamp = -1; missing = false; expires = -Infinity; }
  return { accept, fresh, reset };
}
