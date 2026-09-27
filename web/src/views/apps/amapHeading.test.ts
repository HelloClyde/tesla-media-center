import { describe, expect, it } from 'vitest';
import { bearingBetween, movementHeading, smoothHeading } from './amapHeading';
describe('navigation heading', () => {
  it('uses clockwise bearings from north', () => {
    expect(bearingBetween([116,39], [116,40])).toBeCloseTo(0);
    expect(bearingBetween([116,39], [117,39])).toBeCloseTo(90, 0);
    expect(bearingBetween([116,39], [116,38])).toBeCloseTo(180);
    expect(bearingBetween([116,39], [115,39])).toBeCloseTo(270, 0);
  });
  it('smooths across north without spinning around the map', () => {
    expect(smoothHeading(359, 1)).toBeCloseTo(359.8);
    expect(smoothHeading(1, 359)).toBeCloseTo(.2);
    expect(smoothHeading(undefined, 270)).toBe(270);
  });
  it('ignores inaccurate and stationary heading fixes', () => {
    expect(movementHeading(undefined,[116,39],100,90,10)).toBeUndefined();
    expect(movementHeading([116,39],[116.00001,39],5,0,0)).toBeUndefined();
    expect(movementHeading(undefined,[116,39],5,null,null)).toBeUndefined();
    expect(movementHeading(undefined,[116,39],5,90,10)).toBe(90);
  });
  it('falls back to meaningful movement when GPS heading is unavailable', () => {
    expect(movementHeading([116,39],[116,39.001],5,null,null)).toBeCloseTo(0);
  });
});
