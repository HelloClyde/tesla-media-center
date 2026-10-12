import { describe, expect, it } from 'vitest';
import type { AppRoute, Point } from './amapNavigation';
import { layoutRouteBubbles, previewRouteBounds, routePreviewSamples,
  ROUTE_BUBBLE_WIDTH, ROUTE_BUBBLE_HEIGHT, type RouteBubblePlacement } from './amapRoutePreview';

const route = (path: Point[]): AppRoute => ({ id: 0, path, breaks: [], labels: [], distance: 100, steps: [] });
const area = { left: 20, top: 70, right: 700, bottom: 510 };
const vertical = (x: number) => Array.from({ length: 65 }, (_, i) => ({ x, y: 80 + i * 6.5 }));
function assertVisibleAndSeparate(labels: RouteBubblePlacement[]) {
  for (const label of labels) {
    expect(label.x - ROUTE_BUBBLE_WIDTH / 2).toBeGreaterThanOrEqual(area.left);
    expect(label.x + ROUTE_BUBBLE_WIDTH / 2).toBeLessThanOrEqual(area.right);
    expect(label.y - ROUTE_BUBBLE_HEIGHT / 2).toBeGreaterThanOrEqual(area.top);
    expect(label.y + ROUTE_BUBBLE_HEIGHT / 2).toBeLessThanOrEqual(area.bottom);
  }
  for (let a = 0; a < labels.length; a++) for (let b = a + 1; b < labels.length; b++) {
    expect(Math.abs(labels[a].x - labels[b].x) >= ROUTE_BUBBLE_WIDTH
      || Math.abs(labels[a].y - labels[b].y) >= ROUTE_BUBBLE_HEIGHT).toBe(true);
  }
}

describe('multiple-route map preview', () => {
  it('includes the outer alternatives and endpoints, not just the selected path', () => {
    const routes = [route([[120, 30], [120.01, 30.01]]), route([[119.98, 30], [120.04, 30.03]])];
    expect(previewRouteBounds(routes, [[120, 29.99]])).toEqual([[119.98, 29.99], [120.04, 30.03]]);
    expect(previewRouteBounds([])).toBeUndefined();
  });

  it('bounds sampling work for large native paths and retains their extent', () => {
    const large = route(Array.from({ length: 20000 }, (_, i): Point => [120 + i / 1e6, 30]));
    const sampled = routePreviewSamples(large);
    expect(sampled).toHaveLength(65);
    expect(sampled[0]).toEqual(large.path[0]);
    expect(sampled[sampled.length - 1][0]).toBeCloseTo(large.path[large.path.length - 1][0], 8);
  });

  it('places three or four clear bubbles even when the paths share a trunk', () => {
    const three = layoutRouteBubbles([vertical(220), vertical(270), vertical(330)], area);
    expect(three).toHaveLength(3);
    assertVisibleAndSeparate(three);
    const four = layoutRouteBubbles(Array.from({ length: 4 }, () => vertical(300)), area);
    expect(four).toHaveLength(4);
    assertVisibleAndSeparate(four);
  });

  it('prefers an independent branch rather than the common endpoint segment', () => {
    const shared = vertical(300);
    const alternative = shared.map((point, i) => ({ ...point, x: i > 20 && i < 45 ? 460 : point.x }));
    const labels = layoutRouteBubbles([shared, alternative], area);
    expect(labels[1].anchor.x).toBe(460);
    assertVisibleAndSeparate(labels);
  });

  it('does not pin an off-screen route to an unrelated visible position', () => {
    expect(layoutRouteBubbles([vertical(-200)], area)).toEqual([]);
    expect(layoutRouteBubbles([vertical(200)], { ...area, bottom: 90 })).toEqual([]);
  });
});
