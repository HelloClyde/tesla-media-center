import * as THREE from 'three';
import { vehicleModelVariantForObject, type VehicleModelVariant } from './teslaOfficialModel';

export type VehicleSkinVariant = Exclude<VehicleModelVariant, 'unknown'>;
const DATABASE = 'tmc-vehicle-skins';
const STORE = 'skins';

function openSkinDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function skinTransaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore, finish: (value: T) => void) => void): Promise<T> {
  const db = await openSkinDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    let value: T;
    transaction.oncomplete = () => { db.close(); resolve(value); };
    transaction.onerror = () => { db.close(); reject(transaction.error); };
    transaction.onabort = () => { db.close(); reject(transaction.error); };
    action(transaction.objectStore(STORE), result => { value = result; });
  });
}

function readLegacySkin(variant: VehicleSkinVariant): Promise<Blob | null> {
  return skinTransaction<Blob | null>('readonly', (store, finish) => {
    const request = store.get(variant);
    request.onsuccess = () => finish(request.result instanceof Blob ? request.result : null);
  });
}

function removeLegacySkin(variant: VehicleSkinVariant): Promise<void> {
  return skinTransaction<void>('readwrite', store => { store.delete(variant); });
}

const skinUrl = (variant: VehicleSkinVariant) => `/api/tesla/skins/${encodeURIComponent(variant)}`;

async function checkedJson(response: Response): Promise<void> {
  const result = await response.json().catch(() => null);
  if (!response.ok || result?.status !== 'ok') throw new Error(result?.message || (result?.status === 'need_login' ? '请先登录' : '服务器皮肤操作失败'));
}

export async function readVehicleSkin(variant: VehicleSkinVariant): Promise<Blob | null> {
  const response = await fetch(skinUrl(variant), { credentials: 'same-origin', cache: 'no-store' });
  if (response.status === 204) {
    // Migrate the previous browser-only skin once, without overwriting a server skin.
    const legacy = await readLegacySkin(variant).catch(() => null);
    if (!legacy) return null;
    if (!await saveVehicleSkin(variant, legacy, true)) return readVehicleSkin(variant);
    return legacy;
  }
  if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.message || (result?.status === 'need_login' ? '请先登录' : '服务器皮肤读取失败'));
  }
  return response.blob();
}

export async function saveVehicleSkin(variant: VehicleSkinVariant, blob: Blob, onlyIfMissing = false): Promise<boolean> {
  const response = await fetch(skinUrl(variant), {
    method: 'PUT', credentials: 'same-origin', body: blob,
    headers: { 'Content-Type': blob.type || 'application/octet-stream', ...(onlyIfMissing ? { 'If-None-Match': '*' } : {}) },
  });
  if (onlyIfMissing && response.status === 412) return false;
  await checkedJson(response);
  await removeLegacySkin(variant).catch(() => undefined);
  return true;
}

export async function removeVehicleSkin(variant: VehicleSkinVariant): Promise<void> {
  await checkedJson(await fetch(skinUrl(variant), { method: 'DELETE', credentials: 'same-origin' }));
  await removeLegacySkin(variant).catch(() => undefined);
}

export async function validateVehicleSkin(file: File): Promise<void> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('请选择 PNG、JPEG 或 WebP 图片');
  if (file.size > 10 * 1024 * 1024) throw new Error('贴图不能超过 10 MB');
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    const dimensions = await new Promise<[number, number]>((resolve, reject) => {
      image.onload = () => resolve([image.naturalWidth, image.naturalHeight]);
      image.onerror = () => reject(new Error('贴图无法读取'));
      image.src = url;
    });
    if (dimensions[0] !== dimensions[1] || dimensions[0] < 512 || dimensions[0] > 4096) throw new Error('请选择 512–4096 像素的正方形 UV 贴图');
  } finally { URL.revokeObjectURL(url); }
}

/** Apply a glTF UV atlas only to the matching official vehicle's body paint. */
export function createVehicleSkin(model: THREE.Object3D) {
  const paint = new Map<THREE.MeshStandardMaterial, { map: THREE.Texture | null; color: THREE.Color }>();
  const variant = vehicleModelVariantForObject(model);
  const isBodyPaint = (material: THREE.Material) => (material as THREE.MeshStandardMaterial).isMeshStandardMaterial
    && /^(?:PaintSkybox(?:2|_Original)?|PaintMix)$/.test(material.name);
  let usesSecondUv = false;
  if (variant !== 'unknown') model.traverse(object => {
    if (!(object as THREE.Mesh).isMesh) return;
    const mesh = object as THREE.Mesh;
    if (!mesh.geometry.getAttribute('uv1')) return;
    if ((Array.isArray(mesh.material) ? mesh.material : [mesh.material]).some(isBodyPaint)) usesSecondUv = true;
  });
  const uvAttribute = usesSecondUv ? 'uv1' : 'uv';
  const replacements: { mesh: THREE.Mesh; original: THREE.Material | THREE.Material[]; cloned: THREE.MeshStandardMaterial[] }[] = [];
  if (variant !== 'unknown') model.traverse(object => {
    if (!(object as THREE.Mesh).isMesh) return;
    const mesh = object as THREE.Mesh;
    if (!mesh.geometry.getAttribute(uvAttribute)) return;
    const original = mesh.material;
    const cloned: THREE.MeshStandardMaterial[] = [];
    const materials = (Array.isArray(original) ? original : [original]).map(material => {
      // PaintRough has repeating/out-of-range UVs; mapping the body atlas there creates black patches.
      if (!isBodyPaint(material)) return material;
      const body = (material as THREE.MeshStandardMaterial).clone();
      cloned.push(body);
      paint.set(body, { map: body.map, color: body.color.clone() });
      return body;
    });
    if (cloned.length) {
      mesh.material = Array.isArray(original) ? materials : materials[0];
      replacements.push({ mesh, original, cloned });
    }
  });
  let texture: THREE.Texture | null = null;
  let generation = 0;
  let disposed = false;
  return {
    variant,
    supported: paint.size > 0,
    get active() { return !!texture; },
    async set(blob: Blob | null) {
      const current = ++generation;
      let next: THREE.Texture | null = null;
      if (blob && paint.size) {
        const url = URL.createObjectURL(blob);
        try { next = await new THREE.TextureLoader().loadAsync(url); }
        finally { URL.revokeObjectURL(url); }
        // UV atlases often use transparent black outside the painted islands.
        // Flatten it to white before mipmapping so black does not bleed into seams.
        const image = next.image as HTMLImageElement | undefined;
        if (image?.width && image?.height && typeof document !== 'undefined') {
          const canvas = document.createElement('canvas');
          canvas.width = image.width; canvas.height = image.height;
          const context = canvas.getContext('2d');
          if (context) {
            context.fillStyle = '#ffffff';
            context.fillRect(0, 0, canvas.width, canvas.height);
            context.drawImage(image, 0, 0);
            next.dispose();
            next = new THREE.CanvasTexture(canvas);
          }
        }
        next.colorSpace = THREE.SRGBColorSpace;
        next.flipY = false; // glTF UV coordinates have already been transformed by GLTFLoader.
        next.channel = usesSecondUv ? 1 : 0;
        next.anisotropy = 4;
      }
      if (disposed || current !== generation) { next?.dispose(); return; }
      texture?.dispose();
      texture = next;
      paint.forEach((original, material) => {
        material.map = next || original.map;
        material.color.copy(next ? new THREE.Color('#ffffff') : original.color);
        material.needsUpdate = true;
      });
    },
    dispose() {
      disposed = true; generation++;
      paint.forEach((original, material) => {
        material.map = original.map;
        material.color.copy(original.color);
        material.needsUpdate = true;
      });
      texture?.dispose(); texture = null;
      replacements.forEach(({ mesh, original, cloned }) => {
        mesh.material = original;
        cloned.forEach(material => material.dispose());
      });
    },
  };
}
