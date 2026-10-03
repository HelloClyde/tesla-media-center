import * as THREE from 'three';
import type { MapPoint } from './teslaMapCoordinates';

export function navigationSceneCenter(center: MapPoint, position: MapPoint | undefined, following: boolean): MapPoint {
  return following && position ? position : center;
}

/** Keep the 3D vehicle in the usable part of the screen, independently of Leaflet's 2D pan. */
export function positionNavigationCamera(
  camera: THREE.PerspectiveCamera,
  bearing: number,
  zoom: number,
  vehicle: readonly [number, number],
  following: boolean,
  headingUp: boolean,
) {
  const angle = bearing * Math.PI / 180;
  const distance = Math.max(95, Math.min(330, 170 * 2 ** (17 - zoom)));
  const focusX = following ? vehicle[0] : 0;
  const focusZ = following ? vehicle[1] : 0;
  // Looking a little ahead puts the vehicle near 62% of the canvas height.
  const ahead = following && headingUp ? distance * .24 : 0;
  camera.position.set(focusX - Math.sin(angle) * distance, distance * (zoom < 16 ? 1.1 : .95), focusZ + Math.cos(angle) * distance);
  camera.lookAt(focusX + Math.sin(angle) * ahead, 0, focusZ - Math.cos(angle) * ahead);
}
