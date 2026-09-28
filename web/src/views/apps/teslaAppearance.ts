import * as THREE from 'three';

export const APPEARANCE_KEY = 'tmc.tesla.appearance.v1';
export const defaultAppearance = { color: '#eaf0f3', plate: 'TMC', plateStyle: 'green' };
export type VehicleAppearance = typeof defaultAppearance;
export function normalizeAppearance(value: Partial<VehicleAppearance> | null): VehicleAppearance {
  return {
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
      paint.forEach(m => m.color.set(a.color));
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
