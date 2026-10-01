import { describe, expect, it } from 'vitest';
import { GPS_SPEED_MAX_AGE_MS, speedFromGpsFix, visualTravelSpeedMps, wheelAngularSpeed } from './teslaMotion';

it('uses fresh GPS metres per second and never substitutes an invalid fix', () => {
  const now = 100000;
  expect(speedFromGpsFix(0, now, now)).toBe(0);
  expect(speedFromGpsFix(5, now - 1000, now)).toBe(18);
  expect(speedFromGpsFix(null, now, now)).toBeNull();
  expect(speedFromGpsFix(-1, now, now)).toBeNull();
  expect(speedFromGpsFix(5, now - GPS_SPEED_MAX_AGE_MS - 1, now)).toBeNull();
});

describe('wheelAngularSpeed', () => {
  it('stops the wheels at zero speed', () => {
    expect(wheelAngularSpeed(0)).toBe(0);
    expect(wheelAngularSpeed(-5)).toBe(0);
    expect(visualTravelSpeedMps(0)).toBe(0);
  });

  it('turns gently at low speed and reaches rolling speed by 30 km/h', () => {
    const physical = (kmh: number) => kmh / 3.6 / 0.4;
    expect(wheelAngularSpeed(5)).toBeLessThan(physical(5) * 0.7);
    expect(wheelAngularSpeed(5)).toBeLessThan(wheelAngularSpeed(15));
    expect(wheelAngularSpeed(15)).toBeLessThan(wheelAngularSpeed(30));
    expect(wheelAngularSpeed(30)).toBeCloseTo(physical(30));
    expect(wheelAngularSpeed(60)).toBeCloseTo(physical(60));
    expect(wheelAngularSpeed(5) * 0.4).toBeCloseTo(visualTravelSpeedMps(5));
  });
});
