import * as THREE from 'three';
import axios from 'axios';
import { createBuildingMeshes, type AppBuilding } from './teslaBuildings';
import { viewportTiles } from './amapViewport';
import { route3DTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';
import { groundBounds, groundOffset, type MapPoint } from './teslaMapCoordinates';
import { roadSpans, roadDeckGeometry, roadWidth } from './teslaRoadLevels';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const SIZE = 600, RESOLUTION = 2048, ZOOM = 17;
type Tile = { level: number; x: number; y: number; error?: string; missingLayers?: string[];
  collection?: { features: any[] }; surfaces?: any[]; buildings?: AppBuilding[];
  roadPaints?: { day?: Record<string,{minZoom:number;maxZoom:number;outerWidth:number;innerWidth:number;outer:{color:string;opacity:number};inner:{color:string;opacity:number}}[]> } };

/** A georeferenced ground layer in the SAME scene as the vehicle. No fabricated buildings. */
export function createTeslaMapGround(report: (text: string, ready: boolean) => void) {
  const group = new THREE.Group();
  group.visible = false;
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = RESOLUTION;
  const ctx = canvas.getContext('2d')!;
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 8;
  const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE), material);
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; group.add(ground);
  let buildingsMesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | undefined;
  let roadsMesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | undefined;
  function clearRoads() { if (roadsMesh) { roadsMesh.removeFromParent(); roadsMesh.geometry.dispose(); roadsMesh.material.dispose(); roadsMesh=undefined; } }
  function clearBuildings() { if (buildingsMesh) { buildingsMesh.removeFromParent(); buildingsMesh.geometry.dispose(); buildingsMesh.material.dispose(); buildingsMesh=undefined; } }
  const cache = new Map<string, { tile: Tile; at: number }>();
  let visibleKeys = new Set<string>();
  function pruneCache() {
    for (const key of cache.keys()) {
      if (cache.size <= 64) break;
      if (!visibleKeys.has(key)) cache.delete(key);
    }
  }
  let anchor: MapPoint | undefined, latest: MapPoint | undefined;
  let heading = 0, generation = 0, disposed = false, ready = false;
  let request: AbortController | undefined, retryAfter = 0;
  let route: AppRoute | undefined, routeBucket = -1, warmTiles: number[][] = [];
  let browserWarmKeys = new Set<string>();
  const warmAttempted = new Set<string>();
  const browserAttempted = new Set<string>();
  let warmTimer: ReturnType<typeof setTimeout> | undefined;
  let warmRequest: AbortController | undefined, warmGeneration = 0;
  function cancelWarm() {
    warmGeneration++;
    if (warmTimer !== undefined) clearTimeout(warmTimer);
    warmTimer = undefined;
    warmRequest?.abort(); warmRequest = undefined;
  }
  function scheduleWarm(delay = 750) {
    if (disposed || !ready || request || !route || warmTimer !== undefined || warmRequest) return;
    warmTimer = setTimeout(() => { warmTimer = undefined; void warmRoute(); }, delay);
  }
  async function warmRoute() {
    if (disposed || !ready || request || !route || warmRequest) return;
    const tile = warmTiles.find(t => browserWarmKeys.has(t.join('/')) && !cache.has(t.join('/')) && !browserAttempted.has(t.join('/')))
      || warmTiles.find(t => !cache.has(t.join('/')) && !warmAttempted.has(t.join('/')));
    if (!tile) return;
    const key = tile.join('/'), token = warmGeneration;
    const controller = new AbortController(); warmRequest = controller;
    let delay = 750;
    try {
      // Bring the nearest few tiles into the car's browser cache. Farther ones
      // warm only the server and return a tiny cache-status response.
      const onDevice = browserWarmKeys.has(key);
      const response = await axios.post('/api/amap-app/map/prefetch',
        { level: tile[0], tiles: [[tile[1], tile[2]]] },
        { signal: controller.signal, timeout: 12000 });
      if (disposed || token !== warmGeneration) return;
      if (response.status === 202 && response.data.data?.pending) delay = 2000;
      else {
        if (onDevice && response.data.status === 'ok' && response.data.data?.tiles?.[0]?.ready) {
          // The server has finished its short bounded helper. This second
          // request is a cache hit that transfers the tile to the car early.
          const geometry = await axios.post('/api/amap-app/map',
            { level: tile[0], tiles: [[tile[1], tile[2]]] },
            { signal: controller.signal, timeout: 15000 });
          if (disposed || token !== warmGeneration) return;
          if (geometry.status === 202 && geometry.data.data?.pending) { delay = 2000; return; }
          const result = geometry.data.data?.tiles?.[0] as Tile | undefined;
          if (result && !result.error && !result.missingLayers?.length &&
              result.level === tile[0] && result.x === tile[1] && result.y === tile[2]) {
            cache.set(key, { tile: result, at: Date.now() });
            pruneCache();
          }
        }
        warmAttempted.add(key);
        if (onDevice) browserAttempted.add(key);
      }
    } catch {
      if (!disposed && token === warmGeneration) {
        warmAttempted.add(key);
        if (browserWarmKeys.has(key)) browserAttempted.add(key);
      }
    } finally {
      if (warmRequest === controller) warmRequest = undefined;
      if (!disposed && token === warmGeneration) scheduleWarm(delay);
    }
  }
  function align() {
    if (!anchor || !latest) return;
    const [x, z] = groundOffset(anchor, latest);
    const angle = Math.PI + heading * Math.PI / 180;
    group.rotation.y = angle;
    group.position.x = x * Math.cos(angle) + z * Math.sin(angle);
    group.position.z = -x * Math.sin(angle) + z * Math.cos(angle);
  }
  function paint(tiles: Tile[]) {
    if (!anchor) return;
    const scale = RESOLUTION / SIZE;
    const pixel = (p: number[]) => {
      const [x,z] = groundOffset(p, anchor!); return [RESOLUTION/2+x*scale, RESOLUTION/2+z*scale];
    };
    const path = (points: number[][], close: boolean) => {
      points.forEach((p,i) => { const [x,y]=pixel(p); if (i) ctx.lineTo(x,y); else ctx.moveTo(x,y); });
      if (close) ctx.closePath();
    };
    ctx.globalAlpha = 1; ctx.fillStyle = '#dce5e5'; ctx.fillRect(0,0,RESOLUTION,RESOLUTION);
    for (const tile of tiles) for (const surface of tile.surfaces || []) {
      if (ZOOM < surface.minZoom || ZOOM > surface.maxZoom) continue;
      const paint = surface.paints?.day?.find((p: any) => ZOOM >= p.minZoom && ZOOM <= p.maxZoom);
      if (!paint) continue;
      ctx.beginPath(); surface.rings.forEach((ring: number[][]) => path(ring,true));
      ctx.fillStyle = paint.color; ctx.globalAlpha = paint.opacity ?? 1; ctx.fill('evenodd');
    }
    ctx.globalAlpha = 1; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const roads = tiles.flatMap(t => (t.collection?.features || []).map(f=>({...f,paint:t.roadPaints?.day?.[f.properties?.paintKey]?.find(p=>ZOOM>=p.minZoom && ZOOM<=p.maxZoom)}))).filter(f => {
      const style = f.properties?.style;
      return f.geometry?.type === 'LineString' && (style == null || (ZOOM >= (style & 31) && ZOOM <= ((style >> 5) & 31)));
    });
    // Preserve App rule width ratios and colors; 0.1 converts style units to
    // TMC ground metres. This is cartographic width, not measured lane geometry.
    const styled=roads.sort((a,b)=>(b.paint?.outerWidth || 30)-(a.paint?.outerWidth || 30))
      .flatMap(road=>roadSpans(road.geometry.coordinates,road.properties?.levelMarkers).map(span=>({road,span})));
    clearRoads();
    const decks:THREE.BufferGeometry[]=[];
    let deckVertices=0;
    for (const layer of ['outer','inner'] as const) {
      for (const {road,span} of styled) {
        const p=road.paint, stroke=p?.[layer];
        const width=p?.[layer==='outer'?'outerWidth':'innerWidth'];
        if (span.level>0) {
          const geometry=roadDeckGeometry(span,anchor!,roadWidth(width,layer==='outer'),layer==='inner'?.025:0);
          if(geometry) {
            const count=geometry.getAttribute('position').count;
            if(deckVertices+count<=250000) {
              const color=new THREE.Color(stroke?.color || (layer==='outer'?'#829296':'#f7f9f8'));
              const colors=new Float32Array(count*3);
              for(let i=0;i<count;i++) color.toArray(colors,i*3);
              geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));decks.push(geometry);deckVertices+=count;
              continue;
            }
            geometry.dispose();
          }
        }
        ctx.strokeStyle=stroke?.color || (layer==='outer'?'#bac8cc':'#f7f9f8');
        ctx.globalAlpha=stroke?.opacity ?? 1;
        ctx.lineWidth=roadWidth(width,layer==='outer')*scale;
        ctx.beginPath(); path(span.points,false); ctx.stroke();
      }
    }
    const merged=decks.length?mergeGeometries(decks,false):null;
    decks.forEach(g=>g.dispose());
    if(merged) {
      const deckMaterial=new THREE.MeshStandardMaterial({vertexColors:true,roughness:1,side:THREE.DoubleSide});
      deckMaterial.onBeforeCompile=shader=>{
        shader.vertexShader='varying vec2 roadGroundPosition;\n'+shader.vertexShader;
        shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nroadGroundPosition=position.xz;');
        shader.fragmentShader='varying vec2 roadGroundPosition;\n'+shader.fragmentShader;
        shader.fragmentShader=shader.fragmentShader.replace('#include <clipping_planes_fragment>',`#include <clipping_planes_fragment>\nif(max(abs(roadGroundPosition.x),abs(roadGroundPosition.y))>${SIZE/2}.0) discard;`);
      };
      roadsMesh=new THREE.Mesh(merged,deckMaterial);
      roadsMesh.name='AppRoadLevels';roadsMesh.castShadow=true;roadsMesh.receiveShadow=true;group.add(roadsMesh);
    }
    ctx.globalAlpha=1;
    const names = new Set<string>(), cells = new Set<string>();
    ctx.font = '500 24px sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
    for (const road of roads) {
      const name=road.properties?.name, points=road.geometry.coordinates;
      if (!name || names.has(name) || !points.length) continue;
      const [x,y]=pixel(points[Math.floor(points.length/2)]), cell=`${Math.floor(x/240)}/${Math.floor(y/100)}`;
      if (x<60 || y<30 || x>RESOLUTION-60 || y>RESOLUTION-30 || cells.has(cell)) continue;
      names.add(name); cells.add(cell);
      ctx.strokeStyle='#ffffff';ctx.lineWidth=5;ctx.strokeText(name,x,y);ctx.fillStyle='#516873';ctx.fillText(name,x,y);
    }
    texture.needsUpdate = true;
  }
  async function load(point: MapPoint) {
    cancelWarm();
    const id=++generation; request?.abort(); const controller=new AbortController(); request=controller;
    anchor=[...point]; ready=false; group.visible=false; report('正在加载混合地图…',false); align();
    const bounds=groundBounds(point,SIZE/2);
    const tiles=viewportTiles(ZOOM,...bounds);
    // Building source is level 15 (type 5), independent of the even road levels.
    const n=2**15, x=(v:number)=>Math.max(0,Math.min(n-1,Math.floor((v+180)/360*n))), y=(v:number)=>Math.max(0,Math.min(n-1,Math.floor((90-v)/180*n)));
    for(let xx=x(bounds[0]);xx<=x(bounds[2]);xx++) for(let yy=y(bounds[1]);yy<=y(bounds[3]);yy++) tiles.push([15,xx,yy]);
    visibleKeys = new Set(tiles.map(tile => tile.join('/')));
    const collected: Tile[]=[]; let partial=false, buildingFailed=false;
    try {
      for (const level of [...new Set(tiles.map(t=>t[0]))]) {
        try {
        const keys=tiles.filter(t=>t[0]===level);
        const missing=keys.filter(t=>!cache.has(t.join('/')) || Date.now()-cache.get(t.join('/'))!.at>600000);
        if (missing.length) {
          let response; const deadline=Date.now()+90000;
          do {
            response=await axios.post('/api/amap-app/map',{level,tiles:missing.map(t=>t.slice(1))},{signal:controller.signal,timeout:70000});
            if (response.status!==202 || !response.data.data?.pending) break;
            if (Date.now()>deadline) throw new Error('timeout');
            await new Promise(resolve=>setTimeout(resolve,750));
            if (controller.signal.aborted) return;
          } while (true);
          if (disposed || id!==generation) return;
          if (response.data.status!=='ok') throw new Error('map unavailable');
          for (const tile of response.data.data.tiles as Tile[]) {
            if (tile.error) { partial=true; if(level===15) buildingFailed=true; continue; }
            if (tile.missingLayers?.length) { partial=true; if(level===15) buildingFailed=true; }
            cache.set(`${tile.level}/${tile.x}/${tile.y}`,{tile,at:tile.missingLayers?.length?0:Date.now()});
          }
        }
        collected.push(...keys.flatMap(t=>cache.get(t.join('/'))?.tile || []));
        } catch(error) { if(level!==15) throw error; buildingFailed=true; partial=true; }
      }
      if (disposed || id!==generation) return;
      if (!collected.some(t=>t.collection?.features.length || t.surfaces?.length)) throw new Error('empty');
      paint(collected); clearBuildings();
      const buildings=createBuildingMeshes(collected.flatMap(t=>t.buildings || []),anchor!);
      buildingsMesh=buildings.mesh; if(buildingsMesh) group.add(buildingsMesh);
      ready=true; group.visible=true; align();
      const detail=roadsMesh?' · 立交层高示意':'';
      const status=(buildingFailed?'混合地图 · 建筑图层不完整，可重试':partial?'混合地图 · 部分图层缺失':buildings.count ? `App 立体建筑 · ${buildings.count} 栋` : '混合地图 · 此处暂无建筑数据')+detail;
      report(status,true);
      pruneCache();
    } catch {
      if (disposed || id!==generation) return;
      report('地图暂不可用 · 已显示示意路面，可重试',false);
    } finally {
      if (id===generation) { request=undefined; retryAfter=Date.now()+30000; scheduleWarm(); }
    }
  }
  return { group,
    setRoute(nextRoute?: AppRoute, progress = 0) {
      const bucket = Math.floor(Math.max(0, Number.isFinite(progress) ? progress : 0) / 500);
      if (route === nextRoute && routeBucket === bucket) return;
      cancelWarm();
      if (route !== nextRoute) { warmAttempted.clear(); browserAttempted.clear(); }
      route = nextRoute; routeBucket = bucket;
      warmTiles = route ? route3DTiles(route, progress) : [];
      browserWarmKeys = new Set([14, 15].flatMap(level => warmTiles.filter(t => t[0] === level).slice(0, 4))
        .map(tile => tile.join('/')));
      scheduleWarm();
    },
    update(point: MapPoint, angle: number, groundY: number) {
      latest=point; if (Number.isFinite(angle)) heading=angle;
      group.position.y=groundY; align();
      const offset=anchor?groundOffset(point,anchor):[Infinity,Infinity];
      if (!anchor || Math.hypot(...offset)>120 || (!ready && !request && Date.now()>retryAfter)) void load(point);
    },
    retry() { if (latest) void load(latest); },
    dispose() { disposed=true; cancelWarm(); generation++; request?.abort(); clearBuildings(); clearRoads(); group.removeFromParent(); ground.geometry.dispose(); material.dispose(); texture.dispose(); cache.clear(); },
  };
}
