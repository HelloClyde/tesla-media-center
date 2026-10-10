import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { appLandscapeGuideFov, appLandscapeGuideMaxPitch, followCameraBearing, manualNavigationZoom, navigationSceneCenter, positionNavigationCamera, rebaseNavigationCamera } from './amapNavigationCamera';
import { mapSignsVisible } from './amapMapSigns';
import { groundPoint } from './teslaMapCoordinates';

function screenPosition(bearing: number, zoom: number, vehicle: [number, number], following: boolean, headingUp: boolean, navigating = false, aspect = 1.4) {
  const camera = new THREE.PerspectiveCamera(45, aspect, 1, 1400);
  positionNavigationCamera(camera, bearing, zoom, vehicle, following, headingUp, navigating);
  camera.updateMatrixWorld();
  const projected = new THREE.Vector3(vehicle[0], 3, vehicle[1]).project(camera);
  return { x: (projected.x + 1) / 2, y: (1 - projected.y) / 2 };
}

describe('3D navigation camera', () => {
  it('hides and restores icons using actual manual camera zoom in either orientation', () => {
    for (const headingUp of [true, false]) {
      const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
      const target = positionNavigationCamera(camera, 0, 17, [0, 0], true, headingUp);
      const distance = camera.position.distanceTo(target);
      const offset = camera.position.clone().sub(target);
      camera.position.copy(target).addScaledVector(offset, 2);
      const zoomedOut = manualNavigationZoom(17, distance, camera.position.distanceTo(target));
      expect(zoomedOut).toBeCloseTo(15);
      expect(mapSignsVisible(zoomedOut)).toBe(false);
      camera.position.copy(target).add(offset);
      expect(mapSignsVisible(manualNavigationZoom(17, distance, camera.position.distanceTo(target)))).toBe(true);
      // Orbiting and panning preserve the camera-target distance and visibility.
      target.add(new THREE.Vector3(200, 0, -120));
      camera.position.copy(target).add(new THREE.Vector3(distance, 0, 0));
      expect(manualNavigationZoom(17, distance, camera.position.distanceTo(target))).toBeCloseTo(17);
    }
  });
  it('keeps the base zoom when a manual camera distance is invalid', () => {
    for (const distance of [0, -1, Infinity, Number.NaN]) {
      expect(manualNavigationZoom(17, 200, distance)).toBe(17);
      expect(manualNavigationZoom(17, distance, 200)).toBe(17);
    }
  });
  it('lets the car visibly lead a turn while the camera follows by the shortest angle', () => {
    const firstFrame = followCameraBearing(0, 90, 33);
    expect(firstFrame).toBeGreaterThan(0);
    expect(firstFrame).toBeLessThan(15);
    let bearing = firstFrame;
    for (let i = 0; i < 120; i++) bearing = followCameraBearing(bearing, 90, 33);
    expect(bearing).toBeCloseTo(90, 0);
    expect(followCameraBearing(359, 1, 33)).toBeGreaterThan(359);
  });
  it('uses the APK main-map landscape navigation field of view', () => {
    expect(appLandscapeGuideFov(15)).toBe(36);
    expect(appLandscapeGuideFov(16)).toBeCloseTo(33.006, 3);
    expect(appLandscapeGuideFov(17)).toBeCloseTo(27.006, 3);
    expect(appLandscapeGuideFov(18)).toBeCloseTo(42.09, 2);
    expect(appLandscapeGuideFov(16.5)).toBeCloseTo(30.006, 3);
    expect(appLandscapeGuideFov(Number.NaN)).toBeCloseTo(27.006, 3);
    const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    positionNavigationCamera(camera, 0, 17, [0, 0], true, true);
    expect(camera.fov).toBeCloseTo(27.006, 3);
    positionNavigationCamera(camera, 0, 17, [0, 0], true, false);
    expect(camera.fov).toBeCloseTo(27.006, 3);
    positionNavigationCamera(camera, 0, 17, [0, 0], false, true);
    expect(camera.fov).toBeCloseTo(27.006, 3);
  });
  it('loads the local ground around the followed vehicle instead of the shifted 2D center', () => {
    const mapCenter: [number, number] = [116.1, 39.1];
    const vehicle: [number, number] = [116.09, 39.09];
    expect(navigationSceneCenter(mapCenter, vehicle, true)).toBe(vehicle);
    expect(navigationSceneCenter(mapCenter, vehicle, false)).toBe(mapCenter);
  });

  it('keeps the camera finite while a zoom update is unavailable', () => {
    const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    positionNavigationCamera(camera, 0, Number.NaN, [0, 0], true, true);
    expect(camera.position.toArray().every(Number.isFinite)).toBe(true);
  });

  it('keeps the lower-screen anchor while moving navigation right of the left guidance card', () => {
    for (const bearing of [0, 90, 210]) {
      for (const zoom of [15.5, 17, 18]) {
        const position = screenPosition(bearing, zoom, [120, -90], true, true, true);
        const targetY = .75 + .03 * Math.max(0, Math.min(1, (17 - zoom) / 1.5));
        expect(position.x).toBeCloseTo(.6, 4);
        expect(position.y).toBeGreaterThan(targetY - .04);
        expect(position.y).toBeLessThan(targetY + .04);
      }
    }
  });

  it('keeps the navigation offset stable across aspect ratios and either follow orientation', () => {
    for (const aspect of [1.2, 1.8, 2.5])
      for (const bearing of [0, 90, 210])
        for (const zoom of [15.5, 17, 18])
          for (const headingUp of [true, false]) {
            const position = screenPosition(bearing, zoom, [120, -90], true, headingUp, true, aspect);
            const centered = screenPosition(bearing, zoom, [120, -90], true, headingUp, false, aspect);
            expect(position.x).toBeCloseTo(.6, 4);
            expect(position.y).toBeCloseTo(centered.y, 4);
            expect(centered.x).toBeCloseTo(.5, 4);
          }
  });

  it('keeps a junction 110 metres ahead visible above the vehicle in a short landscape viewport', () => {
    const camera = new THREE.PerspectiveCamera(45, 760 / 600, 1, 1400);
    positionNavigationCamera(camera, 0, 17, [0, 0], true, true);
    camera.updateMatrixWorld();
    const junction = new THREE.Vector3(0, 0, -110).project(camera);
    const screenY = (1 - junction.y) / 2;
    expect(screenY).toBeGreaterThan(.16);
    expect(screenY).toBeLessThan(.5);
  });

  it('stays below the APK main-map navigation pitch ceiling', () => {
    for (const zoom of [14, 15.5, 16, 17, 18, 19])
      for (const [following, headingUp] of [[true, true], [true, false], [false, true]]) {
        const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
        const target = positionNavigationCamera(camera, 0, zoom, [0, 0], following, headingUp);
        const horizontal = Math.hypot(camera.position.x - target.x, camera.position.z - target.z);
        const pitch = THREE.MathUtils.radToDeg(Math.atan2(horizontal, camera.position.y - target.y));
        expect(pitch).toBeLessThanOrEqual(appLandscapeGuideMaxPitch(zoom) + .01);
      }
    expect(appLandscapeGuideMaxPitch(17)).toBe(54);
    expect(appLandscapeGuideMaxPitch(Number.NaN)).toBe(54);
  });

  it('moves the follow camera nearer the vehicle than the browsing camera', () => {
    const following = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    const browsing = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    positionNavigationCamera(following, 0, 17, [0, 0], true, true);
    positionNavigationCamera(browsing, 0, 17, [0, 0], false, true);
    expect(following.position.distanceTo(new THREE.Vector3())).toBeLessThan(browsing.position.distanceTo(new THREE.Vector3()));
  });

  it('centers the vehicle in north-up follow mode', () => {
    expect(screenPosition(0, 17, [120, -90], true, false).y).toBeCloseTo(.49, 1);
  });

  it('keeps manual panning centered on the map instead of the vehicle', () => {
    const camera = new THREE.PerspectiveCamera(45, 1.4, 1, 1400);
    positionNavigationCamera(camera, 0, 17, [120, -90], false, true, true);
    expect(camera.position.x).toBeCloseTo(0);
    expect(camera.position.z).toBeCloseTo(220);
  });

  it('rebases a panned camera without moving its geographic view', () => {
    const center: [number, number] = [120.27, 30.2];
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(180, 90, 55);
    const target = new THREE.Vector3(145, 0, 25);
    const beforeTarget = groundPoint(center, target.x, target.z);
    const beforeCamera = groundPoint(center, camera.position.x, camera.position.z);
    const next = rebaseNavigationCamera(camera, target, center);
    expect(next).toBeDefined();
    expect(target.x).toBeCloseTo(0, 3);
    expect(target.z).toBeCloseTo(0, 3);
    const afterTarget = groundPoint(next!, target.x, target.z);
    const afterCamera = groundPoint(next!, camera.position.x, camera.position.z);
    expect(afterTarget[0]).toBeCloseTo(beforeTarget[0], 8);
    expect(afterTarget[1]).toBeCloseTo(beforeTarget[1], 8);
    expect(afterCamera[0]).toBeCloseTo(beforeCamera[0], 7);
    expect(afterCamera[1]).toBeCloseTo(beforeCamera[1], 8);
    expect(rebaseNavigationCamera(camera, target, next!)).toBeUndefined();
  });
});
