import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { ribbonJoinNormal, roundedRoutePoints, routeRibbonCutProgress, trimRouteRibbon } from './amapRouteRibbon';
import { groundOffset, groundPoint, type MapPoint } from './teslaMapCoordinates';

function quad(from: number, to: number) {
  return [from, 1, 1, to, 1, 1, from, 1, -1,
    from, 1, -1, to, 1, 1, to, 1, -1];
}

describe('3D route ribbon progress', () => {
  it('does not erase the line under a car still animating toward the latest route progress', () => {
    const origin: MapPoint = [120, 30];
    const route = { id: 1, path: [origin, groundPoint(origin, 0, 100)],
      steps: [], breaks: [], distance: 100, labels: [] };
    const carAt30 = groundPoint(origin, 0, 30);
    const carAt60 = groundPoint(origin, 0, 60);
    expect(routeRibbonCutProgress(route, 80, carAt30)).toBeCloseTo(22, 0);
    expect(routeRibbonCutProgress(route, 80, carAt60)).toBeCloseTo(52, 0);
    expect(routeRibbonCutProgress(route, 80)).toBe(72);
  });

  it('rounds a right-angle turn and gives both quads the same joined edge', () => {
    const origin: MapPoint = [120, 30];
    const route = { id: 1, path: [groundPoint(origin,0,50),origin,groundPoint(origin,50,0)],
      steps: [], breaks: [], distance: 100, labels: [] };
    const points = roundedRoutePoints(route, origin);
    expect(points.length).toBeGreaterThan(3);
    const middle = points.slice(1,-1).map(item => groundOffset(item.point,origin));
    expect(middle.some(([x,z]) => x > 0 && z > 0)).toBe(true);
    const east: MapPoint = [0,1], north: MapPoint = [-1,0];
    const one = ribbonJoinNormal(east,north), other = ribbonJoinNormal(north,east);
    expect(one).toEqual(other);
    expect(Math.hypot(...one)).toBeCloseTo(Math.SQRT2,4);
  });

  it('keeps route breaks disconnected instead of rounding across them', () => {
    const origin: MapPoint = [120,30];
    const route = { id: 1, path: [groundPoint(origin,0,50),origin,groundPoint(origin,50,0)],
      steps: [], breaks: [2], distance: 50, labels: [] };
    const points = roundedRoutePoints(route,origin);
    expect(points).toHaveLength(3);
    expect(points[1].section).not.toBe(points[2].section);
  });

  it('bridges a short step gap through the intersection without making a straight diagonal', () => {
    const origin: MapPoint = [120,30];
    const route = { id: 1, path: [groundPoint(origin,0,30),groundPoint(origin,0,10),
      groundPoint(origin,10,0),groundPoint(origin,30,0)],
      steps: [], breaks: [2], distance: 40, labels: [] };
    const points = roundedRoutePoints(route,origin);
    expect(new Set(points.map(point=>point.section)).size).toBe(1);
    expect(points.length).toBeGreaterThan(route.path.length);
    const bend = points.slice(2,-1).map(item=>groundOffset(item.point,origin));
    expect(bend.some(([x,z])=>x>0 && x<10 && z>0 && z<10 && x+z<8)).toBe(true);
  });

  it('cuts through the current quad and restores it after a backward position correction', () => {
    const original = new Float32Array([...quad(0, 10), ...quad(10, 20)]);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(original.slice(), 3));
    const spans = [{start: 0, end: 10}, {start: 10, end: 20}];
    const x = (vertex: number) => geometry.getAttribute('position').getX(vertex);

    trimRouteRibbon(geometry, spans, original, 5);
    expect(geometry.drawRange).toMatchObject({start: 0, count: 12});
    expect([x(0), x(2), x(3)]).toEqual([5, 5, 5]);

    trimRouteRibbon(geometry, spans, original, 15);
    expect(geometry.drawRange).toMatchObject({start: 6, count: 6});
    expect([x(6), x(8), x(9)]).toEqual([15, 15, 15]);

    trimRouteRibbon(geometry, spans, original, 2);
    expect(geometry.drawRange).toMatchObject({start: 0, count: 12});
    expect([x(0), x(2), x(3)]).toEqual([2, 2, 2]);
    expect([x(6), x(8), x(9)]).toEqual([10, 10, 10]);

    trimRouteRibbon(geometry, spans, original, 20);
    expect(geometry.drawRange.count).toBe(0);
    geometry.dispose();
  });
});
