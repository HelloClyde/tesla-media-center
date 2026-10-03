import { expect, it } from 'vitest';
import { createPositionTransition } from './amapPositionTransition';

it('interpolates, retargets continuously and holds the latest point', () => {
  const t = createPositionTransition();
  t.move({ point: [120, 30], heading: 359 }, 0);
  t.move({ point: [120.001, 30], heading: 1 }, 1000);
  const mid = t.sample(1450)!;
  expect(mid.point[0]).toBeCloseTo(120 + .001 * 450 / 1300);
  expect(mid.heading).toBeCloseTo((359 + 2 * 450 / 1300) % 360);
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
  t.move({ point: [120.0002, 30], heading: 90 }, 2000);
  expect(t.sample(2000)!.point[0]).toBeCloseTo(120 + .0001 * 1000 / 1300);
  expect(t.sample(2100)!.point[0]).toBeGreaterThan(t.sample(2000)!.point[0]);
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
