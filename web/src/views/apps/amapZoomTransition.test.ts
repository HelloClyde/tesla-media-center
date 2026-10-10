import {expect, it} from 'vitest';
import {createNavigationZoom} from './amapZoomTransition';

it('moves progressively and finishes at exactly one zoom step', () => {
  const zoom = createNavigationZoom();
  zoom.start(200, 1, 0, 35, 450);
  expect(zoom.sample(0)).toBeCloseTo(200);
  const middle = zoom.sample(90)!;
  expect(middle).toBeLessThan(200);
  expect(middle).toBeGreaterThan(200 / Math.SQRT2);
  expect(zoom.sample(180)).toBeCloseTo(200 / Math.SQRT2);
  expect(zoom.active).toBe(false);
  expect(zoom.sample(200)).toBeUndefined();
});
it('accumulates rapid input without jumping from the displayed camera', () => {
  const zoom = createNavigationZoom();
  zoom.start(200, 1, 0, 35, 450);
  const displayed = zoom.sample(60)!;
  zoom.start(displayed, 1, 60, 35, 450);
  expect(zoom.sample(60)).toBeCloseTo(displayed);
  expect(zoom.sample(240)).toBeCloseTo(100);
});
it('reverses smoothly and clamps at the camera limits', () => {
  const zoom = createNavigationZoom();
  zoom.start(200, 1, 0, 35, 450);
  const displayed = zoom.sample(60)!;
  zoom.start(displayed, -1, 60, 35, 450);
  expect(zoom.sample(60)).toBeCloseTo(displayed);
  expect(zoom.sample(240)).toBeCloseTo(200);
  zoom.start(200, 100, 240, 35, 450);
  expect(zoom.sample(420)).toBe(35);
  zoom.start(35, -100, 420, 35, 450);
  expect(zoom.sample(600)).toBe(450);
});
it('lets pointer interaction or disposal cancel an unfinished zoom', () => {
  const zoom = createNavigationZoom();
  zoom.start(200, 1, 0, 35, 450); zoom.cancel();
  expect(zoom.active).toBe(false);
  expect(zoom.sample(180)).toBeUndefined();
  for (const distance of [NaN, Infinity, 0, -1]) zoom.start(distance, 1, 0, 35, 450);
  expect(zoom.active).toBe(false);
});
