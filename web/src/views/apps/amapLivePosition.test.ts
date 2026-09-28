import { expect, it } from 'vitest';
import { createLivePositionGate } from './amapLivePosition';
const fix = (timestamp: number) => ({ timestamp, latitude: 30.2, longitude: 120.2, accuracy: 1.3 });
it('accepts the latest returned coordinates regardless of old, repeated or invalid timestamps', () => {
  const gate = createLivePositionGate();
  for (const timestamp of [100000, 100000, 99000, 0, NaN, Date.now() + 999999]) {
    expect(gate.accept(fix(timestamp)).accepted).toBe(true);
  }
});
it('still rejects malformed coordinates and precision', () => {
  const gate = createLivePositionGate();
  expect(gate.accept({ ...fix(0), latitude: 100 }).accepted).toBe(false);
  expect(gate.accept({ ...fix(0), longitude: NaN }).accepted).toBe(false);
  expect(gate.accept({ ...fix(0), accuracy: -1 }).accepted).toBe(false);
});
