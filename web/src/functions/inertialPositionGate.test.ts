import { expect, it } from 'vitest';
import { createInertialPositionGate } from './inertialPositionGate';
const point = (timestamp: number, missing_fix = false) => ({ timestamp, missing_fix,
  longitude: 120, latitude: 30, altitude: 0, state: 8, quality: 1,
  source: 'amap-vdr-ordinary', speed: 8, heading: 90, estimated_accuracy: 5 });

it('charges network delay against freshness and rejects stale, future and repeated output', () => {
  const gate = createInertialPositionGate();
  expect(gate.accept(point(101), 1500, 9000)).not.toBeNull();
  expect(gate.fresh(9099)).toBe(true);
  expect(gate.fresh(9100)).toBe(false);
  expect(gate.accept(point(101), 1500, 9099)).toBeNull();
  expect(gate.accept(point(102), 1601, 9200)).toBeNull();
  expect(gate.accept(point(2000), 1601, 9200)).toBeNull();
});

it('does not suppress GPS for inaccurate output and resets recovery history between sessions', () => {
  const gate = createInertialPositionGate();
  expect(gate.accept({ ...point(101), estimated_accuracy: 61 }, 100, 100)).toBeNull();
  expect(gate.fresh(100)).toBe(false);
  expect(gate.accept(point(101, true), 100, 100)?.recovered).toBe(false);
  expect(gate.accept(point(141), 140, 140)?.recovered).toBe(true);
  gate.reset();
  expect(gate.fresh(140)).toBe(false);
  expect(gate.accept(point(1), 0, 150)?.recovered).toBe(false);
});
