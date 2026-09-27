import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { groundOffset, type MapPoint } from './teslaMapCoordinates';

export type AppBuilding = { id: string; parts: { ring: number[][]; base: number; height: number }[];
  paints?: { day?: {minZoom:number;maxZoom:number;surface:{color:string;opacity:number}}[] } };

export function createBuildingMeshes(buildings: AppBuilding[], anchor: MapPoint) {
  const geometries: THREE.BufferGeometry[] = [];
  const seen = new Set<string>(), displayed = new Set<string>();
  let vertices = 0;
  for (const building of buildings) for (const part of building.parts || []) {
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
    // Bake roof/wall shades into vertices so the entire layer is one draw call.
    const colors = new Float32Array(count*3), normal = geometry.getAttribute('normal');
    const source=building.paints?.day?.find(p=>p.minZoom<=17 && p.maxZoom>=17);
    const sourceColor=source?.surface.opacity===1 && /^#[\da-f]{6}$/i.test(source.surface.color) ? source.surface.color : undefined;
    const roof = new THREE.Color(sourceColor || '#e5eeee'), wall = new THREE.Color(sourceColor || '#a8bbc5');
    for (let i=0;i<count;i++) (normal.getY(i)>.5 ? roof : wall).toArray(colors,i*3);
    geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
    geometry.clearGroups(); geometries.push(geometry); displayed.add(building.id);
  }
  const merged = geometries.length ? mergeGeometries(geometries,false) : null;
  geometries.forEach(g=>g.dispose());
  if (!merged) return { mesh: undefined, count: 0 };
  const material = new THREE.MeshStandardMaterial({ vertexColors:true, roughness:.92, metalness:0 });
  // Cut away only the sight line to the vehicle. Keep real heights elsewhere,
  // including when the camera or an imprecise GPS fix is inside a building.
  const focus = { value:new THREE.Vector3() };
  material.onBeforeCompile = shader => {
    shader.uniforms.vehicleFocus=focus;
    shader.vertexShader='varying vec3 buildingWorldPosition;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',
      '#include <project_vertex>\nbuildingWorldPosition = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader='varying vec3 buildingWorldPosition;\nuniform vec3 vehicleFocus;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace('#include <clipping_planes_fragment>', `
      #include <clipping_planes_fragment>
      vec3 sight = vehicleFocus - cameraPosition;
      float along = clamp(dot(buildingWorldPosition-cameraPosition,sight)/max(dot(sight,sight),0.001),0.0,1.0);
      float clearance = distance(buildingWorldPosition, cameraPosition + along*sight);
      float visibility = smoothstep(4.0,7.0,clearance);
      float stipple = fract(sin(dot(floor(gl_FragCoord.xy),vec2(12.9898,78.233)))*43758.5453);
      if (visibility < 1.0 && visibility <= stipple) discard;
    `);
  };
  const mesh = new THREE.Mesh(merged,material); mesh.castShadow=true; mesh.receiveShadow=true;
  mesh.onBeforeRender=()=> {
    focus.value.set(0,0,0);
    mesh.parent?.parent?.localToWorld(focus.value);
  };
  mesh.name='AppBuildings';
  return { mesh, count:displayed.size };
}
