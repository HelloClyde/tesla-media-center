import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

// Tesla-owned assets are provisioned locally; the public repository keeps its CC-BY model as a fallback.
export const OFFICIAL_MODEL_URL = '/models/tesla-model-y-2020-2024.glb';
export const FALLBACK_MODEL_URL = '/models/2022_tesla_model_y.glb';
export const MANUAL_MODEL_STORAGE_KEY = 'tmc.tesla.manual-models';
export type VehicleModelVariant = 'model3-high' | 'model3-highland' | 'modely-high' | 'modely-juniper' |
  'modely-standard' | 'modely-long' | 'models-legacy' | 'models-palladium' | 'modelx-legacy' | 'modelx-palladium' | 'cybertruck' | 'semi' | 'unknown';

const assets: Record<Exclude<VehicleModelVariant, 'unknown'>, { url: string; root: string }> = {
  'model3-high': { url: '/models/tesla-model-3-2017-2023.glb', root: '3_High_Root' },
  'model3-highland': { url: '/models/tesla-model-3-2024-plus.glb', root: 'Poppyseed_Root' },
  'modely-high': { url: OFFICIAL_MODEL_URL, root: 'Y_High_Root' },
  'modely-juniper': { url: '/models/tesla-model-y-2025-plus.glb', root: 'Bayberry_Root' },
  'modely-standard': { url: '/models/tesla-model-y-2025-standard.glb', root: 'BayberryE41_Root' },
  'modely-long': { url: '/models/tesla-model-y-long.glb', root: 'BayberryE80_Root' },
  'models-legacy': { url: '/models/tesla-model-s-2012-2020.glb', root: 'S_Root' },
  'models-palladium': { url: '/models/tesla-model-s-2021-plus.glb', root: 'S_Palladium_Root' },
  'modelx-legacy': { url: '/models/tesla-model-x-2015-2020.glb', root: 'X_Root' },
  'modelx-palladium': { url: '/models/tesla-model-x-2021-plus.glb', root: 'X_Palladium_Root' },
  cybertruck: { url: '/models/tesla-cybertruck.glb', root: 'Cybertruck_Root' },
  semi: { url: '/models/tesla-semi.glb', root: 'Semi_Root' },
};

/** Prefer Tesla's vehicle_config.car_type; use VIN series/year when that is unavailable. */
export function vehicleModelVariant(vin?: string, carType?: string): VehicleModelVariant {
  const type = (carType || '').toLowerCase();
  if (/cybertruck/.test(type)) return 'cybertruck';
  if (/semi/.test(type)) return 'semi';
  if (/e80bayberry/.test(type)) return 'modely-long';
  if (/e41bayberry/.test(type)) return 'modely-standard';
  if (/bayberry/.test(type)) return 'modely-juniper';
  if (/poppyseed/.test(type)) return 'model3-highland';
  if (/lychee/.test(type)) return 'models-palladium';
  if (/tamarind/.test(type)) return 'modelx-palladium';
  const normalized = (vin || '').trim().toUpperCase();
  if (/palladium/.test(type) && normalized[3] === 'X') return 'modelx-palladium';
  if (/palladium/.test(type) && normalized[3] === 'S') return 'models-palladium';
  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(normalized)) {
    if (/^model\s*3$/.test(type)) return 'model3-high';
    if (/^model\s*y$/.test(type)) return 'modely-high';
    return 'unknown';
  }
  const year = 'HJKLMNPRST'.indexOf(normalized[9]);
  const modelYear = year < 0 ? 0 : 2017 + year;
  switch (normalized[3]) {
    case '3': return modelYear >= 2024 ? 'model3-highland' : 'model3-high';
    case 'Y': return modelYear >= 2025 ? 'modely-juniper' : 'modely-high';
    case 'S': return modelYear >= 2021 ? 'models-palladium' : 'models-legacy';
    case 'X': return modelYear >= 2021 ? 'modelx-palladium' : 'modelx-legacy';
    case 'C': return 'cybertruck';
    default: return 'unknown';
  }
}

export function resolvedVehicleModelVariant(vin?: string, carType?: string, manual?: unknown): Exclude<VehicleModelVariant, 'unknown'> {
  const detected = vehicleModelVariant(vin, carType);
  if (detected !== 'unknown') return detected;
  return typeof manual === 'string' && Object.prototype.hasOwnProperty.call(assets, manual)
    ? manual as Exclude<VehicleModelVariant, 'unknown'> : 'modely-high';
}

export function isOfficialVehicle(model: THREE.Object3D) {
  return Object.values(assets).some(asset => !!model.getObjectByName(asset.root));
}

export function vehicleModelVariantForObject(model: THREE.Object3D): VehicleModelVariant {
  return (Object.entries(assets).find(([, asset]) => !!model.getObjectByName(asset.root))?.[0] || 'unknown') as VehicleModelVariant;
}

export async function loadVehicleModel(loader: GLTFLoader, variant: VehicleModelVariant = 'modely-high'): Promise<GLTF> {
  const asset = assets[variant === 'unknown' ? 'modely-high' : variant];
  try {
    const response = await fetch(asset.url, { method: 'HEAD' });
    if (response.ok && !response.headers.get('content-type')?.includes('text/html')) {
      const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(asset.url);
      if (gltf.scene.getObjectByName(asset.root)) return gltf;
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
  for (const clip of clips.filter(item => /^(?:LF|LR|RF|RR)Door(?:Mirror)?Animation(?:Complete|Top|Bottom)?$/.test(item.name))) {
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
