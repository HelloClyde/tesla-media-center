import { describe, expect, it } from 'vitest';
import { remainingCongestionPath, routeCongestionRuns } from './amapRouteTraffic';
import type { AppRoute } from './amapNavigation';
import type { TrafficRoad } from './amapTrafficOverlay';

const route: AppRoute = {
  id: 0, path: [[116.4, 39.9], [116.401, 39.9]], breaks: [],
  steps: [{ start: 0, end: 1, road: '示例路' }], distance: 86, labels: [],
};

describe('navigation route traffic', () => {
  it('colors only matching congestion on the route and trims driven parts', () => {
    const roads: TrafficRoad[] = [
      { status: 3, name: '示例路', angle: 0, path: [[116.40035, 39.9], [116.40065, 39.9]] },
      { status: 2, name: '平行路', angle: 0, path: [[116.4, 39.9004], [116.401, 39.9004]] },
    ];
    const runs = routeCongestionRuns(route, roads);
    expect(runs).toHaveLength(1);
    expect(runs[0].status).toBe(3);
    expect(runs[0].start).toBeGreaterThan(0);
    expect(runs[0].end).toBeLessThan(90);
    expect(remainingCongestionPath(runs[0], runs[0].end)).toEqual([]);
    expect(remainingCongestionPath(runs[0], (runs[0].start + runs[0].end) / 2)[0][0]).toBeGreaterThan(runs[0].path[0][0]);
  });

  it('does not color a crossing road or traffic in the opposite direction', () => {
    const crossing: TrafficRoad = { status: 3, angle: 90, path: [[116.4005, 39.8998], [116.4005, 39.9002]] };
    const opposite: TrafficRoad = { status: 2, angle: 180, path: [[116.4, 39.9], [116.401, 39.9]] };
    expect(routeCongestionRuns(route, [crossing, opposite])).toEqual([]);
  });
});
