import * as THREE from 'three';
import { repairSurfaceGeometry, repairHoodEdgeNormals, repairRearQuarterNormals, repairRoofGlassNormals } from './teslaSurfaceRepair';
import { isOfficialVehicle } from './teslaOfficialModel';
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
  { value: 'metallic', label: '金属', metalness: .34, roughness: .39, clearcoat: .95, clearcoatRoughness: .2 },
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

/** Own the dynamic plate texture and the plate faces attached to this model. */
export function createVehicleAppearance(model: THREE.Object3D) {
  model.updateWorldMatrix(true, true);
  const official = isOfficialVehicle(model);
  const inverseModel = model.matrixWorld.clone().invert();
  const bakedSurface = model.userData.surfaceRevision === 2 || model.getObjectByName('Model_Y_2022')?.userData.surfaceRevision === 2;
  const paint = new Set<THREE.MeshStandardMaterial>();
  const plates = new Set<THREE.MeshStandardMaterial>();
  const glass = new Set<THREE.MeshStandardMaterial>();
  model.traverse(obj => {
    if (!(obj as THREE.Mesh).isMesh) return;
    const mesh = obj as THREE.Mesh;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    // Correct inconsistent face winding before rebuilding paint normals.
    if (!official && materials.every(m => ['Pearl_White_Clearcoat', 'Wheel_Graphite_Alloy', 'Tire_Rubber'].includes(m.name))) {
      const previous = mesh.geometry;
      mesh.geometry = repairSurfaceGeometry(previous);
      previous.dispose();
    }
    if (!official && materials.length && materials.every(m => m.name === 'Pearl_White_Clearcoat')) {
      const previous = mesh.geometry;
      const toModel = inverseModel.clone().multiply(mesh.matrixWorld);
      const hood = repairHoodEdgeNormals(previous, toModel);
      mesh.geometry = repairRearQuarterNormals(hood, toModel);
      hood.dispose();
      previous.dispose();
    }
    if (!official && materials.length && materials.every(m => m.name === 'Smoked_Panoramic_Glass')) {
      const previous = mesh.geometry;
      mesh.geometry = repairRoofGlassNormals(previous, inverseModel.clone().multiply(mesh.matrixWorld));
      previous.dispose();
    }
    // Rebuild paint normals across duplicated UV vertices; preserve body creases.
    // GLTF primitives have independent geometry, so glass, trim and wheels stay intact.
    if (!official && !bakedSurface && materials.length && materials.every(m => m.name === 'Pearl_White_Clearcoat')) {
      const previous = mesh.geometry;
      mesh.geometry = smoothPaintNormals(previous);
      if (mesh.geometry !== previous) previous.dispose();
    }
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (!(m as THREE.MeshStandardMaterial).isMeshStandardMaterial) continue;
      if ((!official && m.name === 'Smoked_Panoramic_Glass') || (official && /^Glass(?:Tinted|Fade|Skybox|_Interior)/.test(m.name))) glass.add(m as THREE.MeshStandardMaterial);
      if (m.name === 'Pearl_White_Clearcoat' || (official && /^Paint(?:Skybox|Fade|Rough)$/.test(m.name))) paint.add(m as THREE.MeshStandardMaterial);
      if (!official && (obj.userData.partType === 'licensePlate' || m.name === 'LicensePlate_Face')) plates.add(m as THREE.MeshStandardMaterial);
    }
  });
  // The imported glass is too mirror-like: bright surroundings create white blobs.
  // Retain a dark, translucent windshield with broad, subdued reflections.
  glass.forEach(m => {
    m.color.set(official ? '#52616a' : '#263745');
    m.metalness = .02;
    m.roughness = official ? .26 : .78;
    m.envMapIntensity = official ? .18 : .03;
    m.opacity = official ? (m.name.includes('Interior') ? .15 : .36) : .9;
    m.transparent = true;
    if (official) m.depthWrite = false;
    m.needsUpdate = true;
  });
  const canvas = document.createElement('canvas'); canvas.width = 1024; canvas.height = 326;
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  texture.flipY = official; texture.anisotropy = 4;
  const ctx = canvas.getContext('2d')!;
  for (const m of plates) { m.color.set('#ffffff'); m.map = texture; m.needsUpdate = true; }
  const addedPlates: THREE.Mesh[] = [];
  if (official) {
    const rear = model.getObjectByName('Plate_US');
    const trunk = model.getObjectByName('Trunk_Spatial');
    const faceMaterial = new THREE.MeshStandardMaterial({ name: 'TMC_RearPlate_Face', map: texture, color: '#ffffff', roughness: .65, metalness: .04, side: THREE.DoubleSide });
    const frameMaterial = new THREE.MeshStandardMaterial({ name: 'TMC_RearPlate_Frame', color: '#171d22', roughness: .43, metalness: .25, side: THREE.DoubleSide });
    const addPlate = (parent: THREE.Object3D, width: number, height: number, x: number, y: number, z: number, material: THREE.Material, name: string) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material);
      mesh.name = name;
      mesh.position.set(x, y, z);
      mesh.rotation.y = -Math.PI / 2;
      mesh.renderOrder = 2;
      parent.add(mesh);
      addedPlates.push(mesh);
    };
    if (rear && trunk) {
      // Measure the imported rear plate in trunk coordinates. Attaching the
      // replacement here also makes it move with the animated hatch.
      const inverseTrunk = trunk.matrixWorld.clone().invert();
      const bounds = new THREE.Box3();
      rear.traverse(child => {
        if (!(child as THREE.Mesh).isMesh) return;
        const mesh = child as THREE.Mesh;
        mesh.geometry.computeBoundingBox();
        const box = mesh.geometry.boundingBox!;
        for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
          bounds.expandByPoint(new THREE.Vector3(x, y, z).applyMatrix4(mesh.matrixWorld).applyMatrix4(inverseTrunk));
        }
      });
      if (!bounds.isEmpty()) {
        const center = bounds.getCenter(new THREE.Vector3());
        // The source plate is a narrow US shape. A wider, shallower face fits
        // Chinese plates without squeezing eight glyphs into the recess.
        addPlate(trunk, .46, .15, bounds.min.x - .006, center.y, center.z, frameMaterial, 'TMC_RearPlate_Frame');
        addPlate(trunk, .438, .136, bounds.min.x - .009, center.y, center.z, faceMaterial, 'TMC_RearPlate');
      }
    }
    if (!addedPlates.length) { faceMaterial.dispose(); frameMaterial.dispose(); }
  }
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
      const colors: Record<string, [string,string,string]> = {
        green:['#b5f1bf','#75d592','#122d25'], blue:['#2873d0','#104695','#ffffff'],
        black:['#3a4248','#161c21','#ffffff'], white:['#ffffff','#dce1e2','#182026'],
      };
      const [top,bottom,fg] = colors[a.plateStyle];
      ctx.save();
      const gradient=ctx.createLinearGradient(0,0,0,canvas.height);
      gradient.addColorStop(0,top);gradient.addColorStop(1,bottom);
      ctx.fillStyle=gradient;ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.strokeStyle=fg;ctx.globalAlpha=.38;ctx.lineWidth=5;ctx.strokeRect(13,13,canvas.width-26,canvas.height-26);ctx.globalAlpha=1;
      ctx.fillStyle=fg;ctx.font='700 196px "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
      const plateText=official&&/^[\u4e00-\u9fa5][A-Z]/.test(a.plate)&&Array.from(a.plate).length>=7
        ? `${Array.from(a.plate).slice(0,2).join('')}·${Array.from(a.plate).slice(2).join('')}` : a.plate;
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(plateText,canvas.width/2,173,884);
      if(official){
        ctx.globalAlpha=.5;
        for(const x of [42,canvas.width-42]){ctx.beginPath();ctx.arc(x,canvas.height/2,8,0,Math.PI*2);ctx.fill();}
      }
      ctx.restore();texture.needsUpdate=true;
    },
    dispose() {
      plates.forEach(m => { m.map=null; });
      addedPlates.forEach(mesh => { mesh.removeFromParent(); mesh.geometry.dispose(); });
      new Set(addedPlates.map(mesh => mesh.material as THREE.Material)).forEach(material => material.dispose());
      texture.dispose();
    },
  };
}
