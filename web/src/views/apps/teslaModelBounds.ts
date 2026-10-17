import * as THREE from 'three';

/** Visible geometry bounds in the car's authored coordinates, before root transforms. */
export function vehicleLocalBounds(model: THREE.Object3D) {
  model.updateWorldMatrix(true, true);
  const inverseModel = model.matrixWorld.clone().invert();
  const bounds = new THREE.Box3();
  const box = new THREE.Box3();
  const transform = new THREE.Matrix4();
  const include = (object: THREE.Object3D) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || !mesh.geometry) return;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    if (!materials.some(material => material.visible)) return;
    if (mesh instanceof THREE.InstancedMesh) {
      if (!mesh.boundingBox) mesh.computeBoundingBox();
      box.copy(mesh.boundingBox!);
    } else {
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
      box.copy(mesh.geometry.boundingBox!);
    }
    transform.multiplyMatrices(inverseModel, mesh.matrixWorld);
    bounds.union(box.applyMatrix4(transform));
  };
  // Union in vehicle coordinates: inverting a world AABB after rotation inflates
  // it, while hidden body/wheel variants must not affect attached lamps or jets.
  model.traverseVisible(include);
  if (bounds.isEmpty()) model.traverse(include);
  return bounds;
}
