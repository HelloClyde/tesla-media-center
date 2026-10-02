import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { navigationSceneCenter, positionNavigationCamera } from './amapNavigationCamera';

function screenPosition(bearing: number, zoom: number, vehicle: [number, number], following: boolean, headingUp: boolean) {
  const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
  positionNavigationCamera(camera, bearing, zoom, vehicle, following, headingUp);
  camera.updateMatrixWorld();
  const projected = new THREE.Vector3(vehicle[0], 3, vehicle[1]).project(camera);
  return { x: (projected.x + 1) / 2, y: (1 - projected.y) / 2 };
}

describe('3D navigation camera', () => {
  it('loads the local ground around the followed vehicle instead of the shifted 2D center', () => {
    const mapCenter: [number, number] = [116.1, 39.1];
    const vehicle: [number, number] = [116.09, 39.09];
    expect(navigationSceneCenter(mapCenter, vehicle, true)).toBe(vehicle);
    expect(navigationSceneCenter(mapCenter, vehicle, false)).toBe(mapCenter);
  });
  it('keeps the vehicle above the footer when the 2D center is far ahead', () => {
    for (const bearing of [0, 90, 210]) {
      for (const zoom of [15.5, 17, 18]) {
        const position = screenPosition(bearing, zoom, [120, -90], true, true);
        expect(position.x).toBeCloseTo(.5, 4);
        expect(position.y).toBeGreaterThan(.58);
        expect(position.y).toBeLessThan(.66);
      }
    }
  });

  it('centers the vehicle in north-up follow mode', () => {
    expect(screenPosition(0, 17, [120, -90], true, false).y).toBeCloseTo(.49, 1);
  });

  it('keeps manual panning centered on the map instead of the vehicle', () => {
    const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    positionNavigationCamera(camera, 0, 17, [120, -90], false, true);
    expect(camera.position.x).toBeCloseTo(0);
    expect(camera.position.z).toBeCloseTo(170);
  });
});
