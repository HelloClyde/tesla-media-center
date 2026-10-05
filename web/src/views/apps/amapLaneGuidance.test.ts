import { describe, expect, it } from 'vitest';
import { laneArrowAsset, upcomingLaneGuide, type LaneGuide } from './amapLaneGuidance';

const guides: LaneGuide[] = [
  { at: 300, variants: [{ startHour: 0, endHour: 24, back: [1, 0, 3], front: [255, 0, 3] }] },
  { at: 800, variants: [{ startHour: 7, endHour: 9, back: [0, 4], front: [0, 255] }] },
];

describe('App lane guidance', () => {
  it('shows real route events only near their mapped position', () => {
    expect(upcomingLaneGuide(guides, 0, 8)?.distance).toBe(300);
    expect(upcomingLaneGuide(guides, 310, 8)?.distance).toBe(0);
    expect(upcomingLaneGuide(guides, 321, 8)).toBeUndefined();
    expect(upcomingLaneGuide(guides, 400, 10)).toBeUndefined();
    expect(upcomingLaneGuide(guides, 400, 8)?.at).toBe(800);
  });

  it('uses the App arrow variant for a recommended lane', () => {
    expect(laneArrowAsset(0, 0)).toBe('/amap/lane/front-0-0.svg');
    expect(laneArrowAsset(1, 255)).toBe('/amap/lane/back-1.svg');
  });
});
