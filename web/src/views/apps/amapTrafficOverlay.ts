import axios from 'axios';
import L from 'leaflet';

export type TrafficRoad = { status: 1 | 2 | 3; path: [number, number][]; name?: string; angle?: number };

export function attachTrafficOverlay(map: L.Map, report: (message: string) => void, onRoads: (roads: TrafficRoad[]) => void) {
  let enabled = false, active = true, disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let lastCenter: L.LatLng | undefined, lastUpdated = 0;

  async function refresh() {
    timer = undefined;
    if (!enabled || !active || disposed) return;
    if (map.getZoom() < 12) {
      onRoads([]);
      lastUpdated = 0;
      report('放大地图后显示实时路况');
      return;
    }
    const center = map.getCenter();
    if (lastCenter && Date.now() - lastUpdated < 45000 && center.distanceTo(lastCenter) < 700) return;
    controller?.abort();
    controller = new AbortController();
    try {
      const response = await axios.post('/api/amap-app/traffic',
        { center: [center.lng, center.lat] }, { signal: controller.signal, timeout: 12000 });
      if (!enabled || !active || disposed) return;
      const roads = response.data?.data?.roads as TrafficRoad[] | undefined;
      if (response.data?.status !== 'ok' || !Array.isArray(roads)) throw new Error('路况数据无效');
      onRoads(roads);
      lastCenter = center;
      lastUpdated = Date.now();
      report(roads.length ? '' : '此区域暂无实时路况');
    } catch (error) {
      if (axios.isCancel(error) || disposed || !enabled || !active) return;
      onRoads([]);
      report(axios.isAxiosError(error) ? error.response?.data?.message || '实时路况暂不可用' : '实时路况暂不可用');
      lastUpdated = Date.now();
      lastCenter = center;
    }
  }
  function schedule() {
    if (!enabled || !active || disposed || timer) return;
    timer = setTimeout(() => void refresh(), 750);
  }
  map.on('moveend zoomend', schedule);
  const interval = setInterval(schedule, 45000);
  return {
    setEnabled(value: boolean) {
      enabled = value;
      if (!value) { controller?.abort(); onRoads([]); lastUpdated = 0; report(''); }
      else schedule();
    },
    setActive(value: boolean) {
      active = value;
      if (!value) { controller?.abort(); onRoads([]); lastUpdated = 0; }
      else schedule();
    },
    dispose() {
      disposed = true; controller?.abort(); clearInterval(interval);
      if (timer) clearTimeout(timer);
      map.off('moveend zoomend', schedule);
    },
  };
}
