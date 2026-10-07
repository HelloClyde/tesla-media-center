import { describe, expect, it } from 'vitest';
import { createTrafficSignalReminder, greenWaveSpeedWindow, mergeTrafficSignalLights, nearGreenReminder, recentTrafficSignalFix, trustedTrafficSignalFix, upcomingRouteTrafficLight, upcomingTrafficSignal, type LiveTrafficLight } from './amapTrafficSignals';
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
    expect(nearGreenReminder({ ...signal()!, observedAt: now - 21_000 }, now)).not.toBeNull();
    expect(nearGreenReminder({ ...signal()!, observedAt: now - 91_000 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, seconds: 4 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, distance: 201 }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, phases: phases.slice(0, 1) }, now)).toBeNull();
    expect(nearGreenReminder({ ...signal()!, phases: [phases[0], { ...phases[1], start: phases[1].start + 2 }] }, now)).toBeNull();
  });

  const at = (time: number, plan = phases, observedAt = now) => upcomingTrafficSignal(route, 50,
    [{ point: [120, 30.001], phases: plan }], observedAt, time);

  it('announces a long red countdown even if its still-valid plan has not refreshed', () => {
    const reminder = createTrafficSignalReminder();
    const plan: LiveTrafficLight['phases'] = [
      { start: now / 1000 - 20, end: now / 1000 + 76, color: 'red' },
      { start: now / 1000 + 76, end: now / 1000 + 106, color: 'green' },
    ];
    expect(reminder.update(at(now + 40_000, plan), now + 40_000)).toBeNull();
    expect(reminder.update(at(now + 73_000, plan), now + 73_000)?.text).toBe('红灯即将变绿');
  });

  it('retries interrupted synthesis and consumes a cue only after playback starts', () => {
    const reminder = createTrafficSignalReminder();
    const first = reminder.update(at(now), now)!;
    expect(reminder.update(at(now + 1_000), now + 1_000)).toEqual(first);
    reminder.markSpoken(first);
    expect(reminder.update(at(now + 2_000), now + 2_000)).toBeNull();
    expect(reminder.update(at(now + 3_000), now + 3_000)).toBeNull();
  });

  it('catches a red-to-green transition when turn speech occupies the pre-green window', () => {
    const reminder = createTrafficSignalReminder();
    reminder.update(at(now), now); // Observed while another instruction is speaking.
    const green = reminder.update(at(now + 3_500), now + 3_500)!;
    expect(green).toMatchObject({ text: '绿灯亮了', expiresAt: now + 6_000 });
    reminder.markSpoken(green);
    expect(reminder.update(at(now + 4_000), now + 4_000)).toBeNull();
  });

  it('uses the actual green refresh when the red-only frame had no forecast', () => {
    const reminder = createTrafficSignalReminder();
    expect(reminder.update(at(now, phases.slice(0, 1)), now)).toBeNull();
    expect(reminder.update(at(now + 3_000, phases.slice(1), now + 3_000), now + 3_000)?.text).toBe('绿灯亮了');
  });

  it('accepts an observed early green even if the previous red-end forecast was corrected', () => {
    const reminder = createTrafficSignalReminder();
    const redOnly = [{ ...phases[0], end: now / 1000 + 10 }];
    reminder.update(at(now, redOnly), now);
    expect(reminder.update(at(now + 3_000, phases.slice(1), now + 3_000), now + 3_000)?.text).toBe('绿灯亮了');
  });

  it('does not announce a first-seen green, a yellow, a distant light or a late transition', () => {
    const reminder = createTrafficSignalReminder();
    expect(reminder.update(at(now + 3_000), now + 3_000)).toBeNull();
    reminder.update(at(now), now);
    expect(reminder.update({ ...at(now + 3_000)!, color: 'yellow' }, now + 3_000)).toBeNull();
    expect(reminder.update({ ...at(now + 3_000)!, distance: 201 }, now + 3_000)).toBeNull();
    expect(reminder.update(at(now + 6_000), now + 6_000)).toBeNull();
    reminder.clear();
    expect(reminder.update(at(now + 3_000), now + 3_000)).toBeNull();
  });

  it('allows the next red cycle under 90 seconds but ignores a delayed result from the old cycle', () => {
    const reminder = createTrafficSignalReminder();
    const first = reminder.update(at(now), now)!;
    reminder.markSpoken(first);
    const nextPlan: LiveTrafficLight['phases'] = [
      { start: now / 1000 + 33, end: now / 1000 + 60, color: 'red' },
      { start: now / 1000 + 60, end: now / 1000 + 90, color: 'green' },
    ];
    const second = reminder.update(at(now + 57_000, nextPlan, now + 57_000), now + 57_000)!;
    reminder.markSpoken(first);
    expect(second.cycle).not.toBe(first.cycle);
    expect(reminder.update(at(now + 58_000, nextPlan, now + 57_000), now + 58_000)).toEqual(second);
  });

  it('does not repeat a played cue when a refresh slightly corrects the phase end', () => {
    const reminder = createTrafficSignalReminder();
    reminder.markSpoken(reminder.update(at(now), now)!);
    const corrected = phases.map(phase => ({ ...phase, start: phase.start + .5, end: phase.end + .5 }));
    expect(reminder.update(at(now + 1_000, corrected, now + 1_000), now + 1_000)).toBeNull();
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
