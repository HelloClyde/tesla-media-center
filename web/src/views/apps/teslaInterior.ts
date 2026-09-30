import * as T from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';

/** Repair the legacy asset's static inner door faces before applying display transforms. */
export function repairVehicleInterior(model: T.Object3D) {
  model.updateWorldMatrix(true,true);
  const inverseRoot = model.matrixWorld.clone().invert();
  const doors = ['FL','FR','RL','RR'].map(id=>model.getObjectByName('Door_'+id));
  repairFramelessRearDoors(model);
  const sources: T.Mesh[]=[];
  model.traverse(o=>{
    if (!(o instanceof T.Mesh) || Array.isArray(o.material)) return;
    if (o.material.name === 'Smoked_Panoramic_Glass') {
      // Keep roof tint, but allow the cabin and open door interiors to be visible.
      const glass=o.material.clone() as T.MeshStandardMaterial;
      glass.transparent=true;glass.opacity=.55;glass.depthWrite=false;
      glass.side=T.DoubleSide;glass.color.set('#425764');o.material=glass;
    }
    if (!/^PaletteMaterial/.test(o.material.name)) return;
    let parent=o.parent;
    while(parent && parent!==model) { if(parent.name.startsWith('Door_') || parent.name.startsWith('Wheel_'))return;parent=parent.parent; }
    sources.push(o);
  });
  // Subtract only the door-opening trim volumes, clipping boundary triangles
  // instead of moving whole triangles across the seat/door seams.
  for(const mesh of sources) {
    const source=mesh.geometry, matrix=inverseRoot.clone().multiply(mesh.matrixWorld);
    const names=Object.keys(source.attributes), sizes=names.map(n=>source.getAttribute(n).itemSize);
    const output:number[][]=names.map(()=>[]);
    type Vertex={ p:T.Vector3; values:number[][] };
    const make=(index:number):Vertex=>({p:new T.Vector3().fromBufferAttribute(source.getAttribute('position'),index).applyMatrix4(matrix),
      values:names.map(n=>{const attr=source.getAttribute(n);return Array.from({length:attr.itemSize},(_,c)=>attr.getComponent(index,c));})});
    const interpolate=(a:Vertex,b:Vertex,t:number):Vertex=>({p:a.p.clone().lerp(b.p,t),values:a.values.map((v,i)=>v.map((x,c)=>x+(b.values[i][c]-x)*t))});
    const emit=(polygon:Vertex[])=>{for(let i=1;i<polygon.length-1;i++)for(const v of [polygon[0],polygon[i],polygon[i+1]])v.values.forEach((values,k)=>output[k].push(...values));};
    // The static inner belt rail reaches ~1.21 m, above the old 1.14 m
    // cutoff. Remove it with the old inner panel; the hinged trim replaces it.
    const boxes=[[-.80,-.54,.49,1.23,-1.28,.9],[.54,.80,.49,1.23,-1.28,.9]];
    const count=source.index?.count ?? source.getAttribute('position').count;
    for(let i=0;i<count;i+=3) {
      let pieces:Vertex[][]=[[0,1,2].map(j=>make(source.index ? source.index.getX(i+j) : i+j))];
      for(const box of boxes) {
        const next:Vertex[][]=[];
        for(const polygon of pieces) {
          let remaining=polygon;
          for(let plane=0;plane<6 && remaining.length;plane++) {
            const axis=Math.floor(plane/2), low=plane%2===0, bound=box[plane];
            const distance=(v:Vertex)=>(v.p.getComponent(axis)-bound)*(low ? 1 : -1);
            const inside:Vertex[]=[],outside:Vertex[]=[];
            for(let k=0;k<remaining.length;k++) {
              const a=remaining[k],b=remaining[(k+1)%remaining.length],da=distance(a),db=distance(b);
              (da>=0 ? inside : outside).push(a);
              if((da>=0)!==(db>=0)){const cross=interpolate(a,b,da/(da-db));inside.push(cross);outside.push(cross);}
            }
            if(outside.length>=3)next.push(outside);
            remaining=inside;
          }
        }
        pieces=next;
      }
      pieces.forEach(emit);
    }
    const geometry=new T.BufferGeometry();
    names.forEach((n,i)=>geometry.setAttribute(n,new T.Float32BufferAttribute(output[i],sizes[i])));
    geometry.computeBoundingBox();geometry.computeBoundingSphere();mesh.geometry=geometry;source.dispose();
  }
  const leather=new T.MeshStandardMaterial({color:'#25282b',roughness:.85});
  const insert=new T.MeshStandardMaterial({color:'#44484a',roughness:.95});
  const metal=new T.MeshStandardMaterial({color:'#a3a6a8',metalness:.7,roughness:.3});
  for(let i=0;i<4;i++) {
    const door=doors[i];if(!door)continue;
    const side=i%2===0 ? -1 : 1, front=i<2;
    const z0=front ? -.20 : -1.10, z1=front ? .80 : -.32;
    const panelGroup=new T.Group();panelGroup.name='Door_Inner_Trim';
    function part(x:number,y:number,z:number,w:number,h:number,d:number,mat:T.Material) {
      const object=new T.Mesh(new RoundedBoxGeometry(w,h,d,2,Math.min(w,h,d)*.35),mat);
      object.position.set(x,y,z);object.castShadow=true;object.receiveShadow=true;panelGroup.add(object);
    }
    part(side*.72,.77,(z0+z1)/2,.07,.58,z1-z0,leather);
    part(side*.672,.88,(z0+z1)/2,.03,.19,(z1-z0)*.86,insert);
    part(side*.64,.73,(z0+z1)/2,.15,.065,(z1-z0)*.65,leather);
    part(side*.669,.97,z1-.18,.02,.035,.14,metal);
    part(side*.667,.53,(z0+z1)/2,.04,.12,(z1-z0)*.64,insert);
    panelGroup.applyMatrix4(door.matrixWorld.clone().invert().multiply(model.matrixWorld));
    door.add(panelGroup);
  }

}

/** The source asset incorrectly parents the rear window seals to the moving doors. */
export function repairFramelessRearDoors(model: T.Object3D) {
  model.updateWorldMatrix(true, true);
  const inverse = model.matrixWorld.clone().invert();
  for (const id of ['RL', 'RR']) {
    const door = model.getObjectByName('Door_' + id);
    if (!door || door.userData.framelessRepaired) continue;
    const trims: T.Mesh[] = [];
    door.traverse(object => {
      if (object instanceof T.Mesh && !Array.isArray(object.material) && object.material.name === 'Satin_Black_Trim') trims.push(object);
    });
    for (const mesh of trims) {
      const source = mesh.geometry, transform = inverse.clone().multiply(mesh.matrixWorld);
      const names = Object.keys(source.attributes), sizes = names.map(name => source.getAttribute(name).itemSize);
      type Vertex = { distance: number; values: number[][] };
      const outputs = [names.map(() => [] as number[]), names.map(() => [] as number[])];
      const make = (index: number): Vertex => {
        const p = new T.Vector3().fromBufferAttribute(source.getAttribute('position'), index).applyMatrix4(transform);
        // The rear belt line rises towards the tail (z < 0). A flat 1.12 m
        // cut classified the entire lower rail as a body seal, leaving a bar
        // across the open doorway. Keep the sloping lower rail on the hinge.
        const beltLine = 1.158 - .05 * p.z;
        return { distance: p.y - beltLine, values: names.map(name => {
          const attribute = source.getAttribute(name);
          return Array.from({ length: attribute.itemSize }, (_, c) => attribute.getComponent(index, c));
        }) };
      };
      for (let i = 0; i < (source.index?.count ?? source.getAttribute('position').count); i += 3) {
        const triangle = [0, 1, 2].map(j => make(source.index ? source.index.getX(i + j) : i + j));
        for (let side = 0; side < 2; side++) {
          const polygon: Vertex[] = [];
          for (let j = 0; j < 3; j++) {
            const a = triangle[j], b = triangle[(j + 1) % 3];
            const inside = side === 0 ? a.distance <= 0 : a.distance > 0;
            const nextInside = side === 0 ? b.distance <= 0 : b.distance > 0;
            if (inside) polygon.push(a);
            if (inside !== nextInside) {
              const t = a.distance / (a.distance - b.distance);
              polygon.push({ distance: 0, values: a.values.map((values, k) => values.map((v, c) => v + (b.values[k][c] - v) * t)) });
            }
          }
          for (let j = 1; j < polygon.length - 1; j++) for (const vertex of [polygon[0], polygon[j], polygon[j + 1]]) {
            vertex.values.forEach((values, k) => outputs[side][k].push(...values));
          }
        }
      }
      const geometries = outputs.map(output => {
        const geometry = new T.BufferGeometry();
        names.forEach((name, i) => geometry.setAttribute(name, new T.Float32BufferAttribute(output[i], sizes[i])));
        geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
      });
      // Belt-line trim stays on the door. Upper seals stay fixed to the body;
      // the glass alone follows the door hinge when opened.
      mesh.geometry = geometries[0];
      const seal = new T.Mesh(geometries[1], mesh.material);
      seal.name = 'Rear_Window_Body_Seal_' + id;
      seal.applyMatrix4(transform); seal.castShadow = true; seal.receiveShadow = mesh.receiveShadow;
      model.add(seal); source.dispose();
    }
    door.userData.framelessRepaired = true;
  }
}
