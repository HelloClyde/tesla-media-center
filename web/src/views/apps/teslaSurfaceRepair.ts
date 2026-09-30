import * as T from 'three';

/** Repair malformed surface triangles without moving vertices, UVs or pivots. */
export function repairSurfaceGeometry(source: T.BufferGeometry) {
  const geometry = source.clone();
  const positions = geometry.getAttribute('position'), normals = geometry.getAttribute('normal');
  if (!normals) return geometry;
  const index = geometry.index, output: number[] = [];
  let reversed = 0, degenerate = 0;
  const a = new T.Vector3(), b = new T.Vector3(), c = new T.Vector3();
  const ab = new T.Vector3(), ac = new T.Vector3();
  const face = new T.Vector3(), expected = new T.Vector3(), normal = new T.Vector3();
  for (let i = 0; i < (index?.count ?? positions.count); i += 3) {
    const ids = [0, 1, 2].map(j => index ? index.getX(i + j) : i + j);
    a.fromBufferAttribute(positions, ids[0]); b.fromBufferAttribute(positions, ids[1]); c.fromBufferAttribute(positions, ids[2]);
    face.copy(ab.subVectors(b, a)).cross(ac.subVectors(c, a));
    const edgeScale = a.distanceToSquared(b) + b.distanceToSquared(c) + c.distanceToSquared(a);
    // Quantization can leave almost collinear slivers with nonzero area. Their
    // unstable normals show up as dark pinholes on glossy bumper paint.
    if (face.lengthSq() < 1e-20 || (face.lengthSq() < 1e-12 && face.lengthSq() < edgeScale * edgeScale * 2.5e-7)) {
      degenerate++; continue;
    }
    expected.set(0, 0, 0);
    ids.forEach(id => expected.add(normal.fromBufferAttribute(normals, id)));
    // Only strong contradictions are corrected. Near-perpendicular corner
    // normals are ambiguous and must not flip intentional sharp-edge faces.
    if (face.normalize().dot(expected.normalize()) < -.5) {
      [ids[1], ids[2]] = [ids[2], ids[1]]; reversed++;
    }
    output.push(...ids);
  }
  geometry.setIndex(output);
  geometry.userData.surfaceRepair = { reversed, degenerate };
  return geometry;
}

/** Split faulty hood-top corners so the adjoining vertical lip keeps its normal. */
export function repairHoodEdgeNormals(source: T.BufferGeometry, toModel: T.Matrix4) {
  return repairPanelCornerNormals(source, toModel, 'hood');
}

export function repairRearQuarterNormals(source: T.BufferGeometry, toModel: T.Matrix4) {
  return repairPanelCornerNormals(source, toModel, 'rear');
}

export function repairRoofGlassNormals(source: T.BufferGeometry, toModel: T.Matrix4) {
  return repairPanelCornerNormals(source, toModel, 'roofGlass');
}

function repairPanelCornerNormals(source: T.BufferGeometry, toModel: T.Matrix4, region: 'hood' | 'rear' | 'roofGlass') {
  const pos=source.getAttribute('position'), norm=source.getAttribute('normal');
  if(!norm)return source.clone();
  const names=Object.keys(source.attributes);
  const values=names.map(name=>Array.from({length:source.getAttribute(name).count},(_,i)=>
    Array.from({length:source.getAttribute(name).itemSize},(_,c)=>source.getAttribute(name).getComponent(i,c))).flat());
  const index=Array.from(source.index?.array ?? Array.from({length:pos.count},(_,i)=>i));
  const normalMatrix=new T.Matrix3().getNormalMatrix(toModel);
  let corrected=0;
  for(let i=0;i<index.length;i+=3){
    const ids=index.slice(i,i+3);
    const p=ids.map(id=>new T.Vector3().fromBufferAttribute(pos,id).applyMatrix4(toModel));
    const inRegion = region === 'hood'
      ? p.every(v=>Math.abs(v.x)<.8&&v.y>.88&&v.z>.65&&v.z<2.1)
      : region === 'roofGlass'
      ? p.every(v=>Math.abs(v.x)<.65&&v.y>1.45&&v.z> -1.5&&v.z<.45)
      : p.every(v=>Math.abs(v.x)>.55&&(
        (v.y>.65&&v.y<1.5&&v.z<-.65&&v.z>-2.15) ||
        (v.y>.35&&v.y<.8&&v.z<-1.35&&v.z>-2.3)
      ));
    if(!inRegion)continue;
    const face=p[1].clone().sub(p[0]).cross(p[2].clone().sub(p[0])).normalize();
    const outward = face.x*Math.sign(p[0].x);
    if(region === 'hood' ? face.y<.65 : region === 'roofGlass' ? face.y<.75 : !(outward>.5 || (outward>.15 && face.y>.65)))continue;
    const n=ids.map(id=>new T.Vector3().fromBufferAttribute(norm,id).applyMatrix3(normalMatrix).normalize());
    const good=n.map(v=>v.dot(face)>(region === 'roofGlass' ? .9 : .8));
    if(good.filter(Boolean).length!==2)continue;
    const bad=good.indexOf(false);
    if(n[bad].dot(face)>(region === 'roofGlass' ? .8 : .5))continue;
    const replacement=new T.Vector3();
    ids.forEach((id,j)=>{if(good[j])replacement.add(new T.Vector3().fromBufferAttribute(norm,id));});replacement.normalize();
    const newIndex=values[names.indexOf('position')].length/pos.itemSize;
    names.forEach((name,k)=>{
      const attr=source.getAttribute(name);
      for(let c=0;c<attr.itemSize;c++)values[k].push(name==='normal'?replacement.getComponent(c):attr.getComponent(ids[bad],c));
    });
    index[i+bad]=newIndex;corrected++;
  }
  if(!corrected)return source.clone();
  const result=new T.BufferGeometry();
  names.forEach((name,k)=>result.setAttribute(name,new T.Float32BufferAttribute(values[k],source.getAttribute(name).itemSize)));
  result.setIndex(index);result.userData={...source.userData,[region === 'hood' ? 'hoodCornersCorrected' : region === 'roofGlass' ? 'roofGlassCornersCorrected' : 'rearQuarterCornersCorrected']:corrected};
  result.computeBoundingBox();result.computeBoundingSphere();
  return result;
}
