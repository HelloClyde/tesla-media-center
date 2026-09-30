import { describe, expect, it } from 'vitest';
import { visualTravelSpeedMps, wheelAngularSpeed } from './teslaMotion';

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
