import type { Object3D, Scene } from 'three';

/** Reuse the parked street's transforms while only the vehicle/effects animate. */
export function createSceneMatrixCache(scene: Scene) {
  const previousAutoUpdate = scene.matrixWorldAutoUpdate;
  scene.matrixWorldAutoUpdate = false;
  let dirty = true;
  return {
    invalidate() { dirty = true; },
    update(dynamicRoots?: readonly Object3D[]) {
      if (dirty) {
        // Include the root transform when rebuilding, even though automatic
        // renderer-wide traversal is disabled between invalidations.
        scene.matrixWorldAutoUpdate = true;
        try { scene.updateMatrixWorld(true); }
        finally { scene.matrixWorldAutoUpdate = false; }
        dirty = false;
      } else if (dynamicRoots) {
        for (const root of dynamicRoots) root.updateWorldMatrix(true, true);
      }
    },
    dispose() { scene.matrixWorldAutoUpdate = previousAutoUpdate; },
  };
}
