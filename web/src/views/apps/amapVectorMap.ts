import {decodeAppMapTiles} from './amapMapWorker';
import {createMapInteraction, waitForMapIdle} from './amapMapWork';
import L from 'leaflet';
import axios from 'axios';
import { postMapTiles, rawBmdDecodeUnsupported, rawBmdUnsupported } from './amapBmdTransport';
import { createMapRenderQueue } from './mapRenderQueue';
import { routeCorridorTiles, surroundingTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';
import { mapTileDistance, viewportTiles } from './amapViewport';
import { layoutPlaceLabels, type PlaceLabel } from './amapPlaceLabels';
import { browserMapTileTtlMs, readMemoryMapTiles, readMapTiles, storeMapTiles } from './amapBrowserTileCache';
import {geometryInView, type GeometryBounds} from './amapGeometryBounds';

export type AppMapAppearance = { theme: 'day' | 'night'; surfaces: boolean; roads: boolean; labels: boolean; transit: boolean; places: boolean };
type RoadPaint = { minZoom: number; maxZoom: number; outerWidth: number; innerWidth: number;
  outer: { color: string; opacity: number }; inner: { color: string; opacity: number } };
type RoadPaints = Record<string, Record<string, RoadPaint[]>>;

export function appRoadPaint(paints: RoadPaints | undefined, theme: AppMapAppearance['theme'], key: string | undefined, zoom: number) {
  const stops = key ? (paints?.[theme]?.[key] || paints?.day?.[key]) : undefined;
  return stops?.find(stop => zoom >= stop.minZoom && zoom <= stop.maxZoom);
}

export function attachAppMap(map: L.Map, report: (message: string) => void) {
  let appearance: AppMapAppearance = { theme: 'day', surfaces: true, roads: true, labels: true, transit: true, places: true };
  const rotating = map.getPane('rotatePane'), upright = map.getPane('norotatePane');
  map.createPane('appSurfaces', rotating).style.zIndex = '200';
  const surfaceRenderer = L.canvas({ pane: 'appSurfaces', padding: .2 });
  const surfaces = L.layerGroup().addTo(map);
  map.createPane('appRoads', rotating).style.zIndex = '210';
  map.createPane('appRoadFills', rotating).style.zIndex = '211';
  map.createPane('appRoadLabels', upright).style.zIndex = '220';
  map.createPane('appPlaceLabels', upright).style.zIndex = '450';
  const renderer = L.canvas({ pane: 'appRoads', padding: .2 });
  const fillRenderer = L.canvas({ pane: 'appRoadFills', padding: .2 });
  const roads = L.layerGroup().addTo(map), labels = L.layerGroup().addTo(map);
  const cache = new Map<string, { time: number; collection?: any; surfaces?: any[]; transit?: any[]; placeLabels?: PlaceLabel[];
    roadPaints?: RoadPaints; missingLayers?: string[] }>();
  const hydrated = new Set<string>();
  let route: AppRoute | undefined, routeBucket = -1, routeGeneration = 0, routeTiles: number[][] = [];
  const routeAttempted = new Set<string>();
  let request: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined;
  let requestIsPrefetch = false;
  function queueLoad(delay: number) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = undefined; void load(); }, delay);
  }
  let disposed = false, generation = 0;
  let rawUnavailable = false, authRequired = false, transientDecodeFailures = 0;
  const decodeRaw = decodeAppMapTiles;
  const interaction = createMapInteraction();
  function visible() {
    const b = map.getBounds();
    return viewportTiles(map.getZoom(), b.getWest(), b.getNorth(), b.getEast(), b.getSouth());
  }

  const renderQueue = createMapRenderQueue(() => report('地图绘制失败，请重试'));
  let moving = false, zooming = false, active = true, following = false;
  let inputActive = false, inputTimer: ReturnType<typeof setTimeout> | undefined;
  const inputPointers = new Set<number>();
  const container = map.getContainer?.();
  function rawInput(event: Event) {
    if (!active || disposed) return;
    if (event.type === 'pointerdown') inputPointers.add((event as PointerEvent).pointerId);
    inputActive = true; interaction.set(true); pauseDrawing();
    if (inputTimer) clearTimeout(inputTimer);
    if (event.type === 'wheel') inputTimer = setTimeout(endInput, 180);
  }
  function endInput() {
    if (inputTimer) clearTimeout(inputTimer);
    inputTimer = undefined;
    if (inputPointers.size) return;
    inputActive = false;
    schedule();
  }
  function endPointer(event: PointerEvent) {
    if (inputPointers.delete(event.pointerId) && !inputPointers.size) endInput();
  }
  function endTouch(event: TouchEvent) {if (!event.touches.length) endInput();}
  container?.addEventListener('pointerdown', rawInput, {passive: true, capture: true});
  container?.addEventListener('wheel', rawInput, {passive: true, capture: true});
  container?.addEventListener('touchstart', rawInput, {passive: true, capture: true});
  window.addEventListener('pointerup', endPointer); window.addEventListener('pointercancel', endPointer);
  window.addEventListener('touchend', endTouch); window.addEventListener('touchcancel', endTouch);
  let drawnView = '';
  function draw(tiles: number[][], force = false) {
    if (disposed || moving || zooming || inputActive || !active) return;
    const bounds = map.getBounds(), width = bounds.getEast() - bounds.getWest(), height = bounds.getNorth() - bounds.getSouth();
    // Moving within a large source tile must refresh the culled viewport too.
    // Quantization keeps tiny following pans from restarting the geometry pass.
    const view = `${Math.floor(map.getZoom())}:${Math.floor(bounds.getWest() / (width / 8 || 1))}/${Math.floor(bounds.getSouth() / (height / 8 || 1))}:${tiles.map(tile => tile.join('/')).join('|')}`;
    if (!force && view === drawnView) return;
    drawnView = view;
    renderQueue.start(drawSteps(tiles));
  }
  const rendered = new Map<string, { data: unknown; style: string; layer: L.Layer; group: L.LayerGroup }>();
  function retain(key: string, data: unknown, style: string, group: L.LayerGroup, create: () => L.Layer, wanted: Set<string>, restyle?: (layer: L.Layer) => void) {
    wanted.add(key);
    const old = rendered.get(key);
    if (old && old.data === data) {
      if (old.style === style) return;
      if (restyle) { restyle(old.layer); old.style = style; return; }
    }
    const layer = create().addTo(group);
    if (old) old.group.removeLayer(old.layer);
    rendered.set(key, { data, style, layer, group });
  }
  function* drawSteps(tiles: number[][]): Generator<void> {
    const wanted = new Set<string>();
    const roadFeatures: { tileKey: string; index: number; feature: any; paint?: RoadPaint }[] = [];
    const zoom = Math.floor(map.getZoom());
    const bounds = map.getBounds(), dx = (bounds.getEast() - bounds.getWest()) * .35, dy = (bounds.getNorth() - bounds.getSouth()) * .35;
    const view: GeometryBounds = [bounds.getWest() - dx, bounds.getSouth() - dy, bounds.getEast() + dx, bounds.getNorth() + dy];
    const used = new Set<string>(), occupied = new Set<string>();
    if (appearance.places) {
      const size = map.getSize();
      const candidates = tiles.flatMap(tile => cache.get(tile.join('/'))?.placeLabels || []);
      for (const label of layoutPlaceLabels(candidates, Math.floor(map.getZoom()), size.x, size.y,
        point => map.latLngToContainerPoint([point[1], point[0]]))) {
        used.add(label.name);
        occupied.add(`${Math.floor(label.x / 115)}/${Math.floor(label.y / 35)}`);
        retain(`label/place/${label.kind}/${label.name}/${label.point.join('/')}`, label.name, `${label.width}/${label.kind}`, labels, () => {
          const element = document.createElement('span'); element.textContent = label.name;
          return L.marker([label.point[1], label.point[0]], { pane: 'appPlaceLabels', interactive: false,
            icon: L.divIcon({ className: `app-place-label app-place-${label.kind}`, html: element,
              iconSize: [label.width, 24], iconAnchor: [label.width / 2, label.kind === 'city' ? 32 : 12] }) });
        }, wanted);
        yield;
      }
    }
    for (const tile of tiles) {
      const tileKey = tile.join('/');
      const cached = cache.get(tileKey);
      if (appearance.surfaces) for (const [index, surface] of (cached?.surfaces || []).entries()) {
        yield;
        if (!geometryInView(surface.rings, view, surface.bounds)) continue;
        const zoom = Math.floor(map.getZoom());
        if (zoom < surface.minZoom || zoom > surface.maxZoom) continue;
        const paint = surface.paints[appearance.theme]?.find((p: any) => zoom >= p.minZoom && zoom <= p.maxZoom);
        if (!paint) continue;
        const style = { fillColor: paint.color, fillOpacity: paint.opacity };
        retain(`${tileKey}/surface/${index}`, surface, `${paint.color}/${paint.opacity}`, surfaces, () => L.polygon(surface.rings.map((ring: number[][]) => ring.map(p => [p[1], p[0]])), {
          pane: 'appSurfaces', renderer: surfaceRenderer, interactive: false,
          stroke: false, ...style, fillRule: 'evenodd', smoothFactor: .3,
        }), wanted, layer => (layer as L.Polygon).setStyle(style));
        yield;
      }
      if (appearance.transit) for (const label of cached?.transit || []) {
        const zoom = Math.floor(map.getZoom());
        if (zoom < label.minZoom || zoom > label.maxZoom) continue;
        const ll = L.latLng(label.point[1], label.point[0]);
        const pixel = map.latLngToContainerPoint(ll);
        const cell = `${Math.floor(pixel.x / 100)}/${Math.floor(pixel.y / 28)}`;
        const key = `${label.name}/${label.point.join('/')}`;
        if (!map.getBounds().contains(ll) || used.has(key) || occupied.has(cell) || occupied.size >= 90) continue;
        used.add(key); occupied.add(cell);
        retain(`label/transit/${key}`, label.name, 'transit', labels, () => {
          const element = document.createElement('span'); element.textContent = label.name;
          return L.marker(ll, { pane: 'appRoadLabels', interactive: false,
            icon: L.divIcon({ className: 'app-transit-label', html: element, iconSize: [100, 20], iconAnchor: [50, 10] }) });
        }, wanted);
        yield;
      }
      if (!cached?.collection) continue;
      const zoom = Math.floor(map.getZoom());
      const features: {feature: any; index: number}[] = [];
      for (const [index, feature] of cached.collection.features.entries()) {
        // Include rejected/off-screen features in the time budget. A flatMap
        // over a dense tile otherwise occupied an uninterruptible first frame.
        yield;
        const style = feature.properties.style;
        if (zoom >= (style & 31) && zoom <= ((style >> 5) & 31) &&
          geometryInView(feature.geometry.coordinates, view, feature.bbox)) features.push({feature, index});
      }
      // Keep the source index: filtered indexes shift when roads enter or leave
      // a zoom level and otherwise cause unchanged geometries to be replaced.
      if (appearance.roads) for (const { index, feature } of features)
        roadFeatures.push({ tileKey, index, feature,
          paint: appRoadPaint(cached.roadPaints, appearance.theme, feature.properties.paintKey, zoom) });
      if (!appearance.labels) continue;
      for (const { feature } of features) {
        const name = feature.properties.name as string;
        const points = feature.geometry.coordinates as number[][];
        if (!name || used.has(name) || !points.length) continue;
        const point = points[Math.floor(points.length / 2)];
        const ll = L.latLng(point[1], point[0]);
        if (!map.getBounds().contains(ll)) continue;
        const pixel = map.latLngToContainerPoint(ll);
        const cell = `${Math.floor(pixel.x / 115)}/${Math.floor(pixel.y / 35)}`;
        if (occupied.has(cell) || occupied.size >= 70) continue;
        occupied.add(cell); used.add(name);
        retain(`label/road/${name}/${point.join('/')}`, name, 'road', labels, () => {
          const element = document.createElement('span'); element.textContent = name;
          return L.marker(ll, { pane: 'appRoadLabels', interactive: false,
            icon: L.divIcon({ className: 'app-road-label', html: element, iconSize: [120, 18], iconAnchor: [60, 9] }) });
        }, wanted);
        yield;
      }
    }
    // Separate canvas panes keep every casing below every fill, including
    // newly visible roads. Existing geometry can then be restyled in place.
    for (const layer of ['outer', 'inner'] as const) for (const road of roadFeatures) {
      if (!road.paint && layer === 'inner') continue;
      const stroke = road.paint?.[layer];
      const weight = road.paint ? Math.max(.5, road.paint[layer === 'outer' ? 'outerWidth' : 'innerWidth'] * .1) : 3;
      const style = { color: stroke?.color || (appearance.theme === 'night' ? '#6f9399' : '#ffffff'),
        weight, opacity: stroke?.opacity ?? .9 };
      retain(`${road.tileKey}/road/${road.index}/${layer}`, road.feature,
        `${style.color}/${weight}/${style.opacity}`, roads,
        () => L.geoJSON(road.feature, { pane: layer === 'outer' ? 'appRoads' : 'appRoadFills', interactive: false,
          style: { renderer: layer === 'outer' ? renderer : fillRenderer, ...style,
            lineCap: 'round', lineJoin: 'round' } }), wanted,
        entry => (entry as L.GeoJSON).setStyle(style));
      yield;
    }
    // Keep the current map as a backdrop until new viewport tiles arrive.
    // Reconcile only after the pass completes so interrupted drawing never clears it.
    const complete = tiles.every(tile => cache.has(tile.join('/')));
    for (const [key, entry] of rendered) {
      if (wanted.has(key)) continue;
      if (!complete && !key.startsWith('label/')) continue;
      entry.group.removeLayer(entry.layer); rendered.delete(key); yield;
    }
  }
  let loading = false;
  const failures = new Map<string, { count: number; retryAt: number }>();
  let serviceFailureCount = 0, serviceRetryAt = 0;
  function needsTile(tile: number[]) {
    const key = tile.join('/'), cached = cache.get(key), failure = failures.get(key);
    return (!cached || Date.now() - cached.time > browserMapTileTtlMs())
      && (!failure || (failure.count < 3 && Date.now() >= failure.retryAt));
  }
  function markFailed(tile: number[]) {
    const key = tile.join('/'), count = (failures.get(key)?.count || 0) + 1;
    failures.set(key, { count, retryAt: Date.now() + 2000 * 2 ** (count - 1) });
    if (failures.size > 256) failures.delete(failures.keys().next().value!);
  }
  async function hydrateTiles(tiles: number[][]) {
    const rememberRows = (rows: ReturnType<typeof readMemoryMapTiles>) => {
      for(const [key,row] of rows) cache.set(key,{
        time:row.at,collection:row.tile.collection,surfaces:row.tile.surfaces as any[],
        transit:row.tile.transit as any[],placeLabels:row.tile.placeLabels as PlaceLabel[],
        roadPaints:row.tile.roadPaints as RoadPaints,missingLayers:row.tile.missingLayers,
      });
    };
    rememberRows(readMemoryMapTiles('full', tiles));
    draw(visible(), true);
    const full=await readMapTiles('full',tiles);
    const saved=await readMapTiles('rendered',tiles.filter(tile=>!full.has(tile.join('/'))));
    for(const tile of tiles) hydrated.add(tile.join('/'));
    rememberRows(new Map([...full, ...saved]));
  }
  async function load() {
    if (disposed || !active || moving || zooming || loading || authRequired) return;
    const tiles = visible();
    const toHydrate=tiles.filter(tile=>!hydrated.has(tile.join('/')));
    if(toHydrate.length) {
      loading=true;
      const id=generation;
      try {
        await hydrateTiles(toHydrate);
        if(disposed || id!==generation || !active) return;
        draw(visible(),true);
      } finally {loading=false;}
      if(!disposed && active) return load();
      return;
    }
    draw(tiles);
    if (!tiles.length) { report('路线总览 · 放大后显示道路详情'); return; }
    if (serviceRetryAt > Date.now()) {
      queueLoad(Math.max(100, serviceRetryAt - Date.now()));
      report('地图服务暂时不可用，稍后自动重试');
      return;
    }
    // Navigation needs the roads beside the car first. A slow overview tile
    // must not hold up street detail. Drawing still uses source order.
    const center = map.getCenter();
    const missing = tiles.filter(needsTile).sort((a, b) =>
      b[0] - a[0] || mapTileDistance(a, center.lng, center.lat) - mapTileDistance(b, center.lng, center.lat));
    if (!missing.length && tiles.some(tile => failures.has(tile.join('/')))) {
      const retryTimes = tiles.map(tile => failures.get(tile.join('/')))
        .filter((failure): failure is { count: number; retryAt: number } => !!failure && failure.count < 3 && failure.retryAt > Date.now())
        .map(failure => failure.retryAt);
      if (retryTimes.length) queueLoad(Math.max(100, Math.min(...retryTimes) - Date.now()));
      report('部分图层加载失败，可重试补齐');
      return;
    }
    if (!missing.length && routeTiles.length) {
      const visibleKeys = new Set(tiles.map(tile => tile.join('/')));
      const ahead = routeTiles.filter(tile => {
        const key = tile.join('/');
        return !visibleKeys.has(key) && !cache.has(key) && !routeAttempted.has(key);
      });
      if (ahead.length) { void warmRoute(ahead.slice(0, 2)); return; }
    }
    const prefetch = missing.length === 0;
    const candidates = prefetch ? surroundingTiles(tiles).filter(needsTile) : missing;
    const coldNeighbours=prefetch?candidates.filter(tile=>!hydrated.has(tile.join('/'))).slice(0,8):[];
    if(coldNeighbours.length) {
      loading=true;
      const id=generation;
      try {await hydrateTiles(coldNeighbours);}
      finally {loading=false;}
      if(!disposed && id===generation && active) return load();
      return;
    }
    if (!candidates.length) {
      const retryTimes = [...failures.values()].filter(f => f.count < 3 && f.retryAt > Date.now()).map(f => f.retryAt);
      if (retryTimes.length) queueLoad(Math.max(100, Math.min(...retryTimes) - Date.now()));
      report(tiles.some(t => failures.has(t.join('/'))) ? '部分图层加载失败，可重试补齐' : '');
      return;
    }
    loading = true;
    const id = generation;
    const controller = new AbortController(); request = controller; requestIsPrefetch = prefetch;
    // Small warm-up batches keep viewport requests responsive. Each completed
    // batch re-evaluates the current view before doing any more background work.
    const level = candidates[0][0];
    const batch = candidates.filter(t => t[0] === level).slice(0, prefetch ? 1 : 4);
    if (!prefetch) report('正在加载 App 地图…');
    try {
      const deadline = Date.now() + 90000;
      const fetchReady = async (path: string) => {
        while (true) {
          const response = await postMapTiles(path, { level, tiles: batch.map(t => t.slice(1)) },
            { signal: controller.signal, timeout: 70000 });
          if (response.data?.status === 'need_login') {
            authRequired = true;
            report('TMC 登录已失效，请登录后重试地图');
            throw new Error('map login required');
          }
          if (response.status !== 202 || !response.data.data?.pending) return response;
          if (Date.now() >= deadline) throw new Error('地图加载超时');
          await new Promise(resolve => setTimeout(resolve, 750));
          if (disposed || id !== generation) throw new Error('地图请求已取消');
        }
      };
      let response;
      try {
        response = await fetchReady(rawUnavailable ? '/api/amap-app/map' : '/api/amap-app/map/bmd');
      } catch (error) {
        if (rawUnavailable || authRequired || controller.signal.aborted || disposed || id !== generation ||
            !rawBmdUnsupported(error)) throw error;
        rawUnavailable = true;
        response = await fetchReady('/api/amap-app/map');
      }
      if (disposed || id !== generation) return;
      if (response.data.status !== 'ok') throw new Error('地图请求失败');
      serviceFailureCount = 0; serviceRetryAt = 0;
      let receivedTiles = response.data.data.tiles;
      if (!rawUnavailable) {
        try {
          receivedTiles = await decodeRaw(receivedTiles, response.data.data.paints || {});
          transientDecodeFailures = 0;
        } catch (error) {
          if (!rawBmdDecodeUnsupported(error) && ++transientDecodeFailures < 2) throw error;
          rawUnavailable = true;
          response = await fetchReady('/api/amap-app/map');
          if (response.data.status !== 'ok') throw new Error('地图回退请求失败');
          receivedTiles = response.data.data.tiles;
        }
      }
      if (disposed || id !== generation) return;
      await waitForMapIdle();
      if (disposed || id !== generation) return;
      const returned = new Set<string>();
      for (const tile of receivedTiles) {
        const key = `${tile.level}/${tile.x}/${tile.y}`;
        if (!batch.some(t => t.join('/') === key)) continue;
        returned.add(key);
        if (tile.error) { markFailed([tile.level, tile.x, tile.y]); continue; }
        cache.delete(key); cache.set(key, { time: tile.missingLayers?.length ? 0 : Date.now(), collection: tile.collection, surfaces: tile.surfaces, transit: tile.transit, placeLabels: tile.placeLabels,
          roadPaints: tile.roadPaints, missingLayers: tile.missingLayers });
        if (tile.missingLayers?.length) markFailed([tile.level, tile.x, tile.y]); else failures.delete(key);
      }
      // Decoded BMD tiles contain the same road, surface, label and paint data
      // that the 3D ground uses. Share them across 2D/3D so switching views
      // does not download the same App tile again. Older rendered rows remain
      // readable through hydrateTiles for existing browser caches.
      void storeMapTiles('full',receivedTiles);
      for (const tile of batch) if (!returned.has(tile.join('/'))) markFailed(tile);
      const protectedKeys = new Set(visible().map(t => t.join('/')));
      for (const key of cache.keys()) {
        if (cache.size <= 128) break;
        if (!protectedKeys.has(key)) cache.delete(key);
      }
      draw(visible(), true);
    } catch (error) {
      if (!disposed && id === generation && !authRequired && !controller.signal.aborted) {
        const status = (error as { response?: { status?: number } } | null)?.response?.status;
        if (typeof status === 'number' && status >= 500) {
          serviceFailureCount = Math.min(serviceFailureCount + 1, 4);
          serviceRetryAt = Date.now() + Math.min(60000, 5000 * 2 ** serviceFailureCount);
          report('地图服务暂时不可用，稍后自动重试');
        } else batch.forEach(markFailed);
      }
    } finally {
      loading = false;
      if (request === controller) { request = undefined; requestIsPrefetch = false; }
      if (!disposed && active && !authRequired) {
        queueLoad(100);
      }
    }
  }

  async function warmRoute(batch: number[][]) {
    loading = true;
    const id = generation, routeId = routeGeneration;
    const controller = new AbortController(); request = controller; requestIsPrefetch = true;
    let delay = 750;
    try {
      const response = await axios.post(rawUnavailable ? '/api/amap-app/map/prefetch' : '/api/amap-app/map/bmd/prefetch',
        { level: 14, tiles: batch.map(tile => tile.slice(1)) },
        { signal: controller.signal, timeout: 12000 });
      if (disposed || id !== generation || routeId !== routeGeneration) return;
      if (response.data?.status === 'need_login') {
        authRequired = true;
        report('TMC 登录已失效，请登录后重试地图');
        return;
      }
      if (response.status === 202) { delay = 2000; return; }
      // A failed tile is attempted only once per route window. Visible loads
      // retain their own retry policy if the vehicle reaches that tile.
      batch.forEach(tile => routeAttempted.add(tile.join('/')));
    } catch {
      if (!disposed && id === generation && routeId === routeGeneration)
        batch.forEach(tile => routeAttempted.add(tile.join('/')));
    } finally {
      loading = false;
      if (request === controller) { request = undefined; requestIsPrefetch = false; }
      if (!disposed && active && !authRequired) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => void load(), delay);
      }
    }
  }

  function pauseDrawing() {
    moving = true;
    drawnView = '';
    // Movement only pauses drawing, never throws away an in-flight download.
    renderQueue.cancel();
    if (timer) clearTimeout(timer);
    timer = undefined;
  }
  function suspend() {
    // The hidden Leaflet map still follows the 3D centre. It must never
    // acquire a gate whose moveend handler is disabled along with 2D drawing.
    if (!active || disposed) return;
    if (requestIsPrefetch && !following) request?.abort();
    if (!following) { interaction.set(true); pauseDrawing(); }
  }
  function suspendZoom() {
    if (!active || disposed) return;
    zooming = true;
    interaction.set(true);
    if (requestIsPrefetch) request?.abort();
    pauseDrawing();
  }
  function resumeZoom() {
    zooming = false;
    schedule();
  }
  function schedule() {
    if (!active || disposed || zooming || inputActive) return;
    moving = false;
    interaction.set(false);
    if (requestIsPrefetch && visible().some(needsTile)) request?.abort();
    // Following issues a succession of tiny pans. Keep the pending draw/load
    // instead of restarting its 100 ms timer on every Leaflet moveend.
    if (following) {
      if (!timer) queueLoad(150);
      return;
    }
    renderQueue.cancel();
    queueLoad(100);
  }
  map.on('movestart', suspend);
  map.on('zoomstart', suspendZoom);
  map.on('moveend rotate', schedule);
  map.on('zoomend', resumeZoom);
  void load();
  return { setFollowing(value: boolean) { following = value; if (value) { moving = false; schedule(); } },
    setActive(value: boolean) {
      active = value;
      if (!value) {
        generation++; request?.abort();
        if (inputTimer) clearTimeout(inputTimer);
        inputTimer = undefined; inputPointers.clear(); inputActive = false; zooming = false;
        interaction.set(false); pauseDrawing();
      } else { moving = false; zooming = false; schedule(); }
    },
    setAppearance(value: AppMapAppearance) { appearance = value; draw(visible(), true); },
    setRoute(nextRoute?: AppRoute, progress = 0) {
      const bucket = Math.floor(Math.max(0, Number.isFinite(progress) ? progress : 0) / 2000);
      if (route === nextRoute && routeBucket === bucket) return;
      if (route !== nextRoute) routeAttempted.clear();
      route = nextRoute; routeBucket = bucket; routeGeneration++;
      routeTiles = nextRoute ? routeCorridorTiles(nextRoute, progress) : [];
      if (active) schedule();
    },
    retry: () => { authRequired = false; failures.clear(); serviceFailureCount = 0; serviceRetryAt = 0; drawnView = ''; void load(); },
    releaseMemory() {
      renderQueue.cancel();
      cache.clear(); hydrated.clear(); rendered.clear();
      surfaces.clearLayers(); roads.clearLayers(); labels.clearLayers();
      drawnView = '';
    },
    dispose() {
    interaction.dispose();
    if (inputTimer) clearTimeout(inputTimer);
    container?.removeEventListener('pointerdown', rawInput, true);
    container?.removeEventListener('wheel', rawInput, true);
    container?.removeEventListener('touchstart', rawInput, true);
    window.removeEventListener('pointerup', endPointer); window.removeEventListener('pointercancel', endPointer);
    window.removeEventListener('touchend', endTouch); window.removeEventListener('touchcancel', endTouch);
    disposed = true; generation++; request?.abort(); renderQueue.cancel(); if (timer) clearTimeout(timer);
    map.off('movestart', suspend); map.off('zoomstart', suspendZoom); map.off('moveend rotate', schedule); map.off('zoomend', resumeZoom);
    roads.remove(); labels.remove(); renderer.remove(); fillRenderer.remove(); surfaces.remove(); surfaceRenderer.remove(); cache.clear(); rendered.clear();
  } };
}
