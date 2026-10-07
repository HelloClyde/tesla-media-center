import * as T from 'three';
import { isOfficialVehicle } from './teslaOfficialModel';

function createOfficialVehicleWipers(model: T.Object3D) {
  const bounds = model.userData.windshieldBounds as T.Box3 | undefined;
  const halfWidth = Math.min(.62, (bounds?.max.x ?? .68) - .08);
  const y = (bounds?.min.y ?? 1.1) + .025;
  const z = (bounds?.min.z ?? -1.18) + .035;
  const bladeMaterial = new T.MeshStandardMaterial({ color: '#101316', roughness: .9, metalness: .1 });
  const pivots = [-1, 1].map((side, index) => {
    const pivot = new T.Group(); pivot.name = `Wiper_pivot_${index}`;
    pivot.position.set(side * halfWidth, y, z);
    const length = halfWidth * .93;
    const blade = new T.Mesh(new T.CylinderGeometry(.008, .008, length, 6), bladeMaterial);
    blade.rotation.z = Math.PI / 2;
    blade.position.x = -side * length / 2;
    blade.name = `Wiper_blade_${index}`;
    pivot.add(blade); model.add(pivot);
    return pivot;
  });
  const axis = new T.Vector3(0, .9, -.44).normalize();
  let phase = 0;
  return {
    update(dt: number, raining: boolean) {
      const wasMoving = phase > 0;
      if (raining || wasMoving) {
        phase += Math.max(0, dt) / 1.15;
        if (phase >= 1) phase = raining ? phase % 1 : 0;
      }
      const sweep = (1 - Math.cos(phase * Math.PI * 2)) / 2;
      pivots.forEach((pivot, i) => pivot.quaternion.setFromAxisAngle(axis, (i === 0 ? -1 : 1) * sweep * 1.18));
      return raining || wasMoving;
    },
  };
}

/** Extract the two connected wiper assemblies once; animate only their pivots. */
export function createVehicleWipers(model: T.Object3D) {
  if (isOfficialVehicle(model)) return createOfficialVehicleWipers(model);
  model.updateMatrixWorld(true);
  const inverse = model.matrixWorld.clone().invert();
  const sources: T.Mesh[] = [];
  model.traverse(object => {
    const mesh = object as T.Mesh;
    if (mesh.isMesh && !Array.isArray(mesh.material) && mesh.material.name === 'Wiper_Matte_Black') sources.push(mesh);
  });
  const pivots = [new T.Group(), new T.Group()];
  pivots[0].position.set(.58657, 1.04618, 1.27415);
  pivots[1].position.set(-.01434, 1.0456, 1.36272);
  pivots.forEach((pivot, i) => { pivot.name = `Wiper_pivot_${i}`; model.add(pivot); });
  for (const source of sources) {
    const geometry = source.geometry.index ? source.geometry.toNonIndexed() : source.geometry.clone();
    // Meshopt may leave normalized integer attributes: transform float copies.
    for (const name of ['position', 'normal']) {
      const attribute = geometry.getAttribute(name);
      if (!attribute) continue;
      const values = new Float32Array(attribute.count * attribute.itemSize);
      for (let i = 0; i < attribute.count; i++) for (let c = 0; c < attribute.itemSize; c++) values[i * attribute.itemSize + c] = attribute.getComponent(i, c);
      geometry.setAttribute(name, new T.BufferAttribute(values, attribute.itemSize));
    }
    geometry.applyMatrix4(new T.Matrix4().multiplyMatrices(inverse, source.matrixWorld));
    const position = geometry.getAttribute('position');
    const parents = Array.from({ length: position.count / 3 }, (_, i) => i);
    const find = (i: number): number => parents[i] === i ? i : (parents[i] = find(parents[i]));
    const owners = new Map<string, number>();
    for (let i = 0; i < position.count; i++) {
      const key = [position.getX(i), position.getY(i), position.getZ(i)].map(v => Math.round(v * 10000)).join(',');
      const triangle = Math.floor(i / 3), previous = owners.get(key);
      if (previous !== undefined) parents[find(triangle)] = find(previous);
      else owners.set(key, triangle);
    }
    const components = new Map<number, { indices: number[]; box: T.Box3 }>();
    for (let i = 0; i < position.count; i++) {
      const root = find(Math.floor(i / 3));
      let part = components.get(root);
      if (!part) { part = { indices: [], box: new T.Box3() }; components.set(root, part); }
      part.indices.push(i);
      part.box.expandByPoint(new T.Vector3().fromBufferAttribute(position, i));
    }
    const indices: number[][] = [[], [], []];
    for (const part of components.values()) {
      // Small spindle bases stay attached to the cowl.
      const width = part.box.max.x - part.box.min.x;
      const slot = width < .05 ? 2 : part.box.getCenter(new T.Vector3()).x > .05 ? 0 : 1;
      indices[slot].push(...part.indices);
    }
    indices.forEach((subset, slot) => {
      if (!subset.length) return;
      const extracted = new T.BufferGeometry();
      for (const name of Object.keys(geometry.attributes)) {
        const attribute = geometry.getAttribute(name);
        const values = new Float32Array(subset.length * attribute.itemSize);
        subset.forEach((index, target) => {
          for (let c = 0; c < attribute.itemSize; c++) values[target * attribute.itemSize + c] = attribute.getComponent(index, c);
        });
        extracted.setAttribute(name, new T.BufferAttribute(values, attribute.itemSize));
      }
      if (slot < 2) extracted.translate(-pivots[slot].position.x, -pivots[slot].position.y, -pivots[slot].position.z);
      const mesh = new T.Mesh(extracted, source.material);
      mesh.name = slot < 2 ? `Wiper_blade_${slot}` : 'Wiper_fixed_bases';
      mesh.castShadow = true;
      if (slot === 2) mesh.position.set(0, .03, -.08);
      (slot < 2 ? pivots[slot] : model).add(mesh);
    });
    geometry.dispose();
    source.removeFromParent();
    source.geometry.dispose();
  }
  // The source mesh parks just in front of the windshield lower edge.
  // Move the assembly onto the glass so a swept blade cannot cross the hood.
  pivots.forEach(pivot => pivot.position.add(new T.Vector3(0, .03, -.08)));
  const axis = new T.Vector3(0, .85, .52).normalize();
  let phase = 0;
  return {
    update(dt: number, raining: boolean) {
      const wasMoving = phase > 0;
      if (raining || wasMoving) {
        phase += Math.max(0, dt) / 1.15;
        if (phase >= 1) phase = raining ? phase % 1 : 0;
      }
      const sweep = (1 - Math.cos(phase * Math.PI * 2)) / 2;
      pivots.forEach((pivot, i) => pivot.quaternion.setFromAxisAngle(axis, -sweep * (i === 0 ? 1.22 : 1.30)));
      // Include the final parked frame after rain stops.
      return raining || wasMoving;
    },
  };
}
