import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';

type BuildingPaint = {minZoom:number;maxZoom:number;surface:{color:string;opacity:number};colorSlots?:string[];
  textureId?:number;secondaryTextureId?:number;materialOption7Raw?:number};
export type AppBuilding = { id: string; overallHeight?: number; parts: { ring: number[][]; base: number; height: number; flags?: number; smoothWalls?:boolean }[];
  paints?: { day?: BuildingPaint[]; night?: BuildingPaint[] } };

// Slot order matches the atlas produced by extract_building_icons.py.
const textureSlot: Record<number, number> = {
  23000029: 1, 23000030: 2, 2100031: 3,
  23100029: 4, 1112: 5, 30: 6,
};

type BuildingOccluder = { index: number; parts: { ring: [number, number][]; base: number; top: number }[] };

function insideRing(point: readonly [number, number], ring: [number, number][]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > point[1]) !== (b[1] > point[1])
        && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

/** Select whole buildings between the camera and car, never a circular hole in a wall. */
export function occludingBuildingIndices(occluders: BuildingOccluder[], camera: THREE.Vector3,
  vehicle: THREE.Vector3, limit = 8): number[] {
  const result: number[] = [];
  const from: [number, number] = [camera.x, camera.z], to: [number, number] = [vehicle.x, vehicle.z];
  const dx = to[0] - from[0], dz = to[1] - from[1];
  const cross = (ax: number, az: number, bx: number, bz: number) => ax * bz - az * bx;
  for (const building of occluders) {
    let blocked = false;
    for (const part of building.parts) {
      if (insideRing(to, part.ring) && vehicle.y >= part.base - 2 && vehicle.y <= part.top + 2) {
        blocked = true; break;
      }
      const ring = part.ring;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i], b = ring[(i + 1) % ring.length];
        const ex = b[0] - a[0], ez = b[1] - a[1], denominator = cross(dx, dz, ex, ez);
        if (Math.abs(denominator) < 1e-6) continue;
        const qx = a[0] - from[0], qz = a[1] - from[1];
        const t = cross(qx, qz, ex, ez) / denominator;
        const u = cross(qx, qz, dx, dz) / denominator;
        if (t <= 0 || t >= 1 || u < 0 || u > 1) continue;
        const y = camera.y + (vehicle.y - camera.y) * t;
        if (y >= part.base && y <= part.top) { blocked = true; break; }
      }
      if (blocked) break;
    }
    if (blocked) {
      result.push(building.index);
      if (result.length >= limit) break;
    }
  }
  return result;
}

export function createBuildingMeshes(buildings: AppBuilding[], anchor: MapPoint, theme: 'day' | 'night' = 'day') {
  const geometries: THREE.BufferGeometry[] = [];
  const seen = new Set<string>(), displayed = new Set<string>();
  const occluders = new Map<string, BuildingOccluder>();
  let vertices = 0, hasFacadeTexture = false, hasMreTexture = false;
  for (const building of buildings) {
    const nativeHeight = building.overallHeight;
    const colorHeight = Number.isFinite(nativeHeight) && nativeHeight! > 0
      ? nativeHeight! : Math.max(1,...(building.parts || []).map(part=>part.base+part.height));
    for (const part of building.parts || []) {
    // libamapr ParseBuilding selects flag 8 only for theme ID "f_lego" and
    // flag 4 for the normal 3D-building path. TMC uses the normal navigation
    // theme; rendering both created the repeated rooftop cylinders.
    if (part.flags !== undefined && (part.flags & 0x8) !== 0) continue;
    if (!Number.isFinite(part.base) || !Number.isFinite(part.height) || part.base < 0 || part.height <= 0 || part.base + part.height > 2000) continue;
    if (!Array.isArray(part.ring) || part.ring.length < 3 || part.ring.length > 10000 || part.ring.some(p => p.length !== 2 || !p.every(Number.isFinite))) continue;
    const points = part.ring.map(p => groundOffset(p, anchor));
    if (Math.min(...points.map(p=>p[0])) > 300 || Math.max(...points.map(p=>p[0])) < -300 || Math.min(...points.map(p=>p[1])) > 300 || Math.max(...points.map(p=>p[1])) < -300) continue;
    const key = `${building.id}/${part.base}/${part.height}/${JSON.stringify(part.ring)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const shape = new THREE.Shape(points.map(([x,z]) => new THREE.Vector2(x,-z)));
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: part.height, bevelEnabled: false, steps: 1, curveSegments: 1 });
    geometry.rotateX(-Math.PI/2); geometry.translate(0,part.base,0);
    const count = geometry.getAttribute('position').count;
    if (vertices + count > 250000) { geometry.dispose(); continue; }
    vertices += count;
    let occluder = occluders.get(building.id);
    if (!occluder) { occluder = { index: occluders.size + 1, parts: [] }; occluders.set(building.id, occluder); }
    occluder.parts.push({ ring: points.map(([x,z]) => [x,z]), base: part.base, top: part.base + part.height });
    geometry.setAttribute('buildingOcclusionId', new THREE.Float32BufferAttribute(
      new Float32Array(count).fill(occluder.index), 1));
    // The sampled BMD rooftop circle has a zero edge mask. Smooth only these
    // candidate contours; the native edge-mask semantics are not fully known.
    const colors = new Float32Array(count*3), normal = geometry.getAttribute('normal');
    const position=geometry.getAttribute('position');
    if(part.smoothWalls) {
      const cx=points.reduce((sum,p)=>sum+p[0],0)/points.length;
      const cz=points.reduce((sum,p)=>sum+p[1],0)/points.length;
      for(let i=0;i<count;i++) if(Math.abs(normal.getY(i))<.5) {
        const dx=position.getX(i)-cx,dz=position.getZ(i)-cz,length=Math.hypot(dx,dz);
        if(length>.001) {normal.setXYZ(i,dx/length,0,dz/length);}
      }
      normal.needsUpdate=true;
    }
    const source=building.paints?.[theme]?.find(p=>p.minZoom<=17 && p.maxZoom>=17);
    const slot=source?.textureId ? textureSlot[source.textureId] || 0 : 0;
    // Night style field 11 points to window-like icon 1112. The native shader
    // samples its MRE texture's blue channel for emission; the exact field-to-
    // sampler binding is still being verified, so this is an isolated layer.
    const mre=theme==='night' && source?.secondaryTextureId===1112;
    if (slot) hasFacadeTexture = true;
    if (mre) hasMreTexture = true;
    const sourceColor=source?.surface.opacity===1 && /^#[\da-f]{6}$/i.test(source.surface.color) ? source.surface.color : undefined;
    const colorSlots=source?.colorSlots?.length===5 && source.colorSlots.every(color=>/^#[\da-f]{6}$/i.test(color))
      ? source.colorSlots.map(color=>new THREE.Color(color)) : undefined;
    const roof = new THREE.Color(sourceColor || (theme==='night'?'#344359':'#e5eeee'));
    const wall = new THREE.Color(sourceColor || (theme==='night'?'#273446':'#a8bbc5'));
    if (sourceColor) wall.multiplyScalar(.72);
    const gradient=new THREE.Color();
    const slots=new Float32Array(count);
    const facadeUv=new Float32Array(count*2);
    const emissionMask=new Float32Array(count);
    const emissionColor=new Float32Array(count*3);
    for (let i=0;i<count;i++) {
      if(colorSlots) {
        // APK BUILDING_WINDOW divides absolute vertex elevation by a height
        // carried in the UV. The BMD feature-level height is the matching
        // source available here. Roof parts can extend above that height;
        // GLSL mix permits the ratio to exceed one.
        // Remaining slots are emission and false-AO colors, which need the
        // separate facade textures and parameters before they can be applied.
        gradient.copy(colorSlots[0]).lerp(colorSlots[1],position.getY(i)/colorHeight);
        gradient.toArray(colors,i*3);
      } else (normal.getY(i)>.5?roof:wall).toArray(colors,i*3);
    }
    if (slot || mre) {
      const originalUv=geometry.getAttribute('uv');
      // ExtrudeGeometry emits one six-vertex quad per wall edge. Preserve its
      // edge direction while fitting each APK facade image to that edge and
      // the feature's original building height. The native texScale/floor
      // uniforms have not yet been recovered, so repetition remains pending.
      for (const group of geometry.groups) if (group.materialIndex===1) {
        for (let start=group.start;start+5<group.start+group.count;start+=6) {
          let min=Infinity,max=-Infinity;
          for(let i=start;i<start+6;i++) {
            min=Math.min(min,originalUv.getX(i)); max=Math.max(max,originalUv.getX(i));
          }
          const width=Math.max(max-min,.001);
          for(let i=start;i<start+6;i++) {
            slots[i]=slot;
            if (mre) {
              emissionMask[i]=1;
              (colorSlots?.[2] || new THREE.Color('#1f2d49')).toArray(emissionColor,i*3);
            }
            facadeUv[i*2]=(originalUv.getX(i)-min)/width;
            facadeUv[i*2+1]=position.getY(i)/colorHeight;
          }
        }
      }
    }
    geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
    geometry.setAttribute('buildingTextureSlot',new THREE.BufferAttribute(slots,1));
    geometry.setAttribute('buildingFacadeUv',new THREE.BufferAttribute(facadeUv,2));
    geometry.setAttribute('buildingEmissionMask',new THREE.BufferAttribute(emissionMask,1));
    geometry.setAttribute('buildingEmissionColor',new THREE.BufferAttribute(emissionColor,3));
    geometry.clearGroups(); geometries.push(geometry); displayed.add(building.id);
    }
  }
  const merged = geometries.length ? mergeGeometries(geometries,false) : null;
  geometries.forEach(g=>g.dispose());
  if (!merged) return { mesh: undefined, count: 0 };
  const material = new THREE.MeshStandardMaterial({ vertexColors:true, roughness:.92, metalness:0,
    // The APK's BUILDING_WINDOW shader adds an emission term after its dark
    // night texture. Until that sampler/slot binding is recovered, use the
    // common night material color as a restrained visibility floor.
    emissive: theme==='night'?'#1f2d49':'#000000', emissiveIntensity:theme==='night'?.9:0 });
  let atlas: THREE.Texture | undefined;
  if (hasFacadeTexture) atlas = new THREE.TextureLoader().load('/amap/buildings/atlas.png', undefined, undefined, () => {
    // A missing static asset must not turn every textured wall black.
    atlas?.dispose();
    atlas=undefined;
    delete material.userData.buildingAtlas;
    material.needsUpdate=true;
  });
  if (atlas) {
    atlas.colorSpace=THREE.SRGBColorSpace;
    atlas.generateMipmaps=false;
    atlas.minFilter=THREE.LinearFilter;
    atlas.magFilter=THREE.LinearFilter;
    material.userData.buildingAtlas=atlas;
  }
  let mreTexture: THREE.Texture | undefined;
  if (hasMreTexture) mreTexture = new THREE.TextureLoader().load('/amap/buildings/1112.png', undefined, undefined, () => {
    mreTexture?.dispose();
    mreTexture=undefined;
    delete material.userData.buildingMre;
    material.needsUpdate=true;
  });
  if (mreTexture) {
    // MRE stores data channels, so leave this sampler in linear space.
    mreTexture.colorSpace=THREE.LinearSRGBColorSpace;
    mreTexture.generateMipmaps=false;
    mreTexture.minFilter=THREE.LinearFilter;
    mreTexture.magFilter=THREE.LinearFilter;
    material.userData.buildingMre=mreTexture;
  }
  // onBeforeCompile has the same function text for every building material;
  // include the actual sampler variants in Three's program cache key.
  material.customProgramCacheKey=()=>`app-buildings:${atlas ? 1 : 0}:${mreTexture ? 1 : 0}`;
  // Native configuration names a building-collision hide animation. Hide the
  // complete occluding building instead of cutting a circular shaft through it.
  const hiddenIds = { value:new Float32Array(8) };
  material.onBeforeCompile = shader => {
    shader.uniforms.hiddenBuildingIds=hiddenIds;
    if (atlas) shader.uniforms.buildingAtlas={value:atlas};
    if (mreTexture) shader.uniforms.buildingMre={value:mreTexture};
    shader.vertexShader=`attribute float buildingOcclusionId;
      varying float occlusionId;
      `+(atlas || mreTexture ? `attribute float buildingTextureSlot;
      attribute vec2 buildingFacadeUv;
      varying float facadeSlot;
      varying vec2 facadeUv;
      ` : '')+(mreTexture ? `attribute float buildingEmissionMask;
      attribute vec3 buildingEmissionColor;
      varying float facadeEmissionMask;
      varying vec3 facadeEmissionColor;
      ` : '')+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',
      '#include <project_vertex>\nocclusionId = buildingOcclusionId;'
      +(atlas || mreTexture?'\nfacadeSlot = buildingTextureSlot; facadeUv = buildingFacadeUv;':'')
      +(mreTexture?'\nfacadeEmissionMask = buildingEmissionMask; facadeEmissionColor = buildingEmissionColor;':''));
    shader.fragmentShader=(atlas ? `uniform sampler2D buildingAtlas;
      varying float facadeSlot;
      varying vec2 facadeUv;
      ` : '')+(mreTexture ? `uniform sampler2D buildingMre;
      varying float facadeEmissionMask;
      varying vec3 facadeEmissionColor;
      ${atlas ? '' : 'varying vec2 facadeUv;'}
      ` : '')+'varying float occlusionId;\nuniform float hiddenBuildingIds[8];\n'+shader.fragmentShader;
    if (atlas) shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>', `
      #include <color_fragment>
      if (facadeSlot > 0.5) {
        vec2 repeatUv = fract(facadeUv * (1.0 - 0.0001));
        vec2 atlasPixel = vec2(mod(facadeSlot, 4.0), floor(facadeSlot / 4.0)) * 256.0
          + vec2(2.0) + repeatUv * 252.0;
        vec2 atlasUv = vec2(atlasPixel.x / 1024.0, 1.0 - atlasPixel.y / 512.0);
        diffuseColor.rgb *= texture2D(buildingAtlas, atlasUv).rgb;
      }
    `);
    if (mreTexture) shader.fragmentShader=shader.fragmentShader.replace('#include <emissivemap_fragment>', `
      #include <emissivemap_fragment>
      if (facadeEmissionMask > 0.5) {
        vec2 repeatUv = fract(facadeUv * (1.0 - 0.0001));
        totalEmissiveRadiance += facadeEmissionColor * texture2D(buildingMre, repeatUv).b;
      }
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <clipping_planes_fragment>', `
      #include <clipping_planes_fragment>
      for (int i = 0; i < 8; i++) if (abs(occlusionId - hiddenBuildingIds[i]) < 0.25) discard;
    `);
  };
  const mesh = new THREE.Mesh(merged,material); mesh.castShadow=true; mesh.receiveShadow=true;
  const occluderList = [...occluders.values()];
  mesh.onBeforeRender=(_renderer,_scene,camera)=> {
    hiddenIds.value.fill(0);
    const vehicle = mesh.parent?.userData.vehicleFocus;
    if (!(vehicle instanceof THREE.Vector3)) return;
    const cameraLocal = mesh.worldToLocal(camera.getWorldPosition(new THREE.Vector3()));
    const vehicleLocal = mesh.worldToLocal(vehicle.clone());
    const selected = occludingBuildingIndices(occluderList, cameraLocal, vehicleLocal);
    selected.forEach((id,index) => { hiddenIds.value[index] = id; });
  };
  mesh.name='AppBuildings';
  return { mesh, count:displayed.size };
}
