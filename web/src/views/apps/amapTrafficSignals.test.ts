import { describe, expect, it } from 'vitest';
import { greenWaveSpeedWindow, mergeTrafficSignalLights, nearGreenReminder, recentTrafficSignalFix, trustedTrafficSignalFix, upcomingRouteTrafficLight, upcomingTrafficSignal, type LiveTrafficLight } from './amapTrafficSignals';
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
    expect(upcomingTrafficSignal(route, 0, [light(30.001, 'red')], now - 91_000, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 150, [light(30.001, 'red')], now, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 0, [{ ...light(30.001, 'red'), point: [120.002, 30.001] }], now, now)).toBeNull();
    expect(upcomingTrafficSignal(route, 0, [{ ...light(30.001, 'red'), phases: [
      { start: now / 1000 - 20, end: now / 1000 - 1, color: 'red' },
    ] }], now, now)).toBeNull();
  });

  it('keeps an absolute 75-second phase through a temporarily old ETA frame', () => {
    const lights: LiveTrafficLight[] = [{ point: [120, 30.001], phases: [
      { start: now / 1000 - 60, end: now / 1000 + 75, color: 'red' },
    ] }];
    expect(upcomingTrafficSignal(route, 0, lights, now - 50_000, now)?.seconds).toBe(75);
    expect(upcomingTrafficSignal(route, 0, lights, now - 50_000, now + 25_000)?.seconds).toBe(50);
    expect(upcomingTrafficSignal(route, 0, lights, now - 50_000, now + 41_000)).toBeNull();
  });

  it('keeps a Hangzhou 96-second red phase through stationary GPS silence and an empty refresh', () => {
    // Archived Hangzhou 5.1 route: the signal at 120.155116,30.270864
    // has a 96-second red phase, with 76 seconds left in the ETA frame.
    const hangzhou: AppRoute = { ...route, path: [
      [120.155116, 30.269864], [120.155116, 30.270864], [120.155116, 30.271864],
    ] };
    const first: LiveTrafficLight = { point: [120.155116, 30.270864], phases: [
      { start: now / 1000 - 20, end: now / 1000 + 76, color: 'red' },
    ] };
    let lights = mergeTrafficSignalLights([], [first], now, now);
    expect(upcomingTrafficSignal(hangzhou, 0, lights, now, now)?.seconds).toBe(76);
    lights = mergeTrafficSignalLights(lights, [], now + 40_000, now + 40_000);
    expect(recentTrafficSignalFix(now, now + 40_000, true)).toBe(true);
    expect(upcomingTrafficSignal(hangzhou, 0, lights, now + 40_000, now + 40_000)?.seconds).toBe(36);
    expect(upcomingTrafficSignal(hangzhou, 0, lights, now + 60_000, now + 60_000)?.seconds).toBe(16);
    expect(upcomingTrafficSignal(hangzhou, 0, lights, now + 77_000, now + 77_000)).toBeNull();
    expect(recentTrafficSignalFix(now, now + 40_000, false)).toBe(false);
    expect(recentTrafficSignalFix(now, now + 91_000, true)).toBe(false);
  });

  it('does not extend an old light when another light refreshes', () => {
    const old = mergeTrafficSignalLights([], [light(30.001, 'red')], now - 89_000, now);
    const refreshed = mergeTrafficSignalLights(old, [light(30.0018, 'green')], now, now);
    expect(refreshed).toHaveLength(2);
    expect(upcomingTrafficSignal(route, 0, refreshed, now, now + 2_000)?.color).toBe('green');
  });
});

describe('near-green voice cue', () => {
  const phases: LiveTrafficLight['phases'] = [
    { start: now / 1000 - 20, end: now / 1000 + 3, color: 'red' },
    { start: now / 1000 + 3, end: now / 1000 + 33, color: 'green' },
  ];
  const signal = () => upcomingTrafficSignal(route, 50, [{ point: [120, 30.001], phases }], now, now);

  it('announces the APK red-three-seconds cue only with a following green phase', () => {
    expect(nearGreenReminder(signal(), now)).toMatchObject({ text: '红灯即将变绿', phaseEnd: now / 1000 + 3 });
    expect(nearGreenReminder({ ...signal()!, observedAt: now - 21_000 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, seconds: 4 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, distance: 201 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, phases: phases.slice(0, 1) }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, phases: [phases[0], { ...phases[1], start: phases[1].start + 2 }] }, now)).toBeNull();
  });
});

it('shows route traffic lights during navigation without inventing a live phase', () => {
  const withLights = { ...route, trafficLights: [[120, 30.001], [120, 30.0018]] as [number, number][] };
  expect(upcomingRouteTrafficLight(withLights, 0)?.distance).toBeGreaterThan(100);
  expect(upcomingRouteTrafficLight(withLights, 150)?.point).toEqual([120, 30.0018]);
  expect(upcomingRouteTrafficLight(withLights, 230)).toBeNull();
});

describe('live traffic light position quality', () => {
  it('accepts a precise matched fix but rejects weak or estimated tunnel positions', () => {
    expect(trustedTrafficSignalFix(1.3)).toBe(true);
    expect(trustedTrafficSignalFix(25, { state: 'tracking', estimated: false })).toBe(true);
    expect(trustedTrafficSignalFix(26)).toBe(false);
    expect(trustedTrafficSignalFix(NaN)).toBe(false);
    expect(trustedTrafficSignalFix(1, { state: 'estimated', estimated: true })).toBe(false);
    expect(trustedTrafficSignalFix(1, { state: 'recovering', estimated: false })).toBe(false);
  });
  it('keeps a previously trusted signal through a short positioning correction only', () => {
    expect(recentTrafficSignalFix(now, now + 19_000)).toBe(true);
    expect(recentTrafficSignalFix(now, now + 20_001)).toBe(false);
    expect(recentTrafficSignalFix(0, now)).toBe(false);
  });
});
