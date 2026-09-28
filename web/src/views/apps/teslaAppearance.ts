import * as THREE from 'three';
function smoothPaintNormals(geometry: THREE.BufferGeometry) {
  const result = geometry.clone();
  const positions = result.getAttribute('position'), original = result.getAttribute('normal'), indices = result.index;
  if (!original) return result;
  const adjacent = new Map<string, THREE.Vector3[]>();
  const key = (i: number) => [positions.getX(i), positions.getY(i), positions.getZ(i)].map(n => Math.round(n * 100000)).join(',');
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i = 0; i < (indices?.count ?? positions.count); i += 3) {
    const ids = [0, 1, 2].map(j => indices ? indices.getX(i + j) : i + j);
    a.fromBufferAttribute(positions, ids[0]); b.fromBufferAttribute(positions, ids[1]); c.fromBufferAttribute(positions, ids[2]);
    const normal = b.sub(a).cross(c.sub(a)).clone();
    if (normal.lengthSq() < 1e-20) continue;
    for (const id of ids) { const k = key(id); const faces = adjacent.get(k) ?? []; faces.push(normal); adjacent.set(k, faces); }
  }
  const normals = original.clone(), reference = new THREE.Vector3(), sum = new THREE.Vector3();
  for (let i = 0; i < positions.count; i++) {
    reference.fromBufferAttribute(original, i).normalize(); sum.set(0, 0, 0);
    for (const face of adjacent.get(key(i)) ?? []) {
      if (reference.dot(face) > .5 * face.length()) sum.add(face);
    }
    if (sum.lengthSq() > 1e-20) { sum.normalize(); normals.setXYZ(i, sum.x, sum.y, sum.z); }
  }
  result.setAttribute('normal', normals);
  return result;
}

export const APPEARANCE_KEY = 'tmc.tesla.appearance.v1';
export const paintFinishes = [
  { value: 'gloss', label: '亮面', metalness: .15, roughness: .2, clearcoat: 1, clearcoatRoughness: .12 },
  { value: 'metallic', label: '金属', metalness: .8, roughness: .28, clearcoat: .8, clearcoatRoughness: .18 },
  { value: 'matte', label: '磨砂', metalness: .05, roughness: .88, clearcoat: 0, clearcoatRoughness: .9 },
  { value: 'satin', label: '缎面', metalness: .25, roughness: .52, clearcoat: .2, clearcoatRoughness: .5 },
];
export const defaultAppearance = { finish: 'gloss', color: '#eaf0f3', plate: 'TMC', plateStyle: 'green' };
export type VehicleAppearance = typeof defaultAppearance;
export function normalizeAppearance(value: Partial<VehicleAppearance> | null): VehicleAppearance {
  return {
    finish: paintFinishes.some(item => item.value === value?.finish) ? value!.finish! : defaultAppearance.finish,
    color: /^#[\da-f]{6}$/i.test(value?.color || '') ? value!.color! : defaultAppearance.color,
    plate: typeof value?.plate === 'string' ? Array.from(value.plate.normalize('NFKC').toUpperCase().replace(/[\s\u0000-\u001f\u007f]/g, '')).slice(0, 10).join('') : 'TMC',
    plateStyle: ['green', 'blue', 'black', 'white'].includes(value?.plateStyle || '') ? value!.plateStyle! : 'green',
  };
}

/** Own one dynamic texture shared by the two Blender-authored plate faces. */
export function createVehicleAppearance(model: THREE.Object3D) {
  const paint = new Set<THREE.MeshStandardMaterial>();
  const plates = new Set<THREE.MeshStandardMaterial>();
  model.traverse(obj => {
    if (!(obj as THREE.Mesh).isMesh) return;
    const mesh = obj as THREE.Mesh;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    // Rebuild paint normals across duplicated UV vertices; preserve body creases.
    // GLTF primitives have independent geometry, so glass, trim and wheels stay intact.
    if (materials.length && materials.every(m => m.name === 'Pearl_White_Clearcoat')) {
      const previous = mesh.geometry;
      mesh.geometry = smoothPaintNormals(previous);
      if (mesh.geometry !== previous) previous.dispose();
    }
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (!(m as THREE.MeshStandardMaterial).isMeshStandardMaterial) continue;
      if (m.name === 'Pearl_White_Clearcoat') paint.add(m as THREE.MeshStandardMaterial);
      if (obj.userData.partType === 'licensePlate' || m.name === 'LicensePlate_Face') plates.add(m as THREE.MeshStandardMaterial);
    }
  });
  const canvas = document.createElement('canvas'); canvas.width = 1024; canvas.height = 326;
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  texture.flipY = false; texture.anisotropy = 4;
  const ctx = canvas.getContext('2d')!;
  for (const m of plates) { m.color.set('#ffffff'); m.map = texture; m.needsUpdate = true; }
  return {
    update(input: VehicleAppearance) {
      const a = normalizeAppearance(input);
      const finish = paintFinishes.find(item => item.value === a.finish)!;
      paint.forEach(m => {
        m.color.set(a.color);
        m.metalness = finish.metalness;
        m.roughness = finish.roughness;
        if ((m as THREE.MeshPhysicalMaterial).isMeshPhysicalMaterial) {
          const physical = m as THREE.MeshPhysicalMaterial;
          physical.clearcoat = finish.clearcoat;
          physical.clearcoatRoughness = finish.clearcoatRoughness;
        }
        m.needsUpdate = true;
      });
      const colors: Record<string, [string,string]> = { green:['#86e6a1','#122d25'],blue:['#1456ad','#ffffff'],black:['#20272d','#ffffff'],white:['#f4f5f2','#182026'] };
      const [bg,fg] = colors[a.plateStyle];
      // Blender exports glTF UVs with the image origin at the top.
      ctx.save();
      ctx.fillStyle=bg; ctx.fillRect(0,0,1024,326);
      ctx.strokeStyle=fg; ctx.lineWidth=5; ctx.strokeRect(16,16,992,294);
      ctx.fillStyle=fg; ctx.font='600 196px "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(a.plate,512,174,920);
      ctx.restore();texture.needsUpdate=true;
    },
    dispose() { plates.forEach(m => { m.map=null; }); texture.dispose(); },
  };
}
