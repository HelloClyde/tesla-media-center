import L from 'leaflet';
import axios from 'axios';
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
  let request: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false, generation = 0;
  function visible() {
    const b = map.getBounds();
    return viewportTiles(map.getZoom(), b.getWest(), b.getNorth(), b.getEast(), b.getSouth());
  }

  function draw(tiles: number[][]) {
    roads.clearLayers(); labels.clearLayers(); surfaces.clearLayers();
    const used = new Set<string>(), occupied = new Set<string>();
    if (appearance.places) {
      const size = map.getSize();
      const candidates = tiles.flatMap(tile => cache.get(tile.join('/'))?.placeLabels || []);
      for (const label of layoutPlaceLabels(candidates, Math.floor(map.getZoom()), size.x, size.y,
        point => map.latLngToContainerPoint([point[1], point[0]]))) {
        const element = document.createElement('span'); element.textContent = label.name;
        used.add(label.name);
        occupied.add(`${Math.floor(label.x / 115)}/${Math.floor(label.y / 35)}`);
        L.marker([label.point[1], label.point[0]], { pane: 'appPlaceLabels', interactive: false,
          icon: L.divIcon({ className: `app-place-label app-place-${label.kind}`, html: element,
            iconSize: [label.width, 24], iconAnchor: [label.width / 2, label.kind === 'city' ? 32 : 12] }) }).addTo(labels);
      }
    }
    for (const tile of tiles) {
      const cached = cache.get(tile.join('/'));
      if (appearance.surfaces) for (const surface of cached?.surfaces || []) {
        const zoom = Math.floor(map.getZoom());
        if (zoom < surface.minZoom || zoom > surface.maxZoom) continue;
        const paint = surface.paints[appearance.theme]?.find((p: any) => zoom >= p.minZoom && zoom <= p.maxZoom);
        if (!paint) continue;
        L.polygon(surface.rings.map((ring: number[][]) => ring.map(p => [p[1], p[0]])), {
          pane: 'appSurfaces', renderer: surfaceRenderer, interactive: false,
          stroke: false, fillColor: paint.color, fillOpacity: paint.opacity, fillRule: 'evenodd', smoothFactor: .3,
        }).addTo(surfaces);
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
        L.marker(ll, { pane: 'appRoadLabels', interactive: false,
          icon: L.divIcon({ className: 'app-transit-label', html: element, iconSize: [100, 20], iconAnchor: [50, 10] }) }).addTo(labels);
      }
      if (!cached?.collection) continue;
      const zoom = Math.floor(map.getZoom());
      const collection = { ...cached.collection, features: cached.collection.features.filter((feature: any) => {
        const style = feature.properties.style;
        return zoom >= (style & 31) && zoom <= ((style >> 5) & 31);
      }) };
      if (appearance.roads) L.geoJSON(collection, { pane: 'appRoads', interactive: false,
        style: { renderer, color: appearance.theme === 'night' ? '#6f9399' : '#ffffff', weight: 3, opacity: .9 } }).addTo(roads);
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
        L.marker(ll, { pane: 'appRoadLabels', interactive: false,
          icon: L.divIcon({ className: 'app-road-label', html: element, iconSize: [120, 18], iconAnchor: [60, 9] }) }).addTo(labels);
      }
    }
  }
  async function load() {
    const id = ++generation;
    request?.abort(); request = new AbortController();
    const tiles = visible();
    if (!tiles.length) { roads.clearLayers(); labels.clearLayers(); surfaces.clearLayers(); report('路线总览 · 放大后显示道路详情'); return; }
    const missing = tiles.filter(t => !cache.has(t.join('/')) || Date.now() - cache.get(t.join('/'))!.time > 600000);
    draw(tiles);
    if (!missing.length) { report(''); return; }
    report('正在加载 App 地图…');
    let failed = false;
    for (const level of [...new Set(missing.map(t => t[0]))]) {
      if (disposed || id !== generation) return;
      try {
        const batch = missing.filter(t => t[0] === level);
        let response;
        const deadline = Date.now() + 90000;
        while (true) {
          if (disposed || id !== generation) return;
          response = await axios.post('/api/amap-app/map', { level, tiles: batch.map(t => t.slice(1)) }, { signal: request.signal, timeout: 70000 });
          if (response.status !== 202 || !response.data.data?.pending) break;
          if (Date.now() >= deadline) throw new Error('地图加载超时，请重试');
          await new Promise(resolve => setTimeout(resolve, 750));
        }
        if (disposed || id !== generation) return;
        if (response.data.status !== 'ok') throw new Error(response.data.message || '请登录后重试');
        for (const tile of response.data.data.tiles) {
          if (tile.error) { failed = true; continue; }
          const key = `${tile.level}/${tile.x}/${tile.y}`;
          cache.delete(key); cache.set(key, { time: tile.missingLayers?.length ? 0 : Date.now(), collection: tile.collection, surfaces: tile.surfaces, transit: tile.transit, placeLabels: tile.placeLabels, missingLayers: tile.missingLayers });
          if (tile.missingLayers?.length) failed = true;
        }
        while (cache.size > 128) cache.delete(cache.keys().next().value!);
        draw(tiles);
      } catch {
        if (disposed || id !== generation) return;
        failed = true;
      }
    }
    report(failed ? '部分图层加载失败，可重试补齐' : '');
  }

  function schedule() {
    generation++; request?.abort();
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void load(), 220);
  }
  map.on('moveend rotate', schedule);
  void load();
  return { setAppearance(value: AppMapAppearance) { appearance = value; draw(visible()); }, retry: () => void load(), dispose() {
    disposed = true; generation++; request?.abort(); if (timer) clearTimeout(timer);
    map.off('moveend rotate', schedule); roads.remove(); labels.remove(); renderer.remove(); surfaces.remove(); surfaceRenderer.remove(); cache.clear();
  } };
}
