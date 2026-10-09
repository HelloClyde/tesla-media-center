import { expect, it } from 'vitest';
import { createPositionTransition } from './amapPositionTransition';

it('interpolates, retargets continuously and holds the latest point', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 359 }, 0);
  t.move({ point: [120.001, 30], heading: 1 }, 1000);
  const mid = t.sample(1450)!;
  expect(mid.point[0]).toBeGreaterThan(120);
  expect(mid.point[0]).toBeLessThan(120.001);
  expect(((mid.heading - 359 + 360) % 360)).toBeGreaterThan(0);
  expect(((mid.heading - 359 + 360) % 360)).toBeLessThan(2);
  t.move({ point: [120.002, 30], heading: 10 }, 1450);
  expect(t.sample(1450)).toEqual(mid);
  expect(t.sample(3000)?.point).toEqual([120.002, 30]);
  expect(t.done(3000)).toBe(true);
});

it('keeps moving between one-second GPS fixes instead of pausing at each point', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 90 }, 0);
  t.move({ point: [120.0001, 30], heading: 90 }, 1000);
  const before = t.sample(1900)!.point[0];
  expect(t.sample(2000)!.point[0]).toBeGreaterThan(before);
  expect(t.done(2000)).toBe(false);
  const current = t.sample(2000);
  t.move({ point: [120.0002, 30], heading: 90 }, 2000);
  expect(t.sample(2000)).toEqual(current);
  expect(t.sample(2100)!.point[0]).toBeGreaterThan(t.sample(2000)!.point[0]);
});

it('preserves movement speed across irregular callback intervals', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 90 }, 0);
  t.move({ point: [120.0001, 30], heading: 90 }, 1000);
  for (const [now, longitude] of [[1700, 120.00017], [2850, 120.000285], [3450, 120.000345]]) {
    const before = t.sample(now)!;
    const speedBefore = before.point[0] - t.sample(now - 1)!.point[0];
    t.move({ point: [longitude, 30], heading: 90 }, now);
    expect(t.sample(now)).toEqual(before);
    const speedAfter = t.sample(now + 1)!.point[0] - before.point[0];
    expect(speedAfter).toBeGreaterThan(0);
    expect(Math.abs(speedAfter / speedBefore - 1)).toBeLessThan(.02);
  }
});

it('ignores duplicate fusion/GPS callbacks without restarting or changing the cadence', () => {
  const t = createPositionTransition(), baseline = createPositionTransition();
  for (const transition of [t, baseline]) {
    transition.move({ point: [120, 30], heading: 90 }, 0);
    transition.move({ point: [120.0001, 30], heading: 90 }, 1000);
  }
  for (const now of [1100, 1250, 1500, 1750]) t.move({ point: [120.0001, 30], heading: 90 }, now);
  expect(t.sample(1900)).toEqual(baseline.sample(1900));
  for (const transition of [t, baseline]) transition.move({ point: [120.0002, 30], heading: 90 }, 2000);
  expect(t.sample(2200)).toEqual(baseline.sample(2200));
});

it('stops at the received fix without extrapolation or overshoot when GPS falls silent', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 359 }, 0);
  t.move({ point: [120.0001, 30.0001], heading: 1 }, 1000);
  t.move({ point: [120.0002, 30.0002], heading: 3 }, 2000);
  for (let now = 2000; now <= 4000; now += 25) {
    expect(t.sample(now)!.point[0]).toBeLessThanOrEqual(120.0002);
    expect(t.sample(now)!.point[1]).toBeLessThanOrEqual(30.0002);
  }
  expect(t.sample(20_000)!.point).toEqual([120.0002, 30.0002]);
  expect(t.done(20_000)).toBe(true);
});

it('snaps initial fixes, large corrections and return from background', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 0 }, 0);
  expect(t.done(0)).toBe(true);
  t.move({ point: [121, 30], heading: 0 }, 1000);
  expect(t.sample(1000)?.point).toEqual([121, 30]);
  t.move({ point: [121.001, 30], heading: 10 }, 1500, true);
  expect(t.sample(1500)?.point).toEqual([121.001, 30]);
});
