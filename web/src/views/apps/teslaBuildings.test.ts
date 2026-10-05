import { describe, expect, it } from 'vitest';
import { Color, Vector3 } from 'three';
import { createBuildingMeshes, occludingBuildingIndices } from './teslaBuildings';

describe('App building extrusion', () => {
  const ring = [[116,40],[116.0001,40],[116.0001,40.0001],[116,40.0001]];
  it('preserves metre heights, roof base and geographic orientation, deduplicating tiles', () => {
    const building = { id:'1', parts:[{ring,base:12,height:8}] };
    const {mesh,count} = createBuildingMeshes([building,building],[116,40]);
    expect(count).toBe(1);
    mesh!.geometry.computeBoundingBox();
    const box=mesh!.geometry.boundingBox!;
    expect(box.min.y).toBeCloseTo(12); expect(box.max.y).toBeCloseTo(20);
    expect(box.max.x).toBeGreaterThan(8); expect(box.min.z).toBeLessThan(-11);
    expect(mesh!.castShadow).toBe(true);
    mesh!.geometry.dispose(); mesh!.material.dispose();
  });
  it('rejects invalid heights and buildings outside the visible neighbourhood', () => {
    expect(createBuildingMeshes([{id:'x',parts:[{ring,base:0,height:NaN}]}],[116,40]).count).toBe(0);
    expect(createBuildingMeshes([{id:'x',parts:[{ring,base:0,height:20}]}],[117,41]).count).toBe(0);
  });
  it('omits the repeated flag-8 rooftop pieces while retaining flag-4 roof structures', () => {
    const source={id:'roof',overallHeight:20,parts:[
      {ring,base:0,height:20,flags:2},
      {ring,base:20,height:8,flags:8},
      {ring,base:20,height:3,flags:4},
    ]};
    const {mesh,count}=createBuildingMeshes([source],[116,40]);
    expect(count).toBe(1);
    mesh!.geometry.computeBoundingBox();
    expect(mesh!.geometry.boundingBox!.max.y).toBeCloseTo(23);
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('uses the native bottom-to-top color gradient and preserves round wall normals', () => {
    const round=Array.from({length:16},(_,index)=>[116+Math.cos(index*Math.PI/8)*.00005,40+Math.sin(index*Math.PI/8)*.00005]);
    const source={id:'round',overallHeight:4,parts:[{ring:round,base:0,height:4,smoothWalls:true}],
      paints:{day:[{minZoom:15,maxZoom:18,surface:{color:'#ddeeff',opacity:1},
        colorSlots:['#ddeeff','#ccddee','#bbccdd','#aabbcc','#99aabb']}]}};
    const {mesh}=createBuildingMeshes([source],[116,40]);
    const colors=mesh!.geometry.getAttribute('color');
    const shades=new Set(Array.from({length:colors.count},(_,i)=>
      [colors.getX(i),colors.getY(i),colors.getZ(i)].map(v=>v.toFixed(3)).join(',')));
    expect(shades.size).toBe(2);
    for(const hex of ['#ddeeff','#ccddee']) {
      expect(shades.has(new Color(hex).toArray().map(v=>v.toFixed(3)).join(','))).toBe(true);
    }
    const normals=mesh!.geometry.getAttribute('normal');
    expect(Array.from({length:normals.count},(_,i)=>normals.getY(i)).some(y=>Math.abs(y)<.5)).toBe(true);
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('keeps one native height gradient across stacked parts', () => {
    const source={id:'stacked',overallHeight:20,parts:[
      {ring,base:0,height:10},{ring,base:10,height:10},
      {ring,base:20,height:2}],
      paints:{night:[{minZoom:15,maxZoom:18,surface:{color:'#000000',opacity:1},
        colorSlots:['#000000','#ffffff','#000000','#000000','#000000']}]}};
    const {mesh}=createBuildingMeshes([source],[116,40],'night');
    const positions=mesh!.geometry.getAttribute('position');
    const colors=mesh!.geometry.getAttribute('color');
    for(const [height,expected] of [[0,0],[10,.5],[20,1],[22,1.1]]) {
      const matched=Array.from({length:positions.count},(_,i)=>i)
        .filter(i=>Math.abs(positions.getY(i)-height)<.001);
      expect(matched.length).toBeGreaterThan(0);
      for(const i of matched) expect(colors.getX(i)).toBeCloseTo(expected,4);
    }
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
  it('assigns the APK facade texture to walls but keeps roof faces untextured', () => {
    const source={id:'textured',overallHeight:20,parts:[{ring,base:0,height:20}],
      paints:{night:[{minZoom:15,maxZoom:18,surface:{color:'#4d4a9c',opacity:1},
        colorSlots:Array(5).fill('#4d4a9c'),textureId:1112}]}};
    const {mesh}=createBuildingMeshes([source],[116,40],'night');
    const normal=mesh!.geometry.getAttribute('normal');
    const slots=mesh!.geometry.getAttribute('buildingTextureSlot');
    const uv=mesh!.geometry.getAttribute('buildingFacadeUv');
    expect(Array.from({length:slots.count},(_,i)=>slots.getX(i))
      .filter((_,i)=>Math.abs(normal.getY(i))<.5)).toContain(5);
    for(let i=0;i<slots.count;i++) if(Math.abs(normal.getY(i))>.5) expect(slots.getX(i)).toBe(0);
    const wallU=Array.from({length:slots.count},(_,i)=>i).filter(i=>slots.getX(i)===5).map(i=>uv.getX(i));
    const wallV=Array.from({length:slots.count},(_,i)=>i).filter(i=>slots.getX(i)===5).map(i=>uv.getY(i));
    expect(Math.min(...wallU)).toBeCloseTo(0);expect(Math.max(...wallU)).toBeCloseTo(1);
    expect(Math.min(...wallV)).toBeCloseTo(0);expect(Math.max(...wallV)).toBeCloseTo(1);
    expect(mesh!.material.userData.buildingAtlas).toBeDefined();
    mesh!.geometry.dispose();mesh!.material.userData.buildingAtlas.dispose();mesh!.material.dispose();
  });
  it('uses the night secondary texture only for wall emission', () => {
    const source={id:'windows',overallHeight:20,parts:[{ring,base:0,height:20}],
      paints:{night:[{minZoom:15,maxZoom:18,surface:{color:'#1f2d49',opacity:1},
        colorSlots:Array(5).fill('#1f2d49'),textureId:23100029,secondaryTextureId:1112}]}};
    const {mesh}=createBuildingMeshes([source],[116,40],'night');
    const normals=mesh!.geometry.getAttribute('normal');
    const mask=mesh!.geometry.getAttribute('buildingEmissionMask');
    expect(Array.from({length:mask.count},(_,i)=>mask.getX(i))
      .filter((_,i)=>Math.abs(normals.getY(i))<.5)).toContain(1);
    for(let i=0;i<mask.count;i++) if(Math.abs(normals.getY(i))>.5) expect(mask.getX(i)).toBe(0);
    expect(mesh!.material.userData.buildingMre.colorSpace).toBe('srgb-linear');
    expect(mesh!.material.customProgramCacheKey()).toBe('app-buildings:1:1');
    const shader={uniforms:{} as Record<string,unknown>,vertexShader:'#include <project_vertex>',
      fragmentShader:'#include <color_fragment>\n#include <emissivemap_fragment>\n#include <clipping_planes_fragment>'};
    mesh!.material.onBeforeCompile(shader as never,{ } as never);
    expect(shader.fragmentShader).toContain('texture2D(buildingMre, repeatUv).b');
    expect(shader.fragmentShader).toContain('facadeEmissionColor');
    mesh!.geometry.dispose();mesh!.material.userData.buildingAtlas.dispose();
    mesh!.material.userData.buildingMre.dispose();mesh!.material.dispose();
  });
  it('separates textured and plain building shader programs', () => {
    const plain=createBuildingMeshes([{id:'plain',parts:[{ring,base:0,height:10}]}],[116,40]);
    expect(plain.mesh!.material.customProgramCacheKey()).toBe('app-buildings:0:0');
    plain.mesh!.geometry.dispose();plain.mesh!.material.dispose();
  });
  it('hides a whole building when it blocks the car, leaving buildings behind the car visible', () => {
    const a = { index: 1, parts: [{ ring: [[-2,4],[2,4],[2,8],[-2,8]] as [number,number][], base: 0, top: 20 }] };
    const b = { index: 2, parts: [{ ring: [[-2,-10],[2,-10],[2,-6],[-2,-6]] as [number,number][], base: 0, top: 20 }] };
    expect(occludingBuildingIndices([a,b], new Vector3(0,8,15), new Vector3(0,1,0))).toEqual([1]);
    expect(occludingBuildingIndices([a], new Vector3(20,8,15), new Vector3(0,1,0))).toEqual([]);
    expect(occludingBuildingIndices([a], new Vector3(0,100,15), new Vector3(0,1,0))).toEqual([]);
    expect(occludingBuildingIndices([a], new Vector3(0,8,15), new Vector3(0,1,6))).toEqual([1]);
  });
  it('uses building IDs in the shader instead of the old circular sightline cutout', () => {
    const {mesh}=createBuildingMeshes([{id:'one',parts:[{ring,base:0,height:20}]}],[116,40]);
    expect(mesh!.geometry.getAttribute('buildingOcclusionId').getX(0)).toBe(1);
    const shader={uniforms:{} as Record<string,unknown>,vertexShader:'#include <project_vertex>',
      fragmentShader:'#include <clipping_planes_fragment>'};
    mesh!.material.onBeforeCompile(shader as never,{} as never);
    expect(shader.fragmentShader).toContain('abs(occlusionId - hiddenBuildingIds[i]) < 0.25');
    expect(shader.fragmentShader).not.toContain('clearance');
    mesh!.geometry.dispose();mesh!.material.dispose();
  });
});
