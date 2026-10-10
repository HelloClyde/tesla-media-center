import * as THREE from 'three';
import axios from 'axios';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';
import { forgetMapModel, readMapModel, storeMapModel } from './amapBrowserTileCache';

type Landmark = { id: string; position: MapPoint; bounds: number[]; model: string;
  rotationDegrees: number; scale: number };
type Loaded = { point: MapPoint; bounds: number[]; day: THREE.Group; night: THREE.Group | undefined; holder: THREE.Group };

/** GLTF day/night scenes may share buffers and textures; release each once. */
export function disposeGltfScenes(scenes: THREE.Object3D[]) {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  for (const scene of scenes) scene.traverse(child => {
    if (!(child as THREE.Mesh).isMesh) return;
    const mesh = child as THREE.Mesh;
    geometries.add(mesh.geometry);
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      materials.add(material);
      for (const value of Object.values(material)) {
        if ((value as THREE.Texture | undefined)?.isTexture) textures.add(value as THREE.Texture);
      }
    }
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  for (const texture of textures) texture.dispose();
}

/** App index-model assets; the GLB contains its original geometry and day/night KTX2 textures. */
export function createAmapLandmarks(renderer: THREE.WebGLRenderer, onBounds: (bounds: number[][]) => void) {
  const group = new THREE.Group();
  const ktx2 = new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer);
  const loader = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);
  const loaded = new Map<string, Loaded>();
  let anchor: MapPoint = [0, 0], requested: MapPoint | undefined;
  let theme: 'day' | 'night' = 'day', generation = 0, disposed = false, pending = false, attemptedAt = 0;
  let allowQueries = true;
  let queryController: AbortController | undefined;
  const modelControllers = new Set<AbortController>();

  function release(entry: Loaded) {
    disposeGltfScenes([entry.day, ...(entry.night ? [entry.night] : [])]);
    entry.holder.removeFromParent();
  }

  function choose(entry: Loaded) {
    entry.holder.clear();
    entry.holder.add(theme === 'night' && entry.night ? entry.night : entry.day);
  }
  function position() {
    let removed = false;
    for (const [id, entry] of loaded) {
      const [x, z] = groundOffset(entry.point, anchor);
      if (Math.abs(x) > 900 || Math.abs(z) > 900) { release(entry); loaded.delete(id); removed = true; continue; }
      entry.holder.position.set(x, 0, z);
      entry.holder.visible = Math.abs(x) < 500 && Math.abs(z) < 500;
    }
    if (removed) onBounds([...loaded.values()].map(entry => entry.bounds));
  }
  async function loadOne(item: Landmark, token: number) {
    if (loaded.has(item.id) || !/^[0-9]{1,19}-[0-9a-f]{12}\.glb$/.test(item.model) ||
        !Number.isFinite(item.rotationDegrees) || !Number.isFinite(item.scale) || item.scale <= 0) return;
    const base = '/api/amap-app/landmarks/';
    const cached = await readMapModel(item.model);
    if (disposed || token !== generation) return;
    let gltf: Awaited<ReturnType<typeof loader.parseAsync>> | undefined;
    if (cached) {
      try { gltf = await loader.parseAsync(cached, base); }
      catch { await forgetMapModel(item.model); }
    }
    if (!gltf) {
      const controller = new AbortController();
      modelControllers.add(controller);
      let data: ArrayBuffer;
      try {
        const response = await axios.get<ArrayBuffer>(`${base}${item.model}`, {
          responseType: 'arraybuffer', timeout: 45000, signal: controller.signal,
        });
        data = response.data;
      } finally { modelControllers.delete(controller); }
      if (disposed || token !== generation) return;
      gltf = await loader.parseAsync(data, base);
      void storeMapModel(item.model, data);
    }
    if (disposed || token !== generation) {
      disposeGltfScenes(gltf.scenes);
      return;
    }
    const day = gltf.scenes[0], night = gltf.scenes[1];
    if (!day) { disposeGltfScenes(gltf.scenes); return; }
    const holder = new THREE.Group();
    // App model coordinates use a longitude-sized local plane. The geographic
    // index confirms a uniform cos(latitude) correction before display.
    holder.scale.setScalar(item.scale * Math.cos(item.position[1] * Math.PI / 180));
    holder.rotation.y = item.rotationDegrees * Math.PI / 180;
    const entry = { point: item.position, bounds: item.bounds, day, night, holder };
    loaded.set(item.id, entry);
    choose(entry);
    group.add(holder);
    position();
    onBounds([...loaded.values()].map(value => value.bounds));
  }
  async function query(point: MapPoint) {
    for (const controller of modelControllers) controller.abort();
    modelControllers.clear();
    pending = true;
    const token = ++generation;
    const controller = new AbortController();
    queryController = controller;
    try {
      const response = await axios.get('/api/amap-app/landmarks', {
        params: { lon: point[0], lat: point[1], radius: 400 }, timeout: 70000,
        signal: controller.signal,
      });
      if (disposed || token !== generation || response.data?.status !== 'ok') return;
      const items: Landmark[] = response.data.data?.models || [];
      await Promise.allSettled(items.map(item => loadOne(item, token)));
    } catch { /* Ordinary BMD buildings remain available when landmark assets fail. */ }
    finally {
      if (token === generation) {
        pending = false;
        queryController = undefined;
        // The car can leave the queried area while a GLB is downloading.
        // Fetch the newest area even if no further position event arrives.
        if (!disposed && allowQueries && Math.hypot(...groundOffset(point, anchor)) > 180) {
          requested = [...anchor];
          attemptedAt = Date.now();
          void query([...anchor]);
        }
      }
    }
  }
  return {
    group,
    update(point: MapPoint, nextTheme: 'day' | 'night', allowQuery = true) {
      if (disposed) return;
      allowQueries = allowQuery;
      anchor = point;
      if (theme !== nextTheme) {
        theme = nextTheme;
        for (const entry of loaded.values()) choose(entry);
      }
      position();
      if (allowQuery && !pending && (!requested || Math.hypot(...groundOffset(requested, point)) > 180 ||
          Date.now() - attemptedAt > 60000)) {
        requested = [...point];
        attemptedAt = Date.now();
        void query(point);
      }
    },
    dispose() {
      disposed = true; generation++;
      queryController?.abort(); queryController = undefined;
      for (const controller of modelControllers) controller.abort();
      modelControllers.clear();
      for (const entry of loaded.values()) release(entry);
      loaded.clear(); group.clear(); ktx2.dispose();
      onBounds([]);
    },
  };
}
