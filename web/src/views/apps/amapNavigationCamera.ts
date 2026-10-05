import * as THREE from 'three';
import { groundOffset, groundPoint, type MapPoint } from './teslaMapCoordinates';

const MAIN_MAP_LANDSCAPE_FOV = [36, 36, 33.00600051879883, 27.006000518798828,
  42.09, 42.09, 42, 42, 42] as const; // APK mapprofile_1 levels 14–22
const MAIN_MAP_LANDSCAPE_MAX_PITCH = [40, 40, 50, 54, 70, 74, 76, 76, 76] as const;

export function navigationSceneCenter(center: MapPoint, position: MapPoint | undefined, following: boolean): MapPoint {
  return following && position ? position : center;
}

/** APK MainMapInitParam selects mapprofile_1; these are its landscape navigation FOV entries. */
function profileValue(values: readonly number[], zoom: number): number {
  if (!Number.isFinite(zoom)) return values[3];
  const level = Math.max(14, Math.min(22, Math.floor(zoom)));
  const next = Math.min(22, level + 1);
  return THREE.MathUtils.lerp(values[level - 14], values[next - 14],
    Math.max(0, Math.min(1, zoom - level)));
}

export function appLandscapeGuideFov(zoom: number): number {
  return profileValue(MAIN_MAP_LANDSCAPE_FOV, zoom);
}

/** APK mapprofile_1 CONFIG_TYPE_STATE_LANDSCAPE_NAVI MaxPitchAngle. */
export function appLandscapeGuideMaxPitch(zoom: number): number {
  return profileValue(MAIN_MAP_LANDSCAPE_MAX_PITCH, zoom);
}

/** Let the vehicle lead a turn before the heading-up camera catches up. */
export function followCameraBearing(current: number, heading: number, elapsedMs: number): number {
  const delta = ((heading - current + 540) % 360) - 180;
  const blend = 1 - 2 ** (-Math.max(0, Math.min(elapsedMs, 100)) / 450);
  return ((current + delta * blend) % 360 + 360) % 360;
}

/** Move the local origin while preserving the camera's geographic view. */
export function rebaseNavigationCamera(camera: THREE.Camera, target: THREE.Vector3, center: MapPoint, threshold = 120): MapPoint | undefined {
  if (Math.hypot(target.x, target.z) <= threshold) return;
  const nextCenter = groundPoint(center, target.x, target.z);
  const [east, south] = groundOffset(nextCenter, center);
  camera.position.x -= east; camera.position.z -= south;
  target.x -= east; target.z -= south;
  return nextCenter;
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
  const safeZoom = Number.isFinite(zoom) ? zoom : 17;
  const fov = appLandscapeGuideFov(safeZoom);
  if (camera.fov !== fov) { camera.fov = fov; camera.updateProjectionMatrix(); }
  const angle = bearing * Math.PI / 180;
  // The APK's landscape profile supplies FOV and a pitch ceiling; its trip
  // navigation layer also reserves screen space via DriveProjenterCenterPadding.
  // Our old 70 m follow distance filled a short landscape view with the road
  // immediately around the car, hiding even a turn 110 m ahead. Frame a longer
  // section of road and leave the vehicle below the useful forward view.
  const guidance = following && headingUp;
  const distance = guidance ? Math.max(135, Math.min(230, 160 * 2 ** ((17 - safeZoom) * .4)))
    : Math.max(150, Math.min(280, 220 * 2 ** ((17 - safeZoom) * .4)));
  const focusX = following ? vehicle[0] : 0;
  const focusZ = following ? vehicle[1] : 0;
  // Keep the car at the same screen anchor when the native FOV changes between
  // profile levels. Solve the perspective projection for the look-ahead point
  // instead of reusing a fixed look-ahead fraction from the old 32° camera.
  const speedZoom = Math.max(0, Math.min(1, (17 - safeZoom) / 1.5));
  let height = guidance ? distance * .48 : distance * .95;
  const desiredY = .75 + .03 * speedZoom;
  const carHeight = 3;
  const slope = (1 - 2 * desiredY) * Math.tan(THREE.MathUtils.degToRad(fov / 2));
  const lookAhead = (cameraHeight: number) => Math.max(0, Math.min(distance,
    (slope * (cameraHeight * (cameraHeight - carHeight) + distance ** 2) - carHeight * distance)
      / (carHeight - cameraHeight - slope * distance)));
  // The earlier low camera exceeded the native mapprofile pitch ceiling.
  // Raise it only as far as necessary, preserving the car's screen anchor.
  const maxPitch = THREE.MathUtils.degToRad(appLandscapeGuideMaxPitch(safeZoom));
  const exceedsPitch = (cameraHeight: number) => Math.atan2(distance + (guidance ? lookAhead(cameraHeight) : 0), cameraHeight) > maxPitch;
  if (exceedsPitch(height)) {
    let low = height, high = distance * 4;
    for (let i = 0; i < 16; i++) {
      const middle = (low + high) / 2;
      if (exceedsPitch(middle)) low = middle;
      else high = middle;
    }
    height = high;
  }
  const ahead = guidance ? lookAhead(height) : 0;
  camera.position.set(focusX - Math.sin(angle) * distance, height, focusZ + Math.cos(angle) * distance);
  const target = new THREE.Vector3(focusX + Math.sin(angle) * ahead, 0, focusZ - Math.cos(angle) * ahead);
  camera.lookAt(target);
  return target;
}
