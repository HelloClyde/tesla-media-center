import L from 'leaflet';
import axios from 'axios';
import { decodeBmdOnMainThread, postMapTiles, rawBmdDecodeUnsupported, rawBmdUnsupported, TransientBmdDecodeError, transferableBmdBuffers } from './amapBmdTransport';
import { createMapRenderQueue } from './mapRenderQueue';
import { routeCorridorTiles, surroundingTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';
import { viewportTiles } from './amapViewport';
import { layoutPlaceLabels, type PlaceLabel } from './amapPlaceLabels';
import { browserMapTileTtlMs, readMapTiles, storeMapTiles } from './amapBrowserTileCache';

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
  map.createPane('appRoadLabels', upright).style.zIndex = '220';
  map.createPane('appPlaceLabels', upright).style.zIndex = '450';
  const renderer = L.canvas({ pane: 'appRoads', padding: .2 });
  const roads = L.layerGroup().addTo(map), labels = L.layerGroup().addTo(map);
  const cache = new Map<string, { time: number; collection?: any; surfaces?: any[]; transit?: any[]; placeLabels?: PlaceLabel[];
    roadPaints?: RoadPaints; missingLayers?: string[] }>();
  const hydrated = new Set<string>();
  let route: AppRoute | undefined, routeBucket = -1, routeGeneration = 0, routeTiles: number[][] = [];
  const routeAttempted = new Set<string>();
  let request: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined;
  function queueLoad(delay: number) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = undefined; void load(); }, delay);
  }
  let disposed = false, generation = 0;
  let bmdWorker: Worker | undefined, bmdWorkerReady = false, workerUnavailable = false;
  let rawUnavailable = false, authRequired = false, transientDecodeFailures = 0;
  function decodeRaw(tiles: any[], paints: any): Promise<any[]> {
    if (workerUnavailable || typeof Worker === 'undefined')
      return Promise.resolve().then(() => decodeBmdOnMainThread(tiles, paints));
    try { bmdWorker ||= new Worker(new URL('./amapBmdWorker.ts', import.meta.url), { type: 'module' }); }
    catch {
      workerUnavailable = true;
      return Promise.resolve().then(() => decodeBmdOnMainThread(tiles, paints));
    }
    return new Promise((resolve, reject) => {
      const worker = bmdWorker!;
      let sent = false;
      const local = () => {
        workerUnavailable = true;
        Promise.resolve().then(() => decodeBmdOnMainThread(tiles, paints)).then(resolve, reject);
      };
      const stop = () => { worker.terminate(); bmdWorker = undefined; bmdWorkerReady = false; };
      const send = () => {
        try { worker.postMessage({ tiles, paints }, transferableBmdBuffers(tiles)); sent = true; }
        catch { clearTimeout(timeout); stop(); local(); }
      };
      const timeout = setTimeout(() => {
        stop();
        if (sent) reject(new TransientBmdDecodeError('BMD decode timeout'));
        else local();
      }, 15000);
      worker.onmessage = event => {
        if (event.data.ready) { bmdWorkerReady = true; send(); return; }
        clearTimeout(timeout);
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data.tiles);
      };
      worker.onerror = () => {
        clearTimeout(timeout); stop();
        if (sent) reject(new TransientBmdDecodeError('BMD worker failed'));
        else local();
      };
      if (bmdWorkerReady) send();
    });
  }
  function visible() {
    const b = map.getBounds();
    return viewportTiles(map.getZoom(), b.getWest(), b.getNorth(), b.getEast(), b.getSouth());
  }

  const renderQueue = createMapRenderQueue(() => report('地图绘制失败，请重试'));
  let moving = false, active = true, following = false;
  let drawnView = '';
  function draw(tiles: number[][], force = false) {
    if (disposed || moving || !active) return;
    const view = `${Math.floor(map.getZoom())}:${tiles.map(tile => tile.join('/')).join('|')}`;
    if (!force && view === drawnView) return;
    drawnView = view;
    renderQueue.start(drawSteps(tiles));
  }
  const rendered = new Map<string, { data: unknown; style: string; layer: L.Layer; group: L.LayerGroup }>();
  function retain(key: string, data: unknown, style: string, group: L.LayerGroup, create: () => L.Layer, wanted: Set<string>) {
    wanted.add(key);
    const old = rendered.get(key);
    if (old && old.data === data && old.style === style) return;
    const layer = create().addTo(group);
    if (old) old.group.removeLayer(old.layer);
    rendered.set(key, { data, style, layer, group });
  }
  function* drawSteps(tiles: number[][]): Generator<void> {
    const wanted = new Set<string>();
    const roadFeatures: { tileKey: string; index: number; feature: any; paint?: RoadPaint }[] = [];
    const zoom = Math.floor(map.getZoom());
    const used = new Set<string>(), occupied = new Set<string>();
    if (appearance.places) {
      const size = map.getSize();
      const candidates = tiles.flatMap(tile => cache.get(tile.join('/'))?.placeLabels || []);
      for (const label of layoutPlaceLabels(candidates, Math.floor(map.getZoom()), size.x, size.y,
        point => map.latLngToContainerPoint([point[1], point[0]]))) {
        const element = document.createElement('span'); element.textContent = label.name;
        used.add(label.name);
        occupied.add(`${Math.floor(label.x / 115)}/${Math.floor(label.y / 35)}`);
        retain(`label/place/${label.kind}/${label.name}/${label.point.join('/')}`, label.name, `${label.width}/${label.kind}`, labels, () => L.marker([label.point[1], label.point[0]], { pane: 'appPlaceLabels', interactive: false,
          icon: L.divIcon({ className: `app-place-label app-place-${label.kind}`, html: element,
            iconSize: [label.width, 24], iconAnchor: [label.width / 2, label.kind === 'city' ? 32 : 12] }) }), wanted);
        yield;
      }
    }
    for (const tile of tiles) {
      const tileKey = tile.join('/');
      const cached = cache.get(tileKey);
      if (appearance.surfaces) for (const [index, surface] of (cached?.surfaces || []).entries()) {
        const zoom = Math.floor(map.getZoom());
        if (zoom < surface.minZoom || zoom > surface.maxZoom) continue;
        const paint = surface.paints[appearance.theme]?.find((p: any) => zoom >= p.minZoom && zoom <= p.maxZoom);
        if (!paint) continue;
        retain(`${tileKey}/surface/${index}`, surface, `${zoom}/${appearance.theme}`, surfaces, () => L.polygon(surface.rings.map((ring: number[][]) => ring.map(p => [p[1], p[0]])), {
          pane: 'appSurfaces', renderer: surfaceRenderer, interactive: false,
          stroke: false, fillColor: paint.color, fillOpacity: paint.opacity, fillRule: 'evenodd', smoothFactor: .3,
        }), wanted);
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
        const element = document.createElement('span'); element.textContent = label.name;
        retain(`label/transit/${key}`, label.name, 'transit', labels, () => L.marker(ll, { pane: 'appRoadLabels', interactive: false,
          icon: L.divIcon({ className: 'app-transit-label', html: element, iconSize: [100, 20], iconAnchor: [50, 10] }) }), wanted);
        yield;
      }
      if (!cached?.collection) continue;
      const zoom = Math.floor(map.getZoom());
      const collection = { ...cached.collection, features: cached.collection.features.filter((feature: any) => {
        const style = feature.properties.style;
        return zoom >= (style & 31) && zoom <= ((style >> 5) & 31);
      }) };
      if (appearance.roads) for (const [index, feature] of collection.features.entries())
        roadFeatures.push({ tileKey, index, feature,
          paint: appRoadPaint(cached.roadPaints, appearance.theme, feature.properties.paintKey, zoom) });
      if (!appearance.labels) continue;
      for (const feature of collection.features) {
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
        const element = document.createElement('span'); element.textContent = name;
        retain(`label/road/${name}/${point.join('/')}`, name, 'road', labels, () => L.marker(ll, { pane: 'appRoadLabels', interactive: false,
          icon: L.divIcon({ className: 'app-road-label', html: element, iconSize: [120, 18], iconAnchor: [60, 9] }) }), wanted);
        yield;
      }
    }
    // All casings precede all fills, preserving the App's two-stroke road
    // hierarchy at intersections rather than painting every road white.
    for (const layer of ['outer', 'inner'] as const) for (const road of roadFeatures) {
      if (!road.paint && layer === 'inner') continue;
      const stroke = road.paint?.[layer];
      const weight = road.paint ? Math.max(.5, road.paint[layer === 'outer' ? 'outerWidth' : 'innerWidth'] * .1) : 3;
      retain(`${road.tileKey}/road/${road.index}/${layer}`, road.feature,
        `${zoom}/${appearance.theme}/${stroke?.color}/${weight}`, roads,
        () => L.geoJSON(road.feature, { pane: 'appRoads', interactive: false,
          style: { renderer, color: stroke?.color || (appearance.theme === 'night' ? '#6f9399' : '#ffffff'),
            weight, opacity: stroke?.opacity ?? .9, lineCap: 'round', lineJoin: 'round' } }), wanted);
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
    const full=await readMapTiles('full',tiles);
    const saved=await readMapTiles('rendered',tiles.filter(tile=>!full.has(tile.join('/'))));
    for(const tile of tiles) hydrated.add(tile.join('/'));
    for(const [key,row] of [...full,...saved]) cache.set(key,{
      time:row.at,collection:row.tile.collection,surfaces:row.tile.surfaces as any[],
      transit:row.tile.transit as any[],placeLabels:row.tile.placeLabels as PlaceLabel[],
      roadPaints:row.tile.roadPaints as RoadPaints,missingLayers:row.tile.missingLayers,
    });
  }
  async function load() {
    if (disposed || !active || loading || authRequired) return;
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
    // Show the broad overview first, then the current street detail before
    // filling in intermediate source levels. Drawing still uses source order.
    const missing = tiles.filter(needsTile).sort((a, b) =>
      a[0] === b[0] ? 0 : a[0] === 3 ? -1 : b[0] === 3 ? 1 : b[0] - a[0]);
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
    const controller = new AbortController(); request = controller;
    // Small warm-up batches keep viewport requests responsive. Each completed
    // batch re-evaluates the current view before doing any more background work.
    const level = candidates[0][0];
    const batch = candidates.filter(t => t[0] === level).slice(0, prefetch ? 4 : 24);
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
      if (!disposed && id === generation && !authRequired) {
        const status = (error as { response?: { status?: number } } | null)?.response?.status;
        if (typeof status === 'number' && status >= 500) {
          serviceFailureCount = Math.min(serviceFailureCount + 1, 4);
          serviceRetryAt = Date.now() + Math.min(60000, 5000 * 2 ** serviceFailureCount);
          report('地图服务暂时不可用，稍后自动重试');
        } else batch.forEach(markFailed);
      }
    } finally {
      loading = false;
      if (request === controller) request = undefined;
      if (!disposed && active && !authRequired) {
        queueLoad(100);
      }
    }
  }

  async function warmRoute(batch: number[][]) {
    loading = true;
    const id = generation, routeId = routeGeneration;
    const controller = new AbortController(); request = controller;
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
      if (request === controller) request = undefined;
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
    if (!following) pauseDrawing();
  }
  function schedule() {
    if (!active || disposed) return;
    moving = false;
    // Following issues a succession of tiny pans. Keep the pending draw/load
    // instead of restarting its 100 ms timer on every Leaflet moveend.
    if (following) {
      if (!timer) queueLoad(150);
      return;
    }
    renderQueue.cancel();
    queueLoad(100);
  }
  map.on('movestart zoomstart', suspend);
  map.on('moveend zoomend rotate', schedule);
  void load();
  return { setFollowing(value: boolean) { following = value; if (value) { moving = false; schedule(); } },
    setActive(value: boolean) { active = value; if (!value) { generation++; request?.abort(); pauseDrawing(); } else { moving = false; schedule(); } },
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
      cache.clear(); rendered.clear();
      surfaces.clearLayers(); roads.clearLayers(); labels.clearLayers();
      bmdWorker?.terminate(); bmdWorker = undefined;
      drawnView = '';
    },
    dispose() {
    disposed = true; generation++; request?.abort(); renderQueue.cancel(); if (timer) clearTimeout(timer);
    bmdWorker?.terminate(); bmdWorker = undefined;
    map.off('movestart zoomstart', suspend); map.off('moveend zoomend rotate', schedule); roads.remove(); labels.remove(); renderer.remove(); surfaces.remove(); surfaceRenderer.remove(); cache.clear(); rendered.clear();
  } };
}
