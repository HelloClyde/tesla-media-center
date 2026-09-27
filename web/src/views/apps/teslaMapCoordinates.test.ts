import { describe, it, expect } from 'vitest';
import { vehicleMapPoint, groundOffset, groundBounds } from './teslaMapCoordinates';

describe('vehicle/map alignment', () => {
  it('rejects absent and invalid positions instead of moving to an example city', () => {
    for (const sample of [null, {}, { longitude: null, latitude: 30 }, { longitude: 0, latitude: 0 }, { longitude: 'bad', latitude: 30 }, { longitude: 181, latitude: 30 }]) expect(vehicleMapPoint(sample)).toBeUndefined();
  });
  it('preserves GCJ coordinates and converts GPS exactly once', () => {
    const sample = { longitude: 116.397, latitude: 39.908 };
    expect(vehicleMapPoint({ ...sample, coord_type: 'gcj02' })).toEqual([116.397, 39.908]);
    expect(vehicleMapPoint(sample)?.[0]).toBeGreaterThan(116.4);
  });
  it('uses metric east/south axes and bounds with the same origin', () => {
    const origin: [number, number] = [116.397, 39.908];
    const [west, north, east, south] = groundBounds(origin, 300);
    expect(groundOffset([east, north], origin)[0]).toBeCloseTo(300, 6);
    expect(groundOffset([east, north], origin)[1]).toBeCloseTo(-300, 6);
    expect(groundOffset([west, south], origin)[0]).toBeCloseTo(-300, 6);
    expect(groundOffset([west, south], origin)[1]).toBeCloseTo(300, 6);
  });
});
