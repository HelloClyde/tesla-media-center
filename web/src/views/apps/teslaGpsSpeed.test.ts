import { expect, it } from 'vitest';
import { createGpsSpeedTracker, speedFromLiveGpsFix, type GpsSpeedFix } from './teslaGpsSpeed';

const start = 100000;
const fix = (offset: number, longitude: number, speed: number | null = null, accuracy = 4): GpsSpeedFix => ({
  latitude: 30, longitude, speed, accuracy, timestamp: start + offset,
});

it('uses the H5 speed value even when the head-unit position timestamp is unusual', () => {
  expect(speedFromLiveGpsFix(5)).toBe(18);
  expect(speedFromLiveGpsFix(0)).toBe(0);
  expect(speedFromLiveGpsFix(null)).toBeNull();
  expect(speedFromLiveGpsFix(Number.NaN)).toBeNull();
});

it('uses device GPS speed when present and estimates from positions when it is null', () => {
  const tracker = createGpsSpeedTracker();
  expect(tracker.accept(fix(0, 120, 5), start)).toBe(18);
  expect(tracker.accept(fix(1000, 120.0001), start + 1000)).toBeNull();
  const derived = tracker.accept(fix(5000, 120.0005), start + 5000);
  expect(derived).toBeGreaterThan(20);
  expect(derived).toBeLessThan(40);
});

it('does not turn stationary jitter or duplicate fixes into speed', () => {
  const tracker = createGpsSpeedTracker();
  expect(tracker.accept(fix(0, 120), start)).toBeNull();
  expect(tracker.accept(fix(5000, 120.00001), start + 5000)).toBe(0);
  expect(tracker.accept(fix(5000, 120.0005), start + 5000)).toBeNull();
});

it('rejects stale, inaccurate and implausible position changes', () => {
  const tracker = createGpsSpeedTracker();
  expect(tracker.accept(fix(0, 120), start)).toBeNull();
  expect(tracker.accept(fix(5000, 120.0005, null, 80), start + 5000)).toBeNull();
  expect(tracker.accept(fix(6000, 120.5), start + 6000)).toBeNull();
  expect(tracker.accept(fix(7000, 120.5001), start + 30000)).toBeNull();
});
