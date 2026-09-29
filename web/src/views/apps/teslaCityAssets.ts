import * as T from 'three';
import { addFacadeWeathering } from './teslaWeathering';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

// Shared authored geometry and textures; each block only owns its transform.
export function createAssetCity() {
  const group = new T.Group();
  group.name = 'DowntownCity';
  const geometries = new Set<T.BufferGeometry>();
  const materials = new Set<T.MeshStandardMaterial>();
  const textures = new Set<T.Texture>();
  const brick = new T.TextureLoader().load('/textures/city-sample/brick-realistic.jpg');
  brick.colorSpace=T.SRGBColorSpace;brick.flipY=false;brick.wrapS=brick.wrapT=T.RepeatWrapping;brick.anisotropy=4;textures.add(brick);
  const interiors = new Set<T.MeshStandardMaterial>();
  let disposed = false, night = false, travel = 0;
  const period = 192;
  function advance(distance: number) {
    travel = ((travel + distance) % period + period) % period;
    for (const block of group.children) block.position.z = ((block.userData.origin + travel + period / 2) % period + period) % period - period / 2;
  }
  function setNight(value: boolean) {
    night = value;
    for (const material of interiors) material.emissiveIntensity = night ? .65 : .035;
  }
  function release() {
    geometries.forEach(value => value.dispose());
    materials.forEach(value => value.dispose());
    textures.forEach(value => value.dispose());
    group.clear();
  }
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const ready = Promise.all([loader.loadAsync('/models/city-sample/downtown.glb'), loader.loadAsync('/models/city-sample/alley-apartments.glb').catch(() => null)]).then(([base, alley]) => {
    const scene=base.scene;
    if(alley){ alley.scene.name='Alley_apartments'; scene.add(alley.scene); }
    scene.updateMatrixWorld(true);
    scene.traverse(object => {
      if (!(object instanceof T.Mesh)) return;
      geometries.add(object.geometry);
      if (!object.geometry.hasAttribute('wearPosition')) {
        const position = object.geometry.getAttribute('position');
        const wear = new T.Float32BufferAttribute(new Float32Array(position.count * 3), 3);
        const point = new T.Vector3();
        for (let i = 0; i < position.count; i++) {
          point.fromBufferAttribute(position, i).applyMatrix4(object.matrixWorld);
          wear.setXYZ(i, point.x, point.y, point.z);
        }
        object.geometry.setAttribute('wearPosition', wear);
      }
      object.castShadow = object.receiveShadow = true;
      for (const material of (Array.isArray(object.material) ? object.material : [object.material]) as T.MeshStandardMaterial[]) {
        materials.add(material);
        if (material.name === 'MI_RedBrick') { material.map=brick; material.normalScale.set(.3,.3); material.roughness=.95; }
        if (/Brick|Trim|Concrete|Asphalt/.test(material.name)) addFacadeWeathering(material);
        for (const value of Object.values(material)) if (value instanceof T.Texture) { textures.add(value); value.anisotropy = 4; }
        if (material.name.includes('FakeInterior')) {
          material.emissiveMap = material.map;
          material.emissive.set('#ffe2b5');
          interiors.add(material);
        }
        if (material.name === 'MI_Glass') { material.opacity = .18; material.depthWrite = false; material.roughness = .22; }
      }
    });
    if (disposed) { release(); return false; }
    const templates = [...scene.children];
    for (const side of [-1, 1]) for (let i = 0; i < 8; i++) {
      const building = templates[alley && i % 3 === 0 ? templates.length-1 : (i + (side === 1 ? 1 : 0)) % 3].clone(true);
      const block = new T.Group();
      block.add(building);
      block.rotation.y = -side * Math.PI / 2;
      block.position.set(side * 14, .16, 0);
      block.userData.origin = i * 24 - 72;
      group.add(block);
    }
    advance(0); setNight(night);
    group.userData.loaded = true;
    return true;
  }).catch(error => {
    console.warn('City assets unavailable; retaining fallback street.', error);
    group.userData.error = String(error);
    return false;
  });
  return { group, ready, advance, setNight, dispose() { disposed = true; release(); group.removeFromParent(); } };
}
