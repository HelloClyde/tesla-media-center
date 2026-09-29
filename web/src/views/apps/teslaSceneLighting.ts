import * as THREE from 'three';

export const VEHICLE_SUN_DIRECTION = new THREE.Vector3(-6, 9, 4).normalize();

export function configureStreetSun(light: THREE.DirectionalLight) {
  // The former 12 m / 30 m frustum excluded buildings and most tree crowns.
  // Cover nearby facades as well as their shadows on the road in every orbit view.
  light.position.copy(VEHICLE_SUN_DIRECTION).multiplyScalar(85);
  light.castShadow = true;
  light.shadow.mapSize.set(2048, 2048);
  Object.assign(light.shadow.camera, { left: -34, right: 34, top: 34, bottom: -34, near: 1, far: 160 });
  light.shadow.camera.updateProjectionMatrix();
  light.shadow.normalBias = .035;
  light.shadow.bias = -.00004;
  light.shadow.radius = 2;
}

export function applyStreetLighting(scene: THREE.Scene, sun: THREE.DirectionalLight, fill: THREE.HemisphereLight, night: boolean) {
  scene.environmentIntensity = night ? .025 : .16;
  sun.color.set(night ? '#a3baff' : '#fff0db');
  sun.intensity = night ? .16 : 2.8;
  fill.color.set('#c6ddf4');
  fill.groundColor.set('#534a40');
  fill.intensity = night ? .12 : .24;
}
