import * as THREE from 'three';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';

export type RoadSpan = { points: number[][]; level: number; rampStart: boolean; rampEnd: boolean };

/** App markers delimit spans; -1 is a terminator, never a -1 metre height. */
export function roadSpans(points: number[][], markers?: number[][]): RoadSpan[] {
  const flat = () => [{points, level:0, rampStart:false, rampEnd:false}];
  if (!markers?.length || points.length < 2) return flat();
  if (markers.some((m,i)=>m.length!==2 || !m.every(Number.isInteger) || m[0]<0 || m[0]>=points.length ||
    m[1]<-128 || m[1]>127 || (i>0 && m[0]<=markers[i-1][0]))) return flat();
  const result: RoadSpan[]=[];
  let start=0, level=0, rampStart=false;
  for (const [index,value] of [...markers,[points.length-1,0]]) {
    if (index>start) result.push({points:points.slice(start,index+1),level,
      rampStart,
      rampEnd:level>0 && value<=0 && (index<points.length-1 || value===-1)});
    start=index;
    rampStart=value>0 && level===0 && index>0;
    // Only the validated positive layer range is visualised. Unknown levels
    // retain a flat road instead of producing kilometre-high geometry.
    level=value>0 && value<=16 ? value : 0;
  }
  return result;
}

export function roadWidth(width: number | undefined, outer: boolean) {
  return Number.isFinite(width) ? Math.max(.25,Math.min(20,width!*.1)) : outer?3:2;
}

/** Schematic separation: 4 m per source level is a display choice, NOT survey height. */
export function roadDeckGeometry(span: RoadSpan, anchor: MapPoint, width: number, lift=0) {
  const points=span.points.map(p=>groundOffset(p,anchor));
  if (points.length<2 || points.some(p=>!p.every(Number.isFinite))) return undefined;
  const distances=[0];
  for (let i=1;i<points.length;i++) distances.push(distances[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]));
  const length=distances[distances.length-1];
  if (!length) return undefined;
  const ramp=Math.min(35,length/3), positions:number[]=[];
  // Resample only for smooth ramp transitions; preserve every source corner.
  const samples: {p:number[];d:number}[]=[];
  for(let i=0;i<points.length-1;i++) {
    const segment=distances[i+1]-distances[i];
    if (!segment) continue;
    const steps=Math.max(1,Math.ceil(segment/5));
    if (samples.length+steps>10000) return undefined;
    for(let j=0;j<steps;j++) {
      const t=j/steps;
      samples.push({p:[points[i][0]+(points[i+1][0]-points[i][0])*t,points[i][1]+(points[i+1][1]-points[i][1])*t],d:distances[i]+segment*t});
    }
  }
  samples.push({p:points[points.length-1],d:length});
  const smooth=(t:number)=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
  for(let i=0;i<samples.length;i++) {
    const {p,d}=samples[i], before=samples[Math.max(0,i-1)].p, after=samples[Math.min(samples.length-1,i+1)].p;
    let dx=after[0]-before[0],dz=after[1]-before[1];
    if (!dx && !dz) {dx=p[0]-before[0];dz=p[1]-before[1];}
    const norm=Math.hypot(dx,dz)||1, nx=-dz/norm*width/2,nz=dx/norm*width/2;
    const h=span.level*4*Math.min(span.rampStart?smooth(d/ramp):1,span.rampEnd?smooth((length-d)/ramp):1)+.06+lift;
    positions.push(p[0]+nx,h,p[1]+nz,p[0]-nx,h,p[1]-nz);
  }
  const indexes:number[]=[];
  for(let i=0;i<samples.length-1;i++) {const a=i*2;indexes.push(a,a+2,a+1,a+1,a+2,a+3);}
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setIndex(indexes);geometry.computeVertexNormals();
  return geometry;
}
