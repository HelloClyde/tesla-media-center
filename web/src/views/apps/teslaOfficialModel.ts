import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

// Tesla-owned asset: provision locally; the public repository keeps its CC-BY model as a fallback.
export const OFFICIAL_MODEL_URL = '/models/tesla-model-y-2020-2024.glb';
export const FALLBACK_MODEL_URL = '/models/2022_tesla_model_y.glb';

export function isOfficialVehicle(model: THREE.Object3D) {
  return !!model.getObjectByName('ModelY_High');
}

export async function loadVehicleModel(loader: GLTFLoader): Promise<GLTF> {
  try {
    const response = await fetch(OFFICIAL_MODEL_URL, { method: 'HEAD' });
    if (response.ok && !response.headers.get('content-type')?.includes('text/html')) {
      const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(OFFICIAL_MODEL_URL);
      if (isOfficialVehicle(gltf.scene)) return gltf;
    }
  } catch (error) {
    console.warn('Tesla vehicle asset unavailable; using the bundled model', error);
  }
  return loader.loadAsync(FALLBACK_MODEL_URL);
}

export function prepareOfficialVehicle(model: THREE.Object3D) {
  if (!isOfficialVehicle(model)) return false;
  model.updateWorldMatrix(true, true);
  const defrost = model.getObjectByName('Defrost_Front');
  if (defrost) model.userData.windshieldBounds = new THREE.Box3().setFromObject(defrost);
  // These are the phone app's studio floor and projected light quads, not car parts.
  for (const name of ['Floor', 'Headlights_Projections', 'Taillights_Projection', 'Defrost_Front', 'Defrost_Rear']) {
    model.getObjectByName(name)?.removeFromParent();
  }
  return true;
}

type DoorTrack = {
  node: THREE.Object3D;
  property: 'quaternion' | 'position' | 'scale';
  duration: number;
  interpolant: THREE.Interpolant;
};

/** Sample Tesla's authored hinge/mirror animations without an always-running mixer. */
export function createOfficialDoorController(model: THREE.Object3D, clips: THREE.AnimationClip[]) {
  const tracks: DoorTrack[] = [];
  for (const clip of clips.filter(item => /^(?:LF|LR|RF|RR)Door(?:Mirror)?Animation$/.test(item.name))) {
    for (const track of clip.tracks) {
      const separator = track.name.lastIndexOf('.');
      if (separator < 0) continue;
      const node = model.getObjectByName(track.name.slice(0, separator));
      const property = track.name.slice(separator + 1);
      if (!node || !['quaternion', 'position', 'scale'].includes(property)) continue;
      const interpolant = (track as THREE.KeyframeTrack & { createInterpolant(): THREE.Interpolant }).createInterpolant();
      tracks.push({ node, property: property as DoorTrack['property'], duration: clip.duration, interpolant });
    }
  }
  let progress = 0;
  return {
    update(dt: number, open: boolean) {
      const target = open ? 1 : 0;
      progress = THREE.MathUtils.damp(progress, target, 8, dt);
      if (Math.abs(progress - target) < 0.001) progress = target;
      for (const { node, property, duration, interpolant } of tracks) {
        const value = interpolant.evaluate(progress * duration);
        if (property === 'quaternion') node.quaternion.fromArray(value).normalize();
        else node[property].fromArray(value);
      }
      return progress !== target;
    },
    moving(open: boolean) { return Math.abs(progress - (open ? 1 : 0)) >= 0.001; },
    count: tracks.length,
  };
}
