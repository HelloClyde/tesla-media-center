import {decodeAppMapTiles} from './amapMapWorker';
import {createMapInteraction, waitForMapIdle} from './amapMapWork';
import * as THREE from 'three';
import axios from 'axios';
import { postMapTiles, rawBmdDecodeUnsupported, rawBmdUnsupported } from './amapBmdTransport';
import { createBuildingMeshes, type AppBuilding } from './teslaBuildings';
import { mapTileDistance, viewportTiles } from './amapViewport';
import { route3DTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';
import { groundBounds, groundOffset, type MapPoint } from './teslaMapCoordinates';
import { roadSpans, roadDeckGeometry, roadWidth, nearestRoadHeight, type RoadDeckEdge } from './teslaRoadLevels';
import { createLaneMesh, laneViewportTiles, navigationLaneBoundaries } from './teslaLanes';
import { browserMapTileTtlMs, readMemoryMapTiles, readMapTiles, storeMapTiles } from './amapBrowserTileCache';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import {geometryInView, type GeometryBounds} from './amapGeometryBounds';

const SIZE = 600, RESOLUTION = 2048, ZOOM = 17;
// Keep the high-resolution navigation patch small. The surrounding App map
// covers the camera's far plane without fetching far-away building meshes.
const BACKDROP_SIZE = 6000, BACKDROP_RESOLUTION = 1024;
type Tile = { level: number; x: number; y: number; error?: string; missingLayers?: string[];
  collection?: { features: any[] }; surfaces?: any[]; buildings?: AppBuilding[];
  roadPaints?: { day?: Record<string,{minZoom:number;maxZoom:number;outerWidth:number;innerWidth:number;outer:{color:string;opacity:number};inner:{color:string;opacity:number}}[]>;
    night?: Record<string,{minZoom:number;maxZoom:number;outerWidth:number;innerWidth:number;outer:{color:string;opacity:number};inner:{color:string;opacity:number}}[]> } };

/** A georeferenced ground layer in the SAME scene as the vehicle. No fabricated buildings. */
export function createTeslaMapGround(report: (text: string, ready: boolean) => void, theme: 'day' | 'night' = 'day') {
  let appearance = theme;
  let rawUnavailable = false, authRequired = false, transientDecodeFailures = 0;
  const decodeRaw = decodeAppMapTiles;
  const interaction = createMapInteraction();
  const group = new THREE.Group();
  group.visible = false;
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = RESOLUTION;
  const ctx = canvas.getContext('2d')!;
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 8;
  const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE), material);
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; group.add(ground);
  const backdropCanvas = document.createElement('canvas');
  backdropCanvas.width = backdropCanvas.height = BACKDROP_RESOLUTION;
  const backdropContext = backdropCanvas.getContext('2d')!;
  const backdropTexture = new THREE.CanvasTexture(backdropCanvas);
  backdropTexture.colorSpace = THREE.SRGBColorSpace;
  const backdropMaterial = new THREE.MeshStandardMaterial({map: backdropTexture, roughness: 1, metalness: 0});
  const backdrop = new THREE.Mesh(new THREE.PlaneGeometry(BACKDROP_SIZE, BACKDROP_SIZE), backdropMaterial);
  backdrop.rotation.x = -Math.PI / 2; backdrop.position.y = -.04; group.add(backdrop);
  let buildingsMesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | undefined;
  let landmarkBounds: number[][] = [];
  let roadsMesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | undefined;
  let laneMesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | undefined;
  let deckEdges: RoadDeckEdge[] = [];
  const deckCell = 30;
  let deckIndex = new Map<string,RoadDeckEdge[]>();
  const deckKey = (x:number,z:number) => `${Math.floor(x/deckCell)}/${Math.floor(z/deckCell)}`;
  function indexDeckEdges() {
    deckIndex = new Map();
    const limit=Math.ceil((SIZE/2+20)/deckCell);
    for(const edge of deckEdges) {
      const margin=edge.width/2+2;
      const west=Math.max(-limit,Math.floor((Math.min(edge.a[0],edge.b[0])-margin)/deckCell));
      const east=Math.min(limit,Math.floor((Math.max(edge.a[0],edge.b[0])+margin)/deckCell));
      const north=Math.max(-limit,Math.floor((Math.min(edge.a[1],edge.b[1])-margin)/deckCell));
      const south=Math.min(limit,Math.floor((Math.max(edge.a[1],edge.b[1])+margin)/deckCell));
      for(let x=west;x<=east;x++) for(let z=north;z<=south;z++) {
        const key=`${x}/${z}`;
        if(!deckIndex.has(key)) deckIndex.set(key,[]);
        deckIndex.get(key)!.push(edge);
      }
    }
  }
  function deckHeightAt(x:number,z:number,direction:readonly [number,number],preferredHeight?:number) {
    return nearestRoadHeight(deckIndex.get(deckKey(x,z)) || [],x,z,direction,preferredHeight);
  }
  let revision = 0, roadRevision = 0;
  function clearRoads() { if (roadsMesh) { roadsMesh.removeFromParent(); roadsMesh.geometry.dispose(); roadsMesh.material.dispose(); roadsMesh=undefined; } }
  function clearLanes() { if(laneMesh) {laneMesh.removeFromParent();laneMesh.geometry.dispose();laneMesh.material.dispose();laneMesh=undefined;} }
  function clearBuildings() { if (buildingsMesh) { buildingsMesh.removeFromParent(); buildingsMesh.geometry.dispose(); (buildingsMesh.material.userData.buildingAtlas as THREE.Texture | undefined)?.dispose(); (buildingsMesh.material.userData.buildingMre as THREE.Texture | undefined)?.dispose(); buildingsMesh.material.dispose(); buildingsMesh=undefined; } }
  function buildingSource(tiles: Tile[]) {
    return tiles.flatMap(tile => tile.buildings || []).filter(building =>
      !landmarkBounds.some(([west, north, east, south]) => building.parts?.some(part => {
        const points = part.ring;
        if (!points?.length) return false;
        const longitude = points.reduce((sum, point) => sum + point[0], 0) / points.length;
        const latitude = points.reduce((sum, point) => sum + point[1], 0) / points.length;
        return west <= longitude && longitude <= east && south <= latitude && latitude <= north;
      })));
  }
  const cache = new Map<string, { tile: Tile; at: number }>();
  const laneCache = new Map<string,{lines:number[][][];kinds:number[];at:number}>();
  function cachedLanes(key:string) {
    const entry=laneCache.get(key);
    if(!entry) return undefined;
    if(Date.now()-entry.at>browserMapTileTtlMs()) {laneCache.delete(key);return undefined;}
    return entry;
  }
  let visibleKeys = new Set<string>();
  function pruneCache() {
    for (const key of cache.keys()) {
      if (cache.size <= 64) break;
      if (!visibleKeys.has(key)) cache.delete(key);
    }
  }
  let anchor: MapPoint | undefined, latest: MapPoint | undefined;
  let displayedTiles: Tile[] = [];
  let displayedBuildingCount = 0, displayedAppearance = appearance;
  let heading = 0, generation = 0, disposed = false, ready = false;
  let interacting = false, pendingPresentation: (() => boolean) | undefined, pendingBuildings = false;
  let pendingLanes: (() => void) | undefined;
  let request: AbortController | undefined, retryAfter = 0;
  let laneRequest: AbortController | undefined, laneGeneration = 0, laneKey: string | undefined;
  let laneGuidance = false, laneProgress = 0, laneProgressBucket = -1;
  function displayLanes(lines:number[][][],kinds:number[],point:MapPoint) {
    clearLanes();
    if (!laneGuidance || !route) return;
    const selectedKinds:number[]=[];
    const selected=navigationLaneBoundaries(lines,route,laneProgress,point,kinds,selectedKinds);
    laneMesh=createLaneMesh(selected,point,SIZE,deckHeightAt,selectedKinds);
    if(laneMesh) {laneMesh.material.color.set(appearance==='night'?'#b8c9d7':'#f8fbfa');group.add(laneMesh);}
  }
  async function loadLanes(point:MapPoint) {
    if (!laneGuidance || !route) return;
    const tiles=laneViewportTiles(point,SIZE);
    const key=tiles.map(([x,y])=>`${x}/${y}`).join(';');
    const render=()=>{
      if (interacting) { pendingLanes = render; return; }
      pendingLanes = undefined;
      const cached=tiles.map(([x,y])=>cachedLanes(`${x}/${y}`)).filter(entry=>entry!==undefined);
      displayLanes(cached.flatMap(entry=>entry.lines),cached.flatMap(entry=>entry.kinds),anchor || point);
    };
    if(laneRequest && laneKey===key) { render(); return; }
    laneRequest?.abort();
    const id=++laneGeneration;
    laneKey=key;
    render();
    if(tiles.every(([x,y])=>cachedLanes(`${x}/${y}`)!==undefined)) {laneRequest=undefined;return;}
    const controller=new AbortController(); laneRequest=controller;
    try {
      const missing=tiles.filter(([x,y])=>cachedLanes(`${x}/${y}`)===undefined);
      const stored=await readMapTiles('lanes',missing.map(([x,y])=>[15,x,y]));
      if(disposed || controller.signal.aborted || id!==laneGeneration) return;
      for(const [x,y] of missing) {
        const saved=stored.get(`15/${x}/${y}`)?.tile;
        if(Array.isArray(saved?.laneBoundaries)) laneCache.set(`${x}/${y}`,{
          lines:saved.laneBoundaries as number[][][],
          kinds:Array.isArray(saved.laneBoundaryKindsRaw) && saved.laneBoundaryKindsRaw.length===saved.laneBoundaries.length
            ? saved.laneBoundaryKindsRaw : saved.laneBoundaries.map(()=>0),
          at:stored.get(`15/${x}/${y}`)!.at});
      }
      render();
      for(const [x,y] of missing) {
        if(cachedLanes(`${x}/${y}`)!==undefined) continue;
        if(disposed || controller.signal.aborted || id!==laneGeneration) return;
        try {
          const deadline=Date.now()+60000;
          let response;
          do {
            response=await axios.post('/api/amap-app/map',{layer:'lanes',level:15,tiles:[[x,y]]},
              {signal:controller.signal,timeout:30000});
            if(response.status!==202 || !response.data.data?.pending) break;
            if(Date.now()>deadline) break;
            await new Promise(resolve=>setTimeout(resolve,750));
          } while(!controller.signal.aborted);
          if(disposed || controller.signal.aborted || id!==laneGeneration) return;
          const tile=response?.data.status==='ok' ? response.data.data?.tiles?.[0] : undefined;
          if(tile?.level!==15 || tile.x!==x || tile.y!==y || !Array.isArray(tile.laneBoundaries)) continue;
          laneCache.set(`${x}/${y}`,{lines:tile.laneBoundaries,
            kinds:Array.isArray(tile.laneBoundaryKindsRaw) && tile.laneBoundaryKindsRaw.length===tile.laneBoundaries.length
              ? tile.laneBoundaryKindsRaw : tile.laneBoundaries.map(()=>0),at:Date.now()});
          void storeMapTiles('lanes',[tile]);
          render();
        } catch { if(controller.signal.aborted) return; /* Keep other tiles usable. */ }
      }
      const visible=new Set(tiles.map(([x,y])=>`${x}/${y}`));
      for(const old of laneCache.keys()) if(laneCache.size>24 && !visible.has(old)) laneCache.delete(old);
    } catch { /* LNDS is optional; the native base map stays usable. */ }
    finally {if(laneRequest===controller) laneRequest=undefined;}
  }
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
    if (disposed || interacting || authRequired || !ready || request || !route || warmTimer !== undefined || warmRequest) return;
    warmTimer = setTimeout(() => { warmTimer = undefined; void warmRoute(); }, delay);
  }
  async function warmRoute() {
    if (disposed || interacting || authRequired || !ready || request || !route || warmRequest) return;
    const tile = warmTiles.find(t => browserWarmKeys.has(t.join('/')) && !cache.has(t.join('/')) && !browserAttempted.has(t.join('/')))
      || warmTiles.find(t => !cache.has(t.join('/')) && !warmAttempted.has(t.join('/')));
    if (!tile) return;
    const key = tile.join('/'), token = warmGeneration;
    const controller = new AbortController(); warmRequest = controller;
    let delay = 750;
    try {
      const stored=await readMapTiles('full',[tile]);
      if(disposed || token!==warmGeneration) return;
      const saved=stored.get(key);
      if(saved) {cache.set(key,{tile:saved.tile as Tile,at:saved.at});pruneCache();warmAttempted.add(key);browserAttempted.add(key);return;}
      // Transfer nearby route tiles as BMD in the warmup request itself.
      // Distant tiles warm only the server and return no browser payload.
      const onDevice = browserWarmKeys.has(key);
      const raw = !rawUnavailable;
      const payload = { level: tile[0], tiles: [[tile[1], tile[2]]] };
      const options = { signal: controller.signal, timeout: onDevice && !raw ? 70000 : 15000 };
      const response = onDevice
        ? await postMapTiles(raw ? '/api/amap-app/map/bmd/prefetch' : '/api/amap-app/map', payload, options)
        : await axios.post(raw ? '/api/amap-app/map/bmd/prefetch' : '/api/amap-app/map/prefetch', payload, options);
      if (disposed || token !== warmGeneration) return;
      if (response.data?.status === 'need_login') {
        authRequired=true; report('TMC 登录已失效，请登录后重试地图',ready); return;
      }
      if (response.status === 202) delay = 2000;
      else {
        if (onDevice && response.data?.status === 'ok') {
          let result = response.data.data?.tiles?.[0] as Tile | undefined;
          if (raw && result && !result.error) {
            try { result=(await decodeRaw([result],response.data.data.paints || {}))[0]; transientDecodeFailures=0; }
            catch (error) {
              if (rawBmdDecodeUnsupported(error) || ++transientDecodeFailures >= 2) rawUnavailable=true;
              result=undefined;
            }
          }
          if (result && !result.error && !result.missingLayers?.length &&
              result.level === tile[0] && result.x === tile[1] && result.y === tile[2]) {
            cache.set(key, { tile: result, at: Date.now() });
            void storeMapTiles('full',[result]);
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
  function paintBackdrop(tiles: Tile[], paintAnchor: MapPoint) {
    const ctx = backdropContext, scale = BACKDROP_RESOLUTION / BACKDROP_SIZE;
    const bounds = groundBounds(paintAnchor, BACKDROP_SIZE / 2);
    const view: GeometryBounds = [bounds[0], bounds[3], bounds[2], bounds[1]];
    const pixel = (point: number[]) => {
      const [x,z] = groundOffset(point, paintAnchor);
      return [BACKDROP_RESOLUTION / 2 + x * scale, BACKDROP_RESOLUTION / 2 + z * scale];
    };
    const path = (points: number[][], close = false) => {
      points.forEach((point, index) => {
        const [x,y] = pixel(point); if (index) ctx.lineTo(x,y); else ctx.moveTo(x,y);
      });
      if (close) ctx.closePath();
    };
    ctx.globalAlpha = 1; ctx.fillStyle = appearance === 'night' ? '#1b2634' : '#dce5e5';
    ctx.fillRect(0,0,BACKDROP_RESOLUTION,BACKDROP_RESOLUTION);
    for (const tile of [...tiles].sort((a,b) => a.level-b.level)) for (const surface of tile.surfaces || []) {
      if (!geometryInView(surface.rings, view, surface.bounds)) continue;
      const paint = (surface.paints?.[appearance] || surface.paints?.day)?.find((p: any) => ZOOM >= p.minZoom && ZOOM <= p.maxZoom);
      if (ZOOM < surface.minZoom || ZOOM > surface.maxZoom || !paint) continue;
      ctx.beginPath(); surface.rings.forEach((ring: number[][]) => path(ring,true));
      ctx.fillStyle = paint.color; ctx.globalAlpha = paint.opacity ?? 1; ctx.fill('evenodd');
    }
    ctx.globalAlpha = 1; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const roads = tiles.flatMap(tile => (tile.collection?.features || []).filter(feature => {
      const style = feature.properties?.style;
      return feature.geometry?.type === 'LineString' && (style == null || (ZOOM >= (style & 31) && ZOOM <= ((style >> 5) & 31)))
        && geometryInView(feature.geometry.coordinates, view, feature.bbox);
    }).map(feature => ({feature, paint: (tile.roadPaints?.[appearance] || tile.roadPaints?.day)?.[feature.properties?.paintKey]
      ?.find(paint => ZOOM >= paint.minZoom && ZOOM <= paint.maxZoom)})));
    roads.sort((a,b) => (b.paint?.outerWidth || 30) - (a.paint?.outerWidth || 30));
    for (const layer of ['outer','inner'] as const) for (const {feature,paint} of roads) {
      ctx.beginPath(); path(feature.geometry.coordinates);
      ctx.strokeStyle = paint?.[layer].color || (appearance === 'night' ? (layer === 'outer' ? '#253244' : '#536278') : (layer === 'outer' ? '#829296' : '#f7f9f8'));
      ctx.globalAlpha = paint?.[layer].opacity ?? 1;
      ctx.lineWidth = Math.max(.35, roadWidth(paint?.[layer === 'outer' ? 'outerWidth' : 'innerWidth'], layer === 'outer') * scale);
      ctx.stroke();
    }
    ctx.globalAlpha = 1; backdropTexture.needsUpdate = true;
  }
  function paint(tiles: Tile[], paintAnchor: MapPoint) {
    const bounds = groundBounds(paintAnchor, SIZE / 2 + 40);
    const view: GeometryBounds = [bounds[0], bounds[3], bounds[2], bounds[1]];
    const scale = RESOLUTION / SIZE;
    const pixel = (p: number[]) => {
      const [x,z] = groundOffset(p, paintAnchor); return [RESOLUTION/2+x*scale, RESOLUTION/2+z*scale];
    };
    const path = (points: number[][], close: boolean) => {
      points.forEach((p,i) => { const [x,y]=pixel(p); if (i) ctx.lineTo(x,y); else ctx.moveTo(x,y); });
      if (close) ctx.closePath();
    };
    ctx.globalAlpha = 1; ctx.fillStyle = appearance==='night'?'#1b2634':'#dce5e5'; ctx.fillRect(0,0,RESOLUTION,RESOLUTION);
    // Fetch priority differs from paint order: broad App surfaces must remain
    // underneath the more detailed navigation tiles.
    for (const tile of [...tiles].sort((a,b)=>a.level-b.level)) for (const surface of tile.surfaces || []) {
      if (!geometryInView(surface.rings, view, surface.bounds)) continue;
      if (ZOOM < surface.minZoom || ZOOM > surface.maxZoom) continue;
      const paint = (surface.paints?.[appearance] || surface.paints?.day)?.find((p: any) => ZOOM >= p.minZoom && ZOOM <= p.maxZoom);
      if (!paint) continue;
      ctx.beginPath(); surface.rings.forEach((ring: number[][]) => path(ring,true));
      ctx.fillStyle = paint.color; ctx.globalAlpha = paint.opacity ?? 1; ctx.fill('evenodd');
    }
    ctx.globalAlpha = 1; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const roads = tiles.flatMap(t => (t.collection?.features || []).filter(f => {
      const style = f.properties?.style;
      return f.geometry?.type === 'LineString' && (style == null || (ZOOM >= (style & 31) && ZOOM <= ((style >> 5) & 31)))
        && geometryInView(f.geometry.coordinates, view, f.bbox);
    }).map(f=>({...f,paint:(t.roadPaints?.[appearance] || t.roadPaints?.day)?.[f.properties?.paintKey]?.find(p=>ZOOM>=p.minZoom && ZOOM<=p.maxZoom)})));
    // Preserve App rule width ratios and colors; 0.1 converts style units to
    // TMC ground metres. This is cartographic width, not measured lane geometry.
    const styled=roads.sort((a,b)=>(b.paint?.outerWidth || 30)-(a.paint?.outerWidth || 30))
      .flatMap(road=>roadSpans(road.geometry.coordinates,road.properties?.levelMarkers).map(span=>({road,span})));
    deckEdges=[];
    const smooth=(value:number)=>{const t=Math.max(0,Math.min(1,value));return t*t*(3-2*t);};
    for(const {road,span} of styled) {
      const points=span.points.map(point=>groundOffset(point,paintAnchor));
      const lengths=[0];
      for(let i=1;i<points.length;i++) lengths.push(lengths[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]));
      const total=lengths[lengths.length-1], ramp=Math.min(35,total/3);
      const height=(distance:number)=>span.level*4*Math.min(span.rampStart?smooth(distance/ramp):1,span.rampEnd?smooth((total-distance)/ramp):1)+.06;
      const width=roadWidth(road.paint?.outerWidth,true);
      for(let i=1;i<points.length;i++) if(lengths[i]>lengths[i-1])
        deckEdges.push({a:points[i-1],b:points[i],from:height(lengths[i-1]),to:height(lengths[i]),width,level:span.level});
    }
    indexDeckEdges();
    clearRoads();
    const decks:THREE.BufferGeometry[]=[];
    let deckVertices=0;
    for (const layer of ['outer','inner'] as const) {
      for (const {road,span} of styled) {
        const p=road.paint, stroke=p?.[layer];
        const width=p?.[layer==='outer'?'outerWidth':'innerWidth'];
        if (span.level>0) {
          const geometry=roadDeckGeometry(span,paintAnchor,roadWidth(width,layer==='outer'),layer==='inner'?.025:0);
          if(geometry) {
            const count=geometry.getAttribute('position').count;
            if(deckVertices+count<=250000) {
              const color=new THREE.Color(stroke?.color || (appearance==='night'?(layer==='outer'?'#253244':'#536278'):(layer==='outer'?'#829296':'#f7f9f8')));
              const colors=new Float32Array(count*3);
              for(let i=0;i<count;i++) color.toArray(colors,i*3);
              geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));decks.push(geometry);deckVertices+=count;
              continue;
            }
            geometry.dispose();
          }
        }
        ctx.strokeStyle=stroke?.color || (appearance==='night'?(layer==='outer'?'#253244':'#536278'):(layer==='outer'?'#bac8cc':'#f7f9f8'));
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
      ctx.strokeStyle=appearance==='night'?'#1b2634':'#ffffff';ctx.lineWidth=5;ctx.strokeText(name,x,y);
      ctx.fillStyle=appearance==='night'?'#9caec0':'#516873';ctx.fillText(name,x,y);
    }
    texture.needsUpdate = true;
  }
  async function load(point: MapPoint) {
    if (authRequired) return;
    cancelWarm();
    const id=++generation; request?.abort(); const controller=new AbortController(); request=controller;
    pendingPresentation = undefined;
    // Keep the previous georeferenced patch visible until the replacement is
    // complete. Hiding it here caused a full grey flash every 120 m.
    report('正在加载混合地图…',ready);
    const bounds=groundBounds(point,SIZE/2);
    const tiles=viewportTiles(12,...groundBounds(point,BACKDROP_SIZE/2));
    tiles.push(...viewportTiles(ZOOM,...bounds).filter(tile => tile[0] === 14));
    // Building source is level 15 (type 5), independent of the even road levels.
    const n=2**15, x=(v:number)=>Math.max(0,Math.min(n-1,Math.floor((v+180)/360*n))), y=(v:number)=>Math.max(0,Math.min(n-1,Math.floor((90-v)/180*n)));
    for(let xx=x(bounds[0]);xx<=x(bounds[2]);xx++) for(let yy=y(bounds[1]);yy<=y(bounds[3]);yy++) tiles.push([15,xx,yy]);
    visibleKeys = new Set(tiles.map(tile => tile.join('/')));
    const collected: Tile[]=[]; let partial=false, buildingFailed=false;
    const present = (complete: boolean) => {
      if (!collected.some(t => t.collection?.features.length || t.surfaces?.length)) return false;
      if (interacting) {
        // Downloads/worker decoding keep warming the cache, while the current
        // meshes remain untouched during a pinch, wheel, pan or camera zoom.
        // Coalesce arrivals into one presentation after the gesture settles.
        pendingPresentation = () => !disposed && id === generation && present(complete);
        return true;
      }
      pendingPresentation = undefined;
      const moved = !anchor || anchor[0] !== point[0] || anchor[1] !== point[1] || displayedAppearance !== appearance;
      const changed = (select: (tile: Tile) => boolean) => {
        const before = displayedTiles.filter(select), after = collected.filter(select);
        return moved || before.length !== after.length || before.some((tile, index) => tile !== after[index]);
      };
      const roadsChanged = changed(tile => !!tile.collection?.features?.length || !!tile.surfaces?.length);
      const buildingsChanged = pendingBuildings || changed(tile => !!tile.buildings?.length);
      if (roadsChanged) {paintBackdrop(collected,point); paint(collected,point); roadRevision++;}
      if (buildingsChanged) {
        clearBuildings();
        const buildings=createBuildingMeshes(buildingSource(collected),point,appearance);
        displayedBuildingCount=buildings.count; buildingsMesh=buildings.mesh;
        if(buildingsMesh) group.add(buildingsMesh);
      }
      pendingBuildings = false;
      anchor=[...point]; displayedTiles=[...collected]; displayedAppearance=appearance;
      if (roadsChanged || buildingsChanged) revision++;
      retryAfter=0; ready=true; group.visible=true; align();
      // The lane overlay needs the detailed road deck, not every distant
      // surface tile. Start it as soon as the priority map is visible.
      if (laneGuidance) {if (roadsChanged) void loadLanes(point);}
      else clearLanes();
      if (complete) {
        const detail=roadsMesh?' · 立交层高示意':'';
        const status=(buildingFailed?'混合地图 · 建筑图层不完整，可重试':partial?'混合地图 · 部分图层缺失':displayedBuildingCount ? `App 立体建筑 · ${displayedBuildingCount} 栋` : '混合地图 · 此处暂无建筑数据')+detail;
        report(status,true);
      } else report('App 地图已显示 · 正在补充建筑与地表…',true);
      return true;
    };
    try {
      const collect = () => {
        collected.splice(0, collected.length, ...tiles.flatMap(tile => cache.get(tile.join('/'))?.tile || []));
      };
      for (const [key, saved] of readMemoryMapTiles('full', tiles)) cache.set(key, {tile: saved.tile as Tile, at: saved.at});
      collect();
      present(false);
      // Fill the visible map before waiting for optional building downloads.
      // Previously a slow level-15 request held every background layer behind
      // it, and their completed batches were not painted until the very end.
      const priority = [14,12,3,6,8,10,15];
      const levels=[...new Set(tiles.map(t=>t[0]))].sort((a,b)=>
        priority.indexOf(a)-priority.indexOf(b));
      const batches = levels.flatMap(level => {
        const keys = tiles.filter(tile => tile[0] === level).sort((a, b) =>
          mapTileDistance(a, point[0], point[1]) - mapTileDistance(b, point[0], point[1]));
        const first = level === 14 ? keys.splice(0,1) : [];
        return [...(first.length ? [first] : []), ...Array.from({length: Math.ceil(keys.length / 4)}, (_, index) => keys.slice(index * 4, index * 4 + 4))];
      });
      for (const keys of batches) {
        const level = keys[0][0];
        try {
        const diskKeys = keys.filter(tile => {
          const entry = cache.get(tile.join('/'));
          return !entry || Date.now() - entry.at > browserMapTileTtlMs();
        });
        if (diskKeys.length) {
          // Decoding every cached background/building tile before presenting
          // a cached road made a 2D -> 3D switch wait for the entire viewport.
          const stored = await readMapTiles('full', diskKeys);
          if (disposed || id !== generation) return;
          for (const [key,saved] of stored) cache.set(key,{tile: saved.tile as Tile, at: saved.at});
          if (stored.size) {collect(); present(false);}
        }
        const missing=keys.filter(t=>!cache.has(t.join('/')) || Date.now()-cache.get(t.join('/'))!.at>browserMapTileTtlMs());
        if (missing.length) {
          let response; const deadline=Date.now()+90000;
          let raw = !rawUnavailable;
          do {
            try {
              response=await postMapTiles(raw?'/api/amap-app/map/bmd':'/api/amap-app/map',
                {level,tiles:missing.map(t=>t.slice(1))},{signal:controller.signal,timeout:70000});
            } catch (error) {
              if (!raw || controller.signal.aborted || !rawBmdUnsupported(error)) throw error;
              raw = false; rawUnavailable = true; continue;
            }
            if (response.data?.status === 'need_login') {
              authRequired = true;
              report('TMC 登录已失效，请登录后重试地图',ready);
              throw new Error('map login required');
            }
            if (response.status!==202 || !response.data.data?.pending) break;
            if (Date.now()>deadline) throw new Error('timeout');
            await new Promise(resolve=>setTimeout(resolve,750));
            if (controller.signal.aborted) return;
          } while (true);
          if (disposed || id!==generation) return;
          if (response.data.status!=='ok') throw new Error('map unavailable');
          let downloaded=response.data.data.tiles as Tile[];
          if (raw) {
            try { downloaded=await decodeRaw(downloaded,response.data.data.paints || {}); transientDecodeFailures=0; }
            catch (error) {
              if (!rawBmdDecodeUnsupported(error) && ++transientDecodeFailures < 2) throw error;
              rawUnavailable=true;
              response=await axios.post('/api/amap-app/map',{level,tiles:missing.map(t=>t.slice(1))},
                {signal:controller.signal,timeout:70000});
              if (response.data?.status === 'need_login') {
                authRequired=true; report('TMC 登录已失效，请登录后重试地图',ready);
                throw new Error('map login required');
              }
              if (response.data.status!=='ok') throw new Error('map fallback unavailable');
              downloaded=response.data.data.tiles as Tile[];
            }
          }
          await waitForMapIdle();
          if (disposed || id !== generation) return;
          for (const tile of downloaded) {
            if (tile.error) { partial=true; if(level===15) buildingFailed=true; continue; }
            if (tile.missingLayers?.length) { partial=true; if(level===15) buildingFailed=true; }
            cache.set(`${tile.level}/${tile.x}/${tile.y}`,{tile,at:tile.missingLayers?.length?0:Date.now()});
          }
          void storeMapTiles('full',downloaded);
        }
        collect();
        if(!disposed && id===generation) present(false);
        } catch(error) {
          if(level===14 || authRequired) throw error;
          if(level===15) buildingFailed=true;
          partial=true;
        }
      }
      if (disposed || id!==generation) return;
      if (!present(true)) throw new Error('empty');
      pruneCache();
    } catch {
      if (disposed || id!==generation) return;
      if (authRequired) return;
      retryAfter=Date.now()+30000;
      report(ready ? '新地图加载失败 · 保持上一幅地图，可重试' : '地图暂不可用 · 可重试',ready);
    } finally {
      if (id===generation) {
        request=undefined;
        // A moving car may have crossed the patch while the helper was busy.
        // Finish this download (and cache it) before loading the latest patch;
        // repeatedly aborting at 120 m can starve every request on highways.
        const next=latest;
        if (!disposed && !authRequired && next && anchor &&
            Math.hypot(...groundOffset(next,anchor))>120 && Date.now()>retryAfter) void load(next);
        else scheduleWarm();
      }
    }
  }
  return { group,
    setInteracting(value: boolean) {
      interacting = value;
      interaction.set(value);
      if (value) { cancelWarm(); return; }
      if (!value && pendingPresentation && !disposed) {
        const present = pendingPresentation; pendingPresentation = undefined;
        present();
      }
      if (!value && pendingBuildings && !disposed && anchor) {
        pendingBuildings = false;
        clearBuildings();
        buildingsMesh=createBuildingMeshes(buildingSource(displayedTiles),anchor,appearance).mesh;
        if (buildingsMesh) group.add(buildingsMesh);
        revision++;
      }
      if (pendingLanes && !disposed) pendingLanes();
      if (!disposed) scheduleWarm();
    },
    setTheme(nextTheme: 'day' | 'night') {
      if (appearance===nextTheme) return;
      appearance=nextTheme;
      if (!anchor || !displayedTiles.length) return;
      paintBackdrop(displayedTiles,anchor); paint(displayedTiles,anchor);
      clearBuildings();
      buildingsMesh=createBuildingMeshes(buildingSource(displayedTiles),anchor,appearance).mesh;
      if(buildingsMesh) group.add(buildingsMesh);
      if(laneMesh) laneMesh.material.color.set(appearance==='night'?'#b8c9d7':'#f8fbfa');
      revision++; roadRevision++;
    },
    setLandmarkBounds(bounds: number[][]) {
      landmarkBounds = bounds.filter(box => box.length === 4 && box.every(Number.isFinite));
      if (!anchor || !displayedTiles.length) return;
      if (interacting) { pendingBuildings = true; return; }
      clearBuildings();
      buildingsMesh=createBuildingMeshes(buildingSource(displayedTiles),anchor,appearance).mesh;
      if (buildingsMesh) group.add(buildingsMesh);
      revision++;
    },
    revision() { return revision; },
    roadRevision() { return roadRevision; },
    roadHeight(point: MapPoint, direction: readonly [number,number]) {
      if(!anchor) return 0;
      const [x,z]=groundOffset(point,anchor);
      return deckHeightAt(x,z,direction);
    },
    setRoute(nextRoute?: AppRoute, progress = 0, navigating = false) {
      const bucket = Math.floor(Math.max(0, Number.isFinite(progress) ? progress : 0) / 500);
      const guided = !!nextRoute && navigating;
      const laneBucket = Math.floor(Math.max(0, Number.isFinite(progress) ? progress : 0) / 25);
      const laneChanged = laneGuidance !== guided || route !== nextRoute || laneProgressBucket !== laneBucket;
      const warmChanged = route !== nextRoute || routeBucket !== bucket;
      if (warmChanged) {
        cancelWarm();
        if (route !== nextRoute) { warmAttempted.clear(); browserAttempted.clear(); }
        route = nextRoute; routeBucket = bucket;
        warmTiles = route ? route3DTiles(route, progress) : [];
        browserWarmKeys = new Set([14, 15].flatMap(level => warmTiles.filter(t => t[0] === level).slice(0, 4))
          .map(tile => tile.join('/')));
      }
      laneGuidance = guided; laneProgress = progress; laneProgressBucket = laneBucket;
      if (!guided && laneChanged) {
        laneGeneration++; laneRequest?.abort(); laneRequest=undefined; clearLanes();
      } else if (laneChanged && anchor && ready) void loadLanes(anchor);
      if (warmChanged) scheduleWarm();
    },
    update(point: MapPoint, angle: number, groundY: number) {
      latest=point; if (Number.isFinite(angle)) heading=angle;
      group.position.y=groundY; align();
      const offset=anchor?groundOffset(point,anchor):[Infinity,Infinity];
      if ((!interacting || (!anchor && !pendingPresentation)) && !authRequired && !request && (!anchor || (Math.hypot(...offset)>120 && Date.now()>retryAfter) ||
          (!ready && Date.now()>retryAfter))) void load(point);
    },
    retry() { authRequired=false; if (latest) void load(latest); },
    dispose() { disposed=true; interaction.dispose(); pendingPresentation=undefined; pendingLanes=undefined; cancelWarm(); generation++; request?.abort(); laneGeneration++; laneRequest?.abort(); clearLanes(); clearBuildings(); clearRoads(); deckEdges=[]; deckIndex.clear(); group.removeFromParent(); ground.geometry.dispose(); material.dispose(); texture.dispose(); backdrop.geometry.dispose(); backdropMaterial.dispose(); backdropTexture.dispose(); cache.clear(); laneCache.clear(); },
  };
}
