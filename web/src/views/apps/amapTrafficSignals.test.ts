import { describe, expect, it } from 'vitest';
import { greenWaveSpeedWindow, upcomingTrafficSignal, type LiveTrafficLight } from './amapTrafficSignals';
import type { AppRoute } from './amapNavigation';

const route: AppRoute = {
  id: 0, path: [[120, 30], [120, 30.001], [120, 30.002]],
  steps: [{ start: 0, end: 2, road: '测试路' }], breaks: [], distance: 222, labels: [],
};
const now = 1_700_000_000_000;
const light = (latitude: number, color: LiveTrafficLight['phases'][number]['color']): LiveTrafficLight => ({
  point: [120, latitude], phases: [{ start: now / 1000 - 3, end: now / 1000 + 17, color }],
});

describe('green wave reference', () => {
  it('uses a future green phase and includes timing margins', () => {
    const signal = upcomingTrafficSignal(route, 0, [{ point: [120, 30.001], phases: [
      { start: now / 1000 - 2, end: now / 1000 + 10, color: 'red' },
      { start: now / 1000 + 10, end: now / 1000 + 25, color: 'green' },
    ] }], now, now);
    const window = greenWaveSpeedWindow(signal, now, 30);
    expect(window).toEqual({ min: 19, max: 30, atCurrentSpeed: true });
  });

  it('does not offer a window without green data or when reaching it would require speeding', () => {
    const signal = upcomingTrafficSignal(route, 0, [light(30.001, 'red')], now, now);
    expect(greenWaveSpeedWindow(signal, now, 30)).toBeNull();
    expect(greenWaveSpeedWindow({ ...signal!, distance: 400, phases: [
      { start: now / 1000 + 1, end: now / 1000 + 10, color: 'green' },
    ] }, now, 40)).toBeNull();
  });
});

describe('upcoming live traffic light', () => {
  it('uses the nearest signal ahead and counts down from its phase expiry', () => {
    const found = upcomingTrafficSignal(route, 0, [light(30.0018, 'red'), light(30.001, 'green')], now, now);
    expect(found?.color).toBe('green');
    expect(found?.seconds).toBe(17);
    expect(found?.distance).toBeGreaterThan(100);
    expect(found?.distance).toBeLessThan(120);
  });

  it('hides an expired, old, off-route, or already passed signal', () => {
    expect(upcomingTrafficSignal(route, 0, [light(30.001, 'red')], now - 46_000, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 150, [light(30.001, 'red')], now, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 0, [{ ...light(30.001, 'red'), point: [120.002, 30.001] }], now, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 0, [{ ...light(30.001, 'red'), phases: [
      { start: now / 1000 - 20, end: now / 1000 - 1, color: 'red' },
    ] }], now, now)).toBeNull();
  });
});
