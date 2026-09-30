import L from 'leaflet';
import axios from 'axios';
import { createMapRenderQueue } from './mapRenderQueue';
import { routeCorridorTiles, surroundingTiles } from './amapTilePrefetch';
import type { AppRoute } from './amapNavigation';
import { viewportTiles } from './amapViewport';
import { layoutPlaceLabels, type PlaceLabel } from './amapPlaceLabels';

export type AppMapAppearance = { theme: 'day' | 'night'; surfaces: boolean; roads: boolean; labels: boolean; transit: boolean; places: boolean };

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
  const cache = new Map<string, { time: number; collection?: any; surfaces?: any[]; transit?: any[]; placeLabels?: PlaceLabel[]; missingLayers?: string[] }>();
  let route: AppRoute | undefined, routeBucket = -1, routeGeneration = 0, routeTiles: number[][] = [];
  const routeAttempted = new Set<string>();
  let request: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false, generation = 0;
  let bmdWorker: Worker | undefined;
  let rawUnavailable = false;
  function decodeRaw(tiles: any[], paints: any): Promise<any[]> {
    if (typeof Worker === 'undefined') return Promise.reject(new Error('Worker unavailable'));
    bmdWorker ||= new Worker(new URL('./amapBmdWorker.ts', import.meta.url), { type: 'module' });
    return new Promise((resolve, reject) => {
      const worker = bmdWorker!;
      const timeout = setTimeout(() => { worker.terminate(); bmdWorker = undefined; reject(new Error('BMD decode timeout')); }, 15000);
      worker.onmessage = event => {
        clearTimeout(timeout);
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data.tiles);
      };
      worker.onerror = () => {
        clearTimeout(timeout); worker.terminate(); bmdWorker = undefined;
        reject(new Error('BMD worker failed'));
      };
      worker.postMessage({ tiles, paints });
    });
  }
  function visible() {
    const b = map.getBounds();
    return viewportTiles(map.getZoom(), b.getWest(), b.getNorth(), b.getEast(), b.getSouth());
  }

  const renderQueue = createMapRenderQueue(() => report('地图绘制失败，请重试'));
  let moving = false, active = true;
  function draw(tiles: number[][]) {
    if (!disposed && !moving && active) renderQueue.start(drawSteps(tiles));
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
      if (appearance.roads) for (const [index, feature] of collection.features.entries()) {
        retain(`${tileKey}/road/${index}`, feature, `${zoom}/${appearance.theme}`, roads, () => L.geoJSON(feature, { pane: 'appRoads', interactive: false,
          style: { renderer, color: appearance.theme === 'night' ? '#6f9399' : '#ffffff', weight: 3, opacity: .9 } }), wanted);
        yield;
      }
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
  function needsTile(tile: number[]) {
    const key = tile.join('/'), cached = cache.get(key), failure = failures.get(key);
    return (!cached || Date.now() - cached.time > 600000)
      && (!failure || (failure.count < 3 && Date.now() >= failure.retryAt));
  }
  function markFailed(tile: number[]) {
    const key = tile.join('/'), count = (failures.get(key)?.count || 0) + 1;
    failures.set(key, { count, retryAt: Date.now() + 2000 * 2 ** (count - 1) });
    if (failures.size > 256) failures.delete(failures.keys().next().value!);
  }
  async function load() {
    if (disposed || !active || loading) return;
    const tiles = visible();
    draw(tiles);
    if (!tiles.length) { report('路线总览 · 放大后显示道路详情'); return; }
    // Show the broad overview first, then the current street detail before
    // filling in intermediate source levels. Drawing still uses source order.
    const missing = tiles.filter(needsTile).sort((a, b) =>
      a[0] === b[0] ? 0 : a[0] === 3 ? -1 : b[0] === 3 ? 1 : b[0] - a[0]);
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
    if (!candidates.length) {
      const retryTimes = [...failures.values()].filter(f => f.count < 3 && f.retryAt > Date.now()).map(f => f.retryAt);
      if (retryTimes.length) timer = setTimeout(() => void load(), Math.max(100, Math.min(...retryTimes) - Date.now()));
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
          const response = await axios.post(path, { level, tiles: batch.map(t => t.slice(1)) },
            { signal: controller.signal, timeout: 70000 });
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
        if (rawUnavailable || controller.signal.aborted || disposed || id !== generation) throw error;
        rawUnavailable = true;
        response = await fetchReady('/api/amap-app/map');
      }
      if (disposed || id !== generation) return;
      if (response.data.status !== 'ok') throw new Error('地图请求失败');
      let receivedTiles = response.data.data.tiles;
      if (!rawUnavailable) {
        try {
          receivedTiles = await decodeRaw(receivedTiles, response.data.data.paints || {});
        } catch {
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
        cache.delete(key); cache.set(key, { time: tile.missingLayers?.length ? 0 : Date.now(), collection: tile.collection, surfaces: tile.surfaces, transit: tile.transit, placeLabels: tile.placeLabels, missingLayers: tile.missingLayers });
        if (tile.missingLayers?.length) markFailed([tile.level, tile.x, tile.y]); else failures.delete(key);
      }
      for (const tile of batch) if (!returned.has(tile.join('/'))) markFailed(tile);
      const protectedKeys = new Set(visible().map(t => t.join('/')));
      for (const key of cache.keys()) {
        if (cache.size <= 128) break;
        if (!protectedKeys.has(key)) cache.delete(key);
      }
      draw(visible());
    } catch {
      if (!disposed && id === generation) batch.forEach(markFailed);
    } finally {
      loading = false;
      if (request === controller) request = undefined;
      if (!disposed && active) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => void load(), 100);
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
      if (response.status === 202 && response.data.data?.pending) { delay = 2000; return; }
      // A failed tile is attempted only once per route window. Visible loads
      // retain their own retry policy if the vehicle reaches that tile.
      batch.forEach(tile => routeAttempted.add(tile.join('/')));
    } catch {
      if (!disposed && id === generation && routeId === routeGeneration)
        batch.forEach(tile => routeAttempted.add(tile.join('/')));
    } finally {
      loading = false;
      if (request === controller) request = undefined;
      if (!disposed && active) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => void load(), delay);
      }
    }
  }

  function suspend() {
    moving = true;
    // Movement only pauses drawing, never throws away an in-flight download.
    renderQueue.cancel();
    if (timer) clearTimeout(timer);
  }
  function schedule() {
    if (!active || disposed) return;
    moving = false;
    renderQueue.cancel();
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void load(), 100);
  }
  map.on('movestart zoomstart', suspend);
  map.on('moveend zoomend rotate', schedule);
  void load();
  return { setActive(value: boolean) { active = value; if (!value) { generation++; request?.abort(); suspend(); } else { moving = false; schedule(); } }, setAppearance(value: AppMapAppearance) { appearance = value; draw(visible()); },
    setRoute(nextRoute?: AppRoute, progress = 0) {
      const bucket = Math.floor(Math.max(0, Number.isFinite(progress) ? progress : 0) / 2000);
      if (route === nextRoute && routeBucket === bucket) return;
      if (route !== nextRoute) routeAttempted.clear();
      route = nextRoute; routeBucket = bucket; routeGeneration++;
      routeTiles = nextRoute ? routeCorridorTiles(nextRoute, progress) : [];
      if (active) schedule();
    },
    retry: () => { failures.clear(); void load(); }, dispose() {
    disposed = true; generation++; request?.abort(); renderQueue.cancel(); if (timer) clearTimeout(timer);
    bmdWorker?.terminate(); bmdWorker = undefined;
    map.off('movestart zoomstart', suspend); map.off('moveend zoomend rotate', schedule); roads.remove(); labels.remove(); renderer.remove(); surfaces.remove(); surfaceRenderer.remove(); cache.clear(); rendered.clear();
  } };
}
