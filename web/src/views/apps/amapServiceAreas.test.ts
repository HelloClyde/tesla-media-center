import { describe, expect, it } from 'vitest';
import { upcomingServiceAreas, shouldAnnounceServiceArea } from './amapServiceAreas';
import type { AppRoute } from './amapNavigation';

const route: AppRoute = { id: 0, labels: [], breaks: [], distance: 0,
  path: [[120, 30], [120.01, 30], [120.02, 30], [120.03, 30], [120.04, 30]],
  steps: [
    { start: 0, end: 1, road: 'G60' },
    { start: 1, end: 2, road: 'G60', serviceArea: '长安服务区' },
    { start: 2, end: 3, road: 'G60', serviceArea: '长安服务区' },
    { start: 3, end: 4, road: 'G60', serviceArea: '嘉兴服务区' },
  ] };

describe('service areas on a driving route', () => {
  it('groups adjacent labels and removes passed areas', () => {
    const first = upcomingServiceAreas(route, 0);
    expect(first.map(area => area.name)).toEqual(['长安服务区', '嘉兴服务区']);
    expect(first[0].to).toBeGreaterThan(first[0].from);
    expect(upcomingServiceAreas(route, first[0].to + 1).map(area => area.name)).toEqual(['嘉兴服务区']);
  });

  it('warns once near the range and yields to an imminent turn', () => {
    const area = upcomingServiceAreas(route, 0)[0];
    expect(shouldAnnounceServiceArea(area, 0, 900)).toBe(true);
    expect(shouldAnnounceServiceArea(area, 0, 100)).toBe(false);
    expect(shouldAnnounceServiceArea(area, area.from + 400, 900)).toBe(false);
  });
});
