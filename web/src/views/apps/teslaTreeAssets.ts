import * as T from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

export function loadStreetTrees(targets: T.Group[]) {
  let disposed=false;
  const geometries=new Set<T.BufferGeometry>(), materials=new Set<T.Material>(), textures=new Set<T.Texture>();
  const release=()=>{geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());};
  const ready=new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync('/models/city-sample/tree.glb').then(({scene})=>{
    scene.traverse(o=>{if(o instanceof T.Mesh){geometries.add(o.geometry);o.castShadow=o.receiveShadow=true;for(const m of (Array.isArray(o.material)?o.material:[o.material])){materials.add(m);for(const t of Object.values(m))if(t instanceof T.Texture){textures.add(t);t.anisotropy=4;}}}});
    if(disposed){release();return false;}
    const box=new T.Box3().setFromObject(scene),size=box.getSize(new T.Vector3()),center=box.getCenter(new T.Vector3());
    targets.forEach((target,i)=>{
      target.userData.dispose?.();target.clear();target.userData.dispose=()=>{};
      const model=scene.clone(true),scale=(5.5+(i*7%5)*.4)/size.y;
      model.scale.multiplyScalar(scale);model.position.set(-center.x*scale,-box.min.y*scale,-center.z*scale);
      target.add(model);target.scale.set( .88+(i%3)*.09,1,.9+(i%4)*.07);
    });return true;
  }).catch(error=>{console.warn('Tree asset unavailable; keeping procedural trees.',error);return false;});
  return {ready,dispose(){disposed=true;release();}};
}
