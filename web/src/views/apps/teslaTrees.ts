import * as T from 'three';

// Branched, tapered trees with leaves attached to twig tips rather than a sphere of cards.
export function createStreetTree(seed: number, bark: T.Material) {
  const group = new T.Group();
  let state = seed >>> 0;
  const random = () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 4294967296; };
  const variant = seed % 3;
  const height = 4.6 + random() * 2.1;
  const spread = [2.2, 1.45, 2.7][variant];
  const branchGeometry = new T.CylinderGeometry(.5, 1, 1, 7);
  const branches: {start:T.Vector3;end:T.Vector3;radius:number}[] = [];
  const tips:T.Vector3[] = [];
  const trunkTop = new T.Vector3((random()-.5)*.35, height*.55, (random()-.5)*.35);
  branches.push({start:new T.Vector3(0,.12,0),end:trunkTop,radius:.15+random()*.07});
  for(let i=0;i<8;i++) {
    const angle=i*2.399+random()*.6;
    const start=trunkTop.clone().multiplyScalar(.58+random()*.42);
    const end=new T.Vector3(Math.cos(angle)*spread*.65,height*(.68+random()*.26),Math.sin(angle)*spread*.65);
    branches.push({start,end,radius:.055+random()*.025});
    for(let j=0;j<5;j++) {
      const a=angle+(random()-.5)*2.4;
      const tip=end.clone().add(new T.Vector3(Math.cos(a)*(.35+random()*.65),random()*.8-.12,Math.sin(a)*(.35+random()*.65)));
      branches.push({start:end.clone().lerp(start,random()*.35),end:tip,radius:.016+random()*.009});
      tips.push(tip);
    }
  }
  const matrix=new T.Object3D();
  const wood=new T.InstancedMesh(branchGeometry,bark,branches.length);
  branches.forEach((b,i)=>{const delta=b.end.clone().sub(b.start);matrix.position.copy(b.start).add(b.end).multiplyScalar(.5);matrix.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.clone().normalize());matrix.scale.set(b.radius,delta.length(),b.radius);matrix.updateMatrix();wood.setMatrixAt(i,matrix.matrix);});
  wood.castShadow=wood.receiveShadow=true;group.add(wood);
  // Curved leaf geometry: no floating rectangular alpha cards and no white edge halos.
  const shape=new T.Shape();shape.moveTo(0,-.5);shape.bezierCurveTo(-.36,-.15,-.3,.25,0,.5);shape.bezierCurveTo(.3,.25,.36,-.15,0,-.5);
  const leafGeometry=new T.ShapeGeometry(shape,3);
  const positions=leafGeometry.getAttribute('position');
  for(let i=0;i<positions.count;i++)positions.setZ(i,Math.abs(positions.getX(i))*.32);
  leafGeometry.computeVertexNormals();
  const material=new T.MeshStandardMaterial({color:'#ffffff',roughness:.82,side:T.DoubleSide});
  const leaves=new T.InstancedMesh(leafGeometry,material,tips.length*64);
  let index=0;
  for(const tip of tips)for(let j=0;j<64;j++){
    matrix.position.copy(tip).add(new T.Vector3((random()-.5)*1.5,(random()-.5)*1.15,(random()-.5)*1.5));
    matrix.rotation.set(-Math.PI/2+(random()-.5)*1.8,random()*Math.PI*2,random()*Math.PI);
    const size=.16+random()*.16;matrix.scale.set(size*(variant===1?.65:1),size, size);matrix.updateMatrix();leaves.setMatrixAt(index,matrix.matrix);
    const color=new T.Color().setHSL(.23+random()*.065,.26+random()*.2,.065+random()*.09);leaves.setColorAt(index++,color);
  }
  leaves.castShadow=leaves.receiveShadow=true;group.add(leaves);
  group.rotation.y=random()*Math.PI*2;
  group.userData.dispose=()=>{wood.dispose();leaves.dispose();branchGeometry.dispose();leafGeometry.dispose();material.dispose();};
  return group;
}
