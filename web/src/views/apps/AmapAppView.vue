<script setup lang="ts">
import { navigationEngine, navigationEngineNotice } from '@/functions/navigationEngine';
import { createRouteFusion, type FusionPosition } from './amapRouteFusion';
import { navigationViewport } from './amapNavigationViewport';
import { remainingRouteSections } from './amapRemainingRoute';
import { remainingCongestionPath, routeCongestionRuns, type CongestionRun } from './amapRouteTraffic';
import { findParallelRoute, type RoadKind } from './amapParallelRoad';
import { computed, nextTick, watch, watchEffect, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref } from 'vue';
import axios from 'axios';
import { publishBackgroundNavigation, clearBackgroundNavigation } from '@/stores/backgroundNavigation';
const viewActive = ref(true);
import { navigationVoicePhrase } from './amapVoicePhrases';
import { upcomingServiceAreas, shouldAnnounceServiceArea, type UpcomingServiceArea } from './amapServiceAreas';
import NavigationTurnIcon from '@/components/NavigationTurnIcon.vue';
import { createLivePositionGate } from './amapLivePosition';
import AmapNavigation3D from './AmapNavigation3D.vue';

import { prepareLocalSpeech, preloadLocalSpeech, cancelLocalSpeechPreload, speakLocal, stopLocalSpeech, localSpeechState } from '@/functions/localSpeech';
import { useGeoLocationStore, type GeoLocation } from '@/stores/geoLocation';
const geoLocation = useGeoLocationStore();
import { useRouter } from 'vue-router';
import L from 'leaflet';
import 'leaflet-rotate';
import { bearingBetween, movementHeading, smoothHeading } from './amapHeading';
import type { Place } from './amapSearch';
import { searchWebPlaces } from './amapWebSearch';
import { attachAppMap, type AppMapAppearance } from './amapVectorMap';
import { attachTrafficOverlay, type TrafficRoad } from './amapTrafficOverlay';
const mapStatus = ref('');
const trafficStatus = ref('');
const trafficRoads = ref<TrafficRoad[]>([]);
const trafficEnabled = ref(true);
let trafficOverlay: ReturnType<typeof attachTrafficOverlay> | undefined;
const liveSpeed = ref<number | null>(null);
let positionWatch: number | undefined;
const use3D = ref(false), map3DStatus = ref('');
const map3D = ref<InstanceType<typeof AmapNavigation3D>>();
const mapCenter = ref<Point>([0, 0]), mapZoom = ref(17);
const show3D = computed(() => use3D.value && !overviewActive.value && (hasOrigin.value || hasDestination.value));
function toggle3D() {
  use3D.value = !use3D.value;
  if (use3D.value) { layerMenu.value = false; orientation.value = 'heading'; followLocation(); }
}
function fail3D() { use3D.value = false; error.value = '当前设备无法显示 3D 地图，已切换为 2D'; }

const layerMenu = ref(false);
const mapAppearance = ref<AppMapAppearance>({ theme: 'day', surfaces: true, roads: true, labels: true, transit: true, places: true });
watch(mapAppearance, value => appMap?.setAppearance(value), { deep: true });
let appMap: ReturnType<typeof attachAppMap> | undefined;
import 'leaflet/dist/leaflet.css';
import { browserNavigationPoint } from '@/functions/navigationCoordinates';
import { formatRouteDuration, formatRouteTolls } from './amapRouteSummary';
import { createPositionTransition } from './amapPositionTransition';
import { cumulative, instruction, matchPosition, meters, pointAt, type AppRoute, type Point } from './amapNavigation';
const router = useRouter();
const mapElement = ref<HTMLElement>();
const topPanel = ref<HTMLElement>(), footerPanel = ref<HTMLElement>();
const overviewActive = ref(false), orientation = ref<'north' | 'heading'>('north');
const heading = ref<number>();
const displayedPosition = ref<Point>(), displayedHeading = ref(0);
const positionTransition = createPositionTransition();
let positionFrame: number | undefined;
let lastAutoZoomAt = -Infinity;
function followPosition(point: Point, now: number) {
  if (!map || !following.value) return;
  applyOrientation();
  const navigation = mode.value !== 'idle' && !overviewActive.value;
  const headingUp = navigation && orientation.value === 'heading';
  if (navigation) {
    const target = navigationViewport(liveSpeed.value).zoom;
    const current = map.getZoom();
    if (Math.abs(target - current) >= .3 && now - lastAutoZoomAt >= 1200) {
      map.setZoom(current + Math.max(-.5, Math.min(.5, target - current)), { animate: false });
      lastAutoZoomAt = now;
    }
  }
  const size = map.getSize();
  const wanted = L.point(size.x / 2, size.y * (headingUp ? navigationViewport(liveSpeed.value).vehicleY : .5));
  const actual = map.latLngToContainerPoint(latLng(point));
  const shift = actual.subtract(wanted);
  if (Math.abs(shift.x) > 1 || Math.abs(shift.y) > 1) map.panBy(shift, { animate: false });
}
function cancelPositionAnimation() {
  if (positionFrame !== undefined) cancelAnimationFrame(positionFrame);
  positionFrame = undefined;
}
function animatePosition(point: Point, snap = false) {
  cancelPositionAnimation();
  positionTransition.move({ point, heading: heading.value || 0 }, performance.now(), snap);
  const frame = (now: number) => {
    positionFrame = undefined;
    if (!viewActive.value || disposed || !map) return;
    const value = positionTransition.sample(now)!;
    displayedPosition.value = value.point; displayedHeading.value = value.heading;
    marker?.setLatLng(latLng(value.point));
    if (following.value) {
      followPosition(value.point, now);
    } else marker?.setRotation(value.heading * Math.PI / 180);
    if (!positionTransition.done(now)) positionFrame = requestAnimationFrame(frame);
  };
  frame(performance.now());
}
let headingAnchor: Point | undefined, overviewGeneration = 0;
function applyOrientation() {
  if (!map || !viewActive.value) return;
  const bearing = orientation.value === 'heading' && !overviewActive.value ? -displayedHeading.value : 0;
  if (Math.abs(((map.getBearing() - bearing + 540) % 360) - 180) > .5) map.setBearing(bearing);
  marker?.setRotation(displayedHeading.value * Math.PI / 180);
}
const viewModeLabel = computed(() => overviewActive.value ? '路线全览' : orientation.value === 'heading' ? '车头向上' : '北向上');
const nextViewModeLabel = computed(() => overviewActive.value ? '北向上' : !following.value ? viewModeLabel.value : orientation.value === 'north' ? '车头向上' : current.value ? '路线全览' : '北向上');
function cycleViewMode() {
  if (!overviewActive.value && !following.value) { followLocation(); return; }
  if (!overviewActive.value && orientation.value === 'heading' && current.value) { void overview(); return; }
  orientation.value = overviewActive.value || orientation.value === 'heading' ? 'north' : 'heading';
  followLocation();
}
async function overview() {
  if (!viewActive.value) return;
  overviewActive.value = true;
  following.value = false;
  applyOrientation();
  const id = ++overviewGeneration;
  await nextTick();
  if (disposed || id !== overviewGeneration || !overviewActive.value || !map || !current.value) return;
  const bounds = L.latLngBounds([...current.value.path, origin.value, destination.value].map(latLng));
  if (!bounds.isValid()) return;
  const top = (topPanel.value?.offsetTop ?? 14) + (topPanel.value?.offsetHeight ?? 0) + 24;
  const bottom = map.getSize().y - (footerPanel.value?.offsetTop ?? map.getSize().y) + 24;
  map.fitBounds(bounds, { paddingTopLeft: [32, top], paddingBottomRight: [92, bottom], maxZoom: 17, animate: false });
}
function followLocation() {
  overviewActive.value = false; overviewGeneration++;
  following.value = true;
  if (heading.value === undefined && current.value) {
    const ahead = pointAt(current.value, progress.value + 25);
    heading.value = bearingBetween(pointAt(current.value, progress.value), ahead);
  }
  applyOrientation();
  if (map && (location.value || hasOrigin.value)) {
    map.setView(latLng(location.value || current.value?.path[0] || origin.value),
      mode.value !== 'idle' ? navigationViewport(liveSpeed.value).zoom : 17, { animate: false });
    lastAutoZoomAt = performance.now();
  }
  if (location.value) animatePosition(location.value, true);
}
const routes = ref<AppRoute[]>([]), selected = ref(0), busy = ref(false), error = ref(''), mapReady = ref(false);
const searching = ref(false), searchMessage = ref('');
const query = ref(''), tips = ref<Place[]>([]), picking = ref<'origin' | 'destination'>('destination');
const origin = ref<Point>([0, 0]), destination = ref<Point>([0, 0]);
const hasOrigin = ref(false), hasDestination = ref(false);
const originName = ref('等待车辆定位'), destinationName = ref('请选择目的地');
const mode = ref<'idle' | 'live' | 'demo'>('idle'), progress = ref(0), following = ref(true), muted = ref(false);
const status = ref('点击地图选择终点；先定位可使用当前位置作为起点'), location = ref<Point>(), arrived = ref(false);
const roadSwitchOpen = ref(false);
const lastGpsPoint = ref<Point>();
const current = computed(() => routes.value[selected.value]);
const congestionRuns = computed(() => current.value && trafficEnabled.value ? routeCongestionRuns(current.value, trafficRoads.value) : []);
const navigationCongestionRuns = computed(() => mode.value === 'idle' ? [] : congestionRuns.value);
watch([mode, current, trafficEnabled], () => trafficOverlay?.setEnabled(trafficEnabled.value && mode.value !== 'idle' && !!current.value));
watch(trafficRoads, () => { if (mode.value !== 'idle') draw(false); });
const next = computed(() => current.value ? instruction(current.value, progress.value) : undefined);
const serviceAreas = computed(() => upcomingServiceAreas(current.value, progress.value));
function serviceAreaDistance(area: UpcomingServiceArea) {
  return progress.value >= area.from ? '当前路段' : `约 ${formatDistance(area.distance)}后`;
}
const remaining = computed(() => current.value ? Math.max(0, cumulative(current.value)[current.value.path.length - 1] - progress.value) : 0);
let map: L.Map, marker: L.Marker | undefined, startMarker: L.Marker | undefined, endMarker: L.Marker | undefined, lines: L.Polyline[] = [];
let congestionLines: { run: CongestionRun; line: L.Polyline }[] = [];
let renderedLineProgress = -Infinity;
type LineState = 'past' | 'active' | 'future';
let lineStates: LineState[] = [];
function routeLineStates(route: AppRoute, distance: number): LineState[] {
  const lengths = cumulative(route), bounds = [0, ...route.breaks, route.path.length];
  const states: LineState[] = [];
  for (let index = 1; index < bounds.length; index++) {
    const from = bounds[index - 1], to = bounds[index];
    if (to - from < 2) continue;
    states.push(distance >= lengths[to - 1] ? 'past' : distance <= lengths[from] ? 'future' : 'active');
  }
  return states;
}
const latLng = (p: Point): L.LatLngTuple => [p[1], p[0]];
let resizeObserver: ResizeObserver | undefined;
let locationTimeout: ReturnType<typeof setTimeout> | undefined;
let simulation: ReturnType<typeof setInterval> | undefined;
let controller: AbortController | undefined, disposed = false, generation = 0, locationGeneration = 0, offCount = 0, lastReplan = 0, spoken = '';
const announcedServiceAreas = new Set<string>();
const formatDistance = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)} 公里` : `${Math.round(n / 10) * 10} 米`;
function speak(text: string) {
  if (muted.value) return;
  void speakLocal(text, 15000).catch(() => {});
}
function prepareVoice() { if (!muted.value) void prepareLocalSpeech().catch(e => { localSpeechState.error=String(e); }); }

watch([current, () => next.value?.key, mode, muted], () => {
  cancelLocalSpeechPreload();
  if (muted.value || !next.value || mode.value === 'idle') return;
  const turn = next.value;
  void preloadLocalSpeech([
    navigationVoicePhrase(turn, false), navigationVoicePhrase(turn, true), '已到达目的地附近',
  ]).catch(() => { /* Playback reports engine errors; navigation remains usable. */ });
});

function finishNavigationFollow(message: string) {
  const wasLive = mode.value === 'live';
  stop(wasLive);
  controller?.abort(); generation++; busy.value = false;
  overviewActive.value = false; overviewGeneration++; following.value = true;
  // Live navigation keeps its existing GPS watch; simulation returns to real GPS.
  if (!wasLive && viewActive.value) locate(false, true);
  status.value = message;
  draw(false); followLocation();
}
function endNavigation() { finishNavigationFollow('导航已结束，继续跟随车辆'); }

async function switchParallelRoad(target: RoadKind) {
  if (mode.value !== 'live' || busy.value || !current.value || !lastGpsPoint.value) return;
  const previous = current.value, point = lastGpsPoint.value;
  const id = ++generation;
  controller?.abort(); controller = new AbortController();
  busy.value = true; error.value = '';
  status.value = '正在查找相邻道路…';
  try {
    const response = await axios.post('/api/amap-app/route', { origin: point, destination: destination.value },
      { signal: controller.signal, timeout: 45000 });
    if (disposed || id !== generation || mode.value !== 'live') return;
    const data = response.data.data;
    if (response.data.status !== 'ok' || data?.state !== 'ready' || !data.routes?.length)
      throw new Error(response.data.message || '暂时无法重新规划路线');
    const index = findParallelRoute(data.routes, previous, point, target);
    if (index < 0) {
      status.value = '附近没有可确认的对应道路，继续当前路线';
      return;
    }
    routes.value = data.routes; selected.value = index;
    const corrected = matchPosition(data.routes[index], point, 0, true);
    progress.value = corrected.progress;
    location.value = corrected.point;
    origin.value = point; originName.value = '当前位置';
    offCount = 0; spoken = ''; announcedServiceAreas.clear();
    roadSwitchOpen.value = false;
    draw(false); followLocation();
    status.value = '已切换道路，路线已重新规划';
    speak('已为您重新规划路线');
  } catch (exception) {
    if (disposed || id !== generation) return;
    status.value = '道路切换失败，继续当前路线';
    error.value = axios.isAxiosError(exception) ? exception.response?.data?.message || '道路切换请求失败，请稍后重试' : (exception as Error).message;
  } finally { if (id === generation) busy.value = false; }
}

watchEffect(() => {
  if (mode.value === 'idle' || !current.value) { clearBackgroundNavigation(); return; }
  publishBackgroundNavigation({ simulated: mode.value === 'demo', muted: muted.value,
    arrow: next.value?.arrow || '↑', instruction: next.value ? `${formatDistance(next.value.distance)}后${next.value.text}` : '继续前行',
    road: next.value?.road || '', remaining: formatDistance(remaining.value), status: status.value,
  }, { stop: endNavigation, toggleVoice });
});
onDeactivated(() => {
  cancelPositionAnimation();
  viewActive.value = false; appMap?.setActive(false); appMap?.releaseMemory(); trafficOverlay?.setActive(false); cancelSearch();
  if (mode.value === 'idle') { resumeLocationOnActivate = trackingLocation; stop(); }
});
watch(show3D, enabled => {
  // The 3D ground has its own decoded-tile warm-up. Keep the hidden 2D layer
  // idle so both renderers do not compete for the single map helper.
  appMap?.setActive(!enabled && viewActive.value);
  appMap?.setRoute(enabled ? undefined : current.value, progress.value);
  trafficOverlay?.setActive(viewActive.value);
});
onActivated(async () => {
  viewActive.value = true;
  await nextTick();
  if (disposed || !map || !viewActive.value) return;
  map.invalidateSize({ pan: false }); appMap?.setActive(!show3D.value); trafficOverlay?.setActive(true); endpoints(); draw(false);
  if (location.value) animatePosition(location.value, true);
  applyOrientation();
  if (resumeLocationOnActivate) { resumeLocationOnActivate = false; locate(false, true); }
});

function endpoints() {
  if (!map || !viewActive.value) return;
  if ((hasOrigin.value || hasDestination.value) && !appMap) appMap = attachAppMap(map, message => { mapStatus.value = message; });
  startMarker?.remove(); endMarker?.remove();
  const pin = (text: string, color: string) => L.divIcon({ className: '', html: `<span style="display:block;background:${color};color:white;border:2px solid white;border-radius:50%;width:26px;height:26px;text-align:center;line-height:23px;font-size:12px">${text}</span>`, iconSize: [26,26], iconAnchor: [13,13] });
  if (hasOrigin.value) startMarker = L.marker(latLng(origin.value), { icon: pin('起', '#0ca87f') }).addTo(map);
  if (hasDestination.value) endMarker = L.marker(latLng(destination.value), { icon: pin('终', '#f38159') }).addTo(map);
}
function draw(fit = true) {
  if (!map || !viewActive.value) return;
  lines.forEach(line => line.remove()); lines = [];
  congestionLines.forEach(({ line }) => line.remove()); congestionLines = [];
  lineStates = [];
  routes.value.forEach((route, index) => {
    if (mode.value !== 'idle' && index !== selected.value) return;
    const sections = remainingRouteSections(route, mode.value === 'idle' ? 0 : progress.value);
    if (mode.value !== 'idle') lineStates = routeLineStates(route, progress.value);
    for (const path of sections) {
      lines.push(L.polyline(path.map(latLng), { color: index === selected.value ? mode.value === 'idle' ? '#12bc87' : '#1688ef' : '#8aa1b3', weight: index === selected.value ? 8 : 5,
        opacity: index === selected.value ? 1 : .55, lineJoin: 'round', lineCap: 'round' }).addTo(map));
    }
  });
  if (mode.value !== 'idle') for (const run of congestionRuns.value) {
    const path = remainingCongestionPath(run, progress.value);
    const line = L.polyline(path.map(latLng), { color: run.status === 3 ? '#e44650' : '#f5a623', weight: 8,
      opacity: 1, lineJoin: 'round', lineCap: 'round', interactive: false }).addTo(map);
    congestionLines.push({ run, line });
  }
  renderedLineProgress = progress.value;
  endpoints();
  appMap?.setRoute(show3D.value ? undefined : current.value, progress.value);
  if (fit && lines.length) void overview();
}
function trimDrivenRoute() {
  if (mode.value === 'idle' || !current.value || Math.abs(progress.value - renderedLineProgress) < 8) return;
  const sections = remainingRouteSections(current.value, progress.value);
  if (sections.length !== lines.length) { draw(false); return; }
  const states = routeLineStates(current.value, progress.value);
  sections.forEach((section, index) => {
    if (states[index] === 'active' || states[index] !== lineStates[index]) lines[index].setLatLngs(section.map(latLng));
  });
  for (const { run, line } of congestionLines) {
    if (progress.value < run.start) continue;
    if (progress.value >= run.end) {
      if ((line.getLatLngs() as L.LatLng[]).length) line.setLatLngs([]);
    } else line.setLatLngs(remainingCongestionPath(run, progress.value).map(latLng));
  }
  lineStates = states;
  renderedLineProgress = progress.value;
}
function choose(index: number) { selected.value = index; progress.value = 0; arrived.value = false; announcedServiceAreas.clear(); draw(); }
function clearRoute() { overviewActive.value = false; overviewGeneration++; stop(); controller?.abort(); generation++; busy.value = false; routes.value = []; heading.value = undefined; headingAnchor = undefined; applyOrientation(); draw(false); }
function setPoint(point: Point, name: string) {
  cancelSearch();
  clearRoute();
  if (picking.value === 'origin') { hasOrigin.value = true; origin.value = point; originName.value = name; picking.value = 'destination'; }
  else { hasDestination.value = true; destination.value = point; destinationName.value = name; }
  tips.value = []; query.value = ''; endpoints();
}
let searchGeneration = 0, searchController: AbortController | undefined;
function cancelSearch() {
  searchGeneration++; searchController?.abort(); searching.value = false;
  tips.value = []; searchMessage.value = '';
}
watch([query, picking], cancelSearch, { flush: 'sync' });
function selectPlace(place: Place) {
  setPoint(place.location, place.name);
  following.value = false;
  map?.setView(latLng(place.location), 16);
  status.value = '地点已选择，可以规划路线';
}
async function search() {
  cancelSearch();
  const keywords = query.value.trim();
  if (!keywords) return;
  const values = keywords.split(/[,，\s]+/).map(Number);
  if (values.length === 2 && values.every(Number.isFinite) && Math.abs(values[0]) <= 180 && Math.abs(values[1]) <= 85) {
    selectPlace({ id: 'coordinate', location: values as Point, name: '坐标选点', address: '' });
    return;
  }
  const id = searchGeneration;
  searchController = new AbortController(); searching.value = true;
  try {
    const places = await searchWebPlaces(keywords, searchController.signal, location.value || (hasOrigin.value ? origin.value : undefined));
    if (disposed || id !== searchGeneration) return;
    tips.value = places;
    if (!tips.value.length) searchMessage.value = '没有找到地点，试试加上城市名称';
  } catch (exception) {
    if (disposed || id !== searchGeneration) return;
    searchMessage.value = axios.isAxiosError(exception) ? exception.response?.data?.message || '地点搜索失败，请稍后重试' : (exception as Error).message;
  } finally {
    if (id === searchGeneration) searching.value = false;
  }
}

async function plan(replan = false) {
  if (busy.value || !hasOrigin.value || !hasDestination.value) return;
  if (!replan) stop();
  const id = ++generation;
  controller?.abort(); controller = new AbortController();
  busy.value = true; error.value = ''; arrived.value = false;
  try {
    const response = await axios.post('/api/amap-app/route', { origin: origin.value, destination: destination.value }, { signal: controller.signal, timeout: 45000 });
    if (disposed || id !== generation) return;
    if (response.data.status === 'need_login') { await router.replace('/login'); return; }
    const data = response.data.data;
    if (response.data.status !== 'ok' || data?.state !== 'ready' || !data.routes?.length) throw new Error(response.data.message || '这条路线暂未成功解析，请更换地点或重试');
    routes.value = data.routes; selected.value = 0; progress.value = 0; offCount = 0; spoken = ''; announcedServiceAreas.clear(); draw(!replan);
    status.value = replan ? '路线已重新规划' : '路线已就绪，选择方案后开始导航';
    if (replan) speak('已为您重新规划路线');
  } catch (exception) {
    if (id !== generation || disposed) return;
    error.value = axios.isAxiosError(exception) ? exception.response?.data?.message || '路线请求失败，请重试' : (exception as Error).message;
    if (replan) status.value = '偏离路线，重算失败；请稍后重试';
    else { routes.value = []; draw(false); }
  } finally { if (id === generation) busy.value = false; }
}
function updatePosition(point: Point, accuracy = 0, gpsHeading?: number | null, speed?: number | null, recovered = false, fusion?: FusionPosition) {
  const direction = movementHeading(headingAnchor, point, accuracy, gpsHeading, speed);
  if (direction !== undefined) { heading.value = smoothHeading(heading.value, direction); headingAnchor = point; }
  else if (!headingAnchor && accuracy <= 60) headingAnchor = point;
  location.value = point;
  if (viewActive.value) {
  if (!marker) marker = L.marker(latLng(point), { icon: L.divIcon({ className: '', html: '<div class="amap-vehicle">▲</div>', iconSize: [36,36], iconAnchor: [18,18] }), rotateWithView: true, zIndexOffset: 1000 }).addTo(map);
  animatePosition(point);
  }
  if (!current.value || mode.value === 'idle') return;
  if (accuracy > 60) { status.value = '定位精度不足，等待更准确的位置'; return; }
  const match = matchPosition(current.value, point, progress.value, recovered);
  if (match.distance > Math.max(40, accuracy * 1.5)) {
    offCount++;
    status.value = '已偏离路线';
    if (mode.value === 'live' && offCount >= 3 && !busy.value && Date.now() - lastReplan > 20000) {
      lastReplan = Date.now(); origin.value = point; originName.value = '当前位置'; status.value = '正在重新规划'; void plan(true);
    }
    return;
  }
  offCount = 0; progress.value = fusion?.progress ?? (recovered ? match.progress : Math.max(progress.value, match.progress));
  trimDrivenRoute();
  appMap?.setRoute(current.value, progress.value);
  if (recovered) spoken = '';
  status.value = mode.value === 'demo' ? '模拟导航 · 非车辆实时位置'
    : '实时导航中 · 车机定位';
  if (fusion) status.value = fusion.state === 'tracking' ? '实时导航中 · 路线融合' : fusion.state === 'recovering' ? '定位恢复 · 平滑校正中' : fusion.state === 'waiting' ? '推算已暂停 · 等待可靠定位' : `定位精度下降 · 估算位置（${fusion.estimationSeconds ?? 0} 秒）`;
  if (!fusion?.estimated && remaining.value < 25 && meters(point, current.value.path[current.value.path.length - 1]) < 40) {
    finishNavigationFollow('已到达目的地附近，继续跟随车辆'); arrived.value = true; speak('已到达目的地附近'); return;
  }
  if (fusion?.state === 'waiting') return;
  const turn = next.value;
  if (turn && turn.distance < 250) {
    const key = `${turn.key}:${turn.distance < 40 ? 'near' : 'ahead'}`;
    if (key !== spoken) { spoken = key; speak(navigationVoicePhrase(turn, turn.distance < 40)); }
  }
  const area = serviceAreas.value[0];
  if (!muted.value && area && !announcedServiceAreas.has(area.key) &&
      shouldAnnounceServiceArea(area, progress.value, turn?.distance ?? Infinity)) {
    announcedServiceAreas.add(area.key);
    speak(`前方有${area.name}，请留意入口`);
  }
}
function toggleVoice() { muted.value = !muted.value; if (muted.value) stopLocalSpeech(); else prepareVoice(); }
let routeFusion: ReturnType<typeof createRouteFusion> | undefined;
let fusionTimer: ReturnType<typeof setInterval> | undefined;
function renderFusion(result?: FusionPosition) {
  if (!result || disposed || mode.value !== 'live') return;
  liveSpeed.value = result.speed * 3.6;
  updatePosition(result.point, 0, result.heading, result.speed, result.state === 'off-route', result);
}
function stopFusion() { clearInterval(fusionTimer); fusionTimer = undefined; routeFusion = undefined; }
function startFusion() {
  stopFusion();
  if (navigationEngine.value !== 'route-fusion' || mode.value !== 'live' || !current.value) return;
  routeFusion = createRouteFusion(current.value);
  fusionTimer = setInterval(() => renderFusion(routeFusion?.tick(performance.now())), 250);
}
watch(current, () => startFusion());
let trackingLocation = false, resumeLocationOnActivate = false;
watch(navigationEngine, () => startFusion());
function stop(keepLocation = false) {
  stopFusion();
  roadSwitchOpen.value = false;
  announcedServiceAreas.clear();
  cancelLocalSpeechPreload();
  if (!keepLocation) {
    trackingLocation = false;
    locationGeneration++;
    if (positionWatch !== undefined) navigator.geolocation?.clearWatch(positionWatch);
    positionWatch = undefined; liveSpeed.value = null;
    if (locationTimeout) clearTimeout(locationTimeout);
    locationTimeout = undefined;
    geoLocation.removeListener('amap-navigation');
  }
  if (simulation) clearInterval(simulation);
  simulation = undefined; mode.value = 'idle';
  stopLocalSpeech();
}
function startDemo() {
  prepareVoice();
  if (!current.value) return;
  stop(); orientation.value = 'heading'; overviewActive.value = false; overviewGeneration++; mode.value = 'demo'; progress.value = 0; following.value = true; arrived.value = false; spoken = '';
  headingAnchor = current.value.path[0]; heading.value = bearingBetween(headingAnchor, pointAt(current.value, 25));
  map.setZoom(navigationViewport(liveSpeed.value).zoom); draw(false); updatePosition(current.value.path[0]);
  simulation = setInterval(() => { if (current.value) updatePosition(pointAt(current.value, progress.value + 15)); }, 500);
}
function locate(navigate = false, preserveRoute = false) {
  if (navigate) prepareVoice();
  if (!map || !navigator.geolocation) { error.value = '当前浏览器无法定位'; return; }
  if (!window.isSecureContext) { error.value = '当前位置页面不是安全连接，请通过 HTTPS 访问后再定位'; status.value = '定位需要安全连接'; return; }
  if (!navigate && !preserveRoute) clearRoute(); else stop();
  trackingLocation = true;
  following.value = true;
  const id = locationGeneration; error.value = ''; status.value = '正在获取当前位置…';
  let received = false;
  const liveGate = createLivePositionGate();
  // Permission inspection is advisory; do not delay the user-initiated position request.
  void navigator.permissions?.query({ name: 'geolocation' }).then(permission => {
    if (disposed || id !== locationGeneration || received) return;
    if (permission.state === 'granted') status.value = '定位已授权，正在等待车机返回位置';
    else if (permission.state === 'prompt') status.value = '请在浏览器的位置权限提示中允许定位';
    else status.value = '此网站的定位权限被拒绝，请检查浏览器网站权限';
  }).catch(() => { /* Some car browsers do not support permission inspection. */ });
  locationTimeout = setTimeout(() => {
    if (disposed || id !== locationGeneration || received) return;
    status.value = '等待车机返回位置，将继续获取';
    error.value = '定位尚未返回，仍在等待；可打开设备诊断核对，或在地图上选择起点';
  }, 25000);
  if (navigate) {
    orientation.value = 'heading'; overviewActive.value = false; overviewGeneration++;
    mode.value = 'live'; following.value = true; arrived.value = false; headingAnchor = undefined;
    draw(false);
    // Use the route's initial direction until GPS supplies a usable vehicle heading.
    if (heading.value === undefined && current.value) heading.value = bearingBetween(current.value.path[0], pointAt(current.value, 25));
    applyOrientation(); map.setZoom(navigationViewport(liveSpeed.value).zoom);
    startFusion();
  }
  const receive = (position: GeoLocation) => {
    if (disposed || id !== locationGeneration) return;
    if (position.source !== 'gps') return;
    const accepted = liveGate.accept(position);
    if (!accepted.accepted) return;
    const first = !received;
    received = true; error.value = "";
    if (locationTimeout) clearTimeout(locationTimeout);
    locationTimeout = undefined;
    const point = browserNavigationPoint(position.longitude, position.latitude);
    lastGpsPoint.value = point;
    if (mode.value === 'idle') { hasOrigin.value = true; origin.value = point; originName.value = '当前位置'; endpoints(); if (first && !preserveRoute && !navigate) map.setView(latLng(point), 16); if (!preserveRoute && !navigate) status.value = '已定位，请选择目的地'; }
    if (mode.value === 'live' && routeFusion) {
      const result = routeFusion.accept({ point, accuracy: position.accuracy, speed: position.speed, heading: position.heading, timestamp: position.timestamp }, performance.now());
      renderFusion(result);
      if (!result && !location.value) status.value = '路线融合 · 等待可靠定位';
      return;
    }
    liveSpeed.value = typeof position.speed === 'number' && Number.isFinite(position.speed) && position.speed >= 0 ? position.speed * 3.6 : null;
    updatePosition(point, position.accuracy, position.heading, position.speed, accepted?.recovered);

  };
  const failed = (failure: GeolocationPositionError) => {
    if (disposed || id !== locationGeneration) return;
    if (failure.code !== 1) { if (!received) status.value = '暂未取得位置，正在重试'; return; }
    stop(); status.value = '未能取得当前位置';
    error.value = failure.code === 1 ? '此网站的定位请求被拒绝，请检查网站权限及浏览器定位设置' :
      failure.code === 2 ? '浏览器暂时无法提供位置，请检查车机定位信号，或在地图上选择起点' :
      failure.code === 3 ? '获取位置超时；这不代表未授权，请稍后重试或在地图上选择起点' : '定位失败，请重试';
  };
  if (navigate) {

    const startWatch = () => {
      if (disposed || id !== locationGeneration) return;
      if (positionWatch !== undefined) navigator.geolocation.clearWatch(positionWatch);
      positionWatch = undefined;
      // Keep single-position polling as a fallback when the watch stops reporting.
      try {
        positionWatch = navigator.geolocation.watchPosition(position => receive({
          ...position.coords, latitude: position.coords.latitude, longitude: position.coords.longitude,
          accuracy: position.coords.accuracy, altitude: position.coords.altitude,
          altitudeAccuracy: position.coords.altitudeAccuracy, speed: position.coords.speed,
          heading: position.coords.heading, timestamp: position.timestamp, source: 'gps',
        }), failed, { maximumAge: 0, timeout: 10000 });
      } catch { /* One-shot polling remains active. */ }
    };
    startWatch();

  }
  geoLocation.addListener('amap-navigation', receive);
  geoLocation.addErrorListener('amap-navigation', failed);
  const cached = geoLocation.getCurPosition();
  if (cached) receive(cached);
  geoLocation.init();
  geoLocation.refresh();
}
function pauseMapFollowing() {
  following.value = false; overviewActive.value = false; overviewGeneration++;
}
function beginMapTouch(event: TouchEvent) {
  if (event.touches.length === 2) pauseMapFollowing();
}
onMounted(() => {
  if (!mapElement.value) return;
  mapElement.value.addEventListener('touchstart', beginMapTouch, { passive: true, capture: true });
  map = L.map(mapElement.value, { rotate: true, rotateControl: false, touchRotate: true, shiftKeyRotate: false, zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 18, zoomSnap: .25 }).setView([20, 0], 3);
  trafficOverlay = attachTrafficOverlay(map, message => { trafficStatus.value = message; }, roads => { trafficRoads.value = roads; });
  trafficOverlay.setEnabled(trafficEnabled.value && mode.value !== 'idle' && !!current.value);
  map.on('move zoom', () => { const center=map.getCenter(); mapCenter.value=[center.lng,center.lat]; mapZoom.value=map.getZoom(); });
  map.attributionControl.addAttribution('© 高德地图 · App 矢量地图');

  map.on('click', event => { if (mode.value === 'idle' && !busy.value) setPoint([event.latlng.lng, event.latlng.lat], '地图选点'); });
  map.on('dragstart', pauseMapFollowing);
  resizeObserver = new ResizeObserver(() => {
    if (!viewActive.value) return;
    map.invalidateSize({ pan: false });
    if (overviewActive.value) void overview();
  });
  resizeObserver.observe(mapElement.value);
  if (footerPanel.value) resizeObserver.observe(footerPanel.value);
  mapReady.value = true; endpoints(); locate(false);
});
onBeforeUnmount(() => { cancelPositionAnimation(); clearBackgroundNavigation(); mapElement.value?.removeEventListener('touchstart', beginMapTouch, true); disposed = true; generation++; cancelSearch(); controller?.abort(); stop(); resizeObserver?.disconnect(); trafficOverlay?.dispose(); appMap?.dispose(); map?.remove(); });
</script>

<template>
  <section class="navigation-app" :class="{ 'map-day': mapAppearance.theme === 'day' }">
    <div ref="mapElement" class="navigation-map" aria-label="高德导航地图"></div>
    <AmapNavigation3D v-if="show3D && viewActive" ref="map3D" :center="mapCenter" :position="displayedPosition || location" :heading="displayedHeading" :bearing="orientation === 'heading' ? displayedHeading : 0" :zoom="mapZoom" :route="current" :progress="progress" :traffic-runs="navigationCongestionRuns" :navigating="mode !== 'idle'" @status="map3DStatus = $event" @failed="fail3D" @pick="mode === 'idle' && !busy && setPoint($event, '地图选点')" />
    <div v-if="!mapReady"  class="map-loading">{{ error || '正在加载地图…' }}</div>
    <header ref="topPanel" v-if="mode === 'idle'" class="route-search glass">
      <div class="brand"><span>↗</span><strong>高德导航</strong><small>TMC</small></div>
      <div class="search-line"><select v-model="picking" aria-label="选点类型"><option value="destination">终点</option><option value="origin">起点</option></select>
        <input v-model="query" :aria-label="picking === 'destination' ? '搜索目的地' : '搜索起点'" placeholder="搜索地点、地址，或输入经纬度" maxlength="100" @keydown.enter="!$event.isComposing && search()" />
        <button :disabled="!mapReady || busy || searching || !query.trim()" @click="search">{{ searching ? '搜索中' : '搜索' }}</button><button :disabled="!mapReady || busy" @click="locate(false)">定位</button></div>
      <p v-if="searchMessage" class="search-message" role="status">{{ searchMessage }}</p>
      <div v-if="tips.length" class="search-tips" aria-label="地点搜索结果"><button v-for="tip in tips" :key="tip.id" @click="selectPlace(tip)"><strong>{{ tip.name }}</strong><small>{{ tip.address }}</small></button></div>
    </header>
    <div ref="topPanel" v-else-if="next" class="turn-card glass" aria-live="polite"><NavigationTurnIcon class="turn-arrow" :arrow="next.arrow" /><div><small>{{ mode === 'demo' ? '模拟导航' : '实时导航' }}</small><h2>{{ formatDistance(next.distance) }}后{{ next.text }}</h2><p>{{ next.road }}</p></div></div>
    <aside v-if="mode !== 'idle' && serviceAreas.length" class="service-area-card glass" aria-label="前方服务区">
      <strong>前方服务区</strong>
      <div v-for="area in serviceAreas" :key="area.key" class="service-area-item"><span>{{ area.name }}</span><b>{{ serviceAreaDistance(area) }}</b></div>
      <small>位置按路线区间估算，请留意道路标志</small>
    </aside>
    <div class="map-controls">
      <button class="dimension-mode" :class="{ active: use3D }" :disabled="!hasOrigin && !hasDestination" :aria-label="use3D ? '切换为 2D 地图' : '切换为 3D 地图'" :aria-pressed="use3D" @click="toggle3D">{{ use3D ? '3D' : '2D' }}</button>
      <button title="地图图层"  aria-label="地图图层" :aria-expanded="layerMenu" @click="layerMenu = !layerMenu">▱</button>
      <button class="view-mode" :class="{ active: overviewActive || following }" :disabled="!mapReady" :title="`${viewModeLabel} · 点击${!overviewActive && !following ? '恢复跟随' : '切换为' + nextViewModeLabel}`" :aria-label="`视角：${viewModeLabel}，点击${!overviewActive && !following ? '恢复跟随' : '切换为' + nextViewModeLabel}`" @click="cycleViewMode">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <template v-if="overviewActive"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><path d="m8 16 3-8 5 8"/><circle cx="11" cy="8" r="1"/></template>
          <template v-else-if="orientation === 'heading'"><path d="m12 3 8 17-8-4-8 4Z" fill="currentColor" stroke="none"/></template>
          <template v-else><circle cx="12" cy="12" r="9"/><path d="M9 16V8l6 8V8"/></template>
        </svg>
      </button>
      <button aria-label="放大" @click="overviewActive = false; overviewGeneration++; following = false; map?.zoomIn()">＋</button>
      <button aria-label="缩小" @click="overviewActive = false; overviewGeneration++; following = false; map?.zoomOut()">−</button>
    </div>
    <div v-if="layerMenu" class="layer-menu glass" role="group" aria-label="地图图层设置">
      <strong>地图图层</strong>
      <div v-if="!show3D" class="map-themes"><button :class="{ active: mapAppearance.theme === 'day' }" @click="mapAppearance.theme = 'day'">日间</button><button :class="{ active: mapAppearance.theme === 'night' }" @click="mapAppearance.theme = 'night'">夜间</button></div>
      <template v-if="!show3D">
        <label><input type="checkbox" v-model="mapAppearance.surfaces" />地块与水域</label>
        <label><input type="checkbox" v-model="mapAppearance.roads" />道路</label>
        <label><input type="checkbox" v-model="mapAppearance.labels" />道路名称</label>
        <label><input type="checkbox" v-model="mapAppearance.places" />省市名称</label>
        <label><input type="checkbox" v-model="mapAppearance.transit" />公共交通标注</label>
      </template>
      <label><input type="checkbox" v-model="trafficEnabled" />导航线路路况</label>
      <div v-if="trafficEnabled" class="traffic-legend"><span><i class="traffic-clear"></i>引导线</span><span><i class="traffic-slow"></i>缓行</span><span><i class="traffic-jam"></i>拥堵</span></div>
      <small v-if="trafficEnabled && trafficStatus" class="traffic-message">{{ trafficStatus }}</small>
    </div>
    <footer ref="footerPanel" class="navigation-footer glass">
      <p v-if="show3D ? map3DStatus : mapStatus" class="map-notice">{{ show3D ? map3DStatus : mapStatus }} <button v-if="!mapStatus.startsWith('路线总览') && !mapStatus.startsWith('正在加载')" @click="show3D ? map3D?.retry() : appMap?.retry()">重试</button></p>
      <p v-if="trafficEnabled && trafficStatus && trafficStatus !== '此区域暂无实时路况' && trafficStatus !== '放大地图后显示实时路况'" class="traffic-warning" role="status">路况：{{ trafficStatus }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="navigationEngine !== 'browser'" class="status" role="status">{{ navigationEngineNotice }}</p>
      <template v-if="mode === 'idle'">
        <div class="destination-line"><span><i class="start-dot"></i>{{ originName }} <b>→</b> <i class="end-dot"></i>{{ destinationName }}</span><button class="primary" :disabled="busy || !mapReady || !hasOrigin || !hasDestination" @click="plan()">{{ busy ? '规划中…' : '规划路线' }}</button></div>
        <div v-if="routes.length" class="route-options"><button v-for="(route, index) in routes" :key="route.id" :class="{ selected: selected === index }" @click="choose(index)"><strong class="route-duration">{{ formatRouteDuration(route.duration) }}</strong><span class="route-cost">{{ formatDistance(route.distance) }} · {{ formatRouteTolls(route) }}</span><small>{{ route.labels.join(' · ') || `方案 ${index + 1}` }}</small></button></div>
        <p v-if="!muted && (localSpeechState.loading || localSpeechState.error)" class="status">语音：{{ localSpeechState.error || localSpeechState.status }}</p>
        <div class="footer-line"><span class="status">{{ status }}</span><template v-if="current && !arrived"><button :disabled="busy" @click="startDemo">模拟导航</button><button class="primary" :disabled="busy" @click="locate(true)">开始导航</button></template></div>
      </template>
      <div v-else class="footer-line"><button @click="endNavigation()">退出导航</button><div class="trip"><strong>剩余 {{ formatDistance(remaining) }}</strong><small>{{ status }}<template v-if="liveSpeed !== null"> · {{ Math.round(liveSpeed) }} km/h</template></small></div><button v-if="mode === 'live'" :disabled="busy || !lastGpsPoint" :aria-expanded="roadSwitchOpen" @click="roadSwitchOpen = !roadSwitchOpen">切换道路</button><button @click="toggleVoice()">{{ muted ? '开启语音' : '关闭语音' }}</button></div>
      <div v-if="mode === 'live' && roadSwitchOpen" class="road-switch" role="group" aria-label="道路切换">
        <span>当前位置纠偏</span>
        <button :disabled="busy" @click="switchParallelRoad('main')">主路</button><button :disabled="busy" @click="switchParallelRoad('side')">辅路</button>
        <button :disabled="busy" @click="switchParallelRoad('elevated')">高架</button><button :disabled="busy" @click="switchParallelRoad('ground')">地面</button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.road-switch{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}.road-switch span{font-size:12px;color:#5c746c;margin-right:4px}.navigation-app .road-switch button{min-width:64px;min-height:42px;background:#e4f8ef;border-color:#b6e7d6;color:#087b5d;font-weight:600}
.layer-menu{position:absolute;z-index:600;right:64px;top:20px;padding:14px;display:grid;gap:12px;min-width:180px}.layer-menu label{display:flex;gap:9px;align-items:center}.map-themes{display:flex;gap:8px}.map-themes .active{background:#e4f8ef;border-color:#19b88b}.navigation-app{position:relative;width:100%;height:100%;min-height:360px;overflow:hidden;background:#e7ece8;color:#203a39}.navigation-map{position:absolute;inset:0;z-index:0}.route-search,.turn-card,.navigation-footer,.map-controls{z-index:500}.glass{background:rgba(255,255,255,.94);backdrop-filter:blur(18px);box-shadow:0 6px 24px #183c3420;border:1px solid #ffffffc9;border-radius:18px}.route-search{position:absolute;top:14px;left:16px;width:min(430px,calc(100% - 90px));padding:12px 16px}.brand{display:flex;align-items:center;gap:10px;margin-bottom:9px}.brand>span{display:grid;place-items:center;background:#10ac82;color:white;border-radius:10px;width:29px;height:29px;font-size:25px}.brand small{color:#80918d;letter-spacing:2px}.search-line{display:flex;gap:8px}.search-line input{width:0;flex:1;border:0;background:transparent;outline:none;color:inherit}.search-line select{border:0;background:transparent;color:#6b817b}.search-tips{max-height:220px;overflow:auto}.search-tips button{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid #e8edea;border-radius:0}.search-tips small{color:#87928f}.navigation-app button{min-height:38px;padding:7px 14px;border:1px solid #dbe6e0;border-radius:11px;background:white;color:#33504b;cursor:pointer;white-space:nowrap}.navigation-app button:disabled{opacity:.55;cursor:wait}.navigation-app .primary{background:#0eaa80;color:white;border-color:#0eaa80;font-weight:600}.map-controls{position:absolute;right:14px;top:20px;display:flex;flex-direction:column;gap:8px}.map-controls button{width:40px;height:40px;padding:0;font-size:23px;box-shadow:0 3px 10px #25453518}.navigation-footer{position:absolute;left:16px;right:16px;bottom:14px;padding:12px 16px}.destination-line,.footer-line{display:flex;align-items:center;gap:12px}.destination-line>span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.destination-line b{margin:0 10px;color:#899e96}.start-dot,.end-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;background:#14b88d}.end-dot{background:#f58d66}.footer-line{margin-top:8px}.status{flex:1;color:#73877f;font-size:12px}.route-options{display:flex;gap:8px;margin:10px 0;overflow:auto}.route-options button{flex:1;display:flex;align-items:center;justify-content:space-between;gap:8px}.route-options small{color:#7d8e85;font-size:11px}.route-options .selected{background:#e4f8ef;border-color:#19b88b;color:#078161}.turn-card{position:absolute;left:16px;top:14px;display:flex;align-items:center;gap:18px;max-width:calc(100% - 90px);padding:16px 24px;background:#123f38f2;color:white}.turn-arrow{width:56px;height:64px;flex-shrink:0;display:block}.turn-card h2{font-size:23px;margin:5px 0}.turn-card p{margin:0;opacity:.8}.turn-card small{color:#85dfbd}.trip{flex:1;display:flex;flex-direction:column;gap:4px}.trip small{color:#69827a;font-size:12px}.map-loading{pointer-events:none;position:absolute;inset:0;display:grid;place-items:center}.error{color:#b64d38;font-size:13px;margin:0 0 8px}@media(max-width:700px){.route-search{top:10px;left:10px;padding:10px}.navigation-footer{left:10px;right:10px;bottom:10px;padding:10px}.turn-card{padding:12px;gap:10px}.turn-card h2{font-size:19px}.status{font-size:11px}.navigation-app button{padding:7px 10px}.route-options button{flex-direction:column;gap:3px}.footer-line{gap:7px}}
</style>
<style>.amap-vehicle{width:36px;height:36px;display:grid;place-items:center;border:3px solid white;border-radius:50%;background:#078cda;color:white;font-size:24px;box-shadow:0 2px 12px #06365466}</style>

<style>
.navigation-map.leaflet-container{background:#142b32}.map-day .navigation-map.leaflet-container{background:#e8eced}.map-day .app-road-label{color:#485759;text-shadow:0 1px 3px white,1px 0 3px white}.app-road-label{color:#e1eeed;text-align:center;white-space:nowrap;font-size:11px;text-shadow:0 1px 3px #142b32,1px 0 3px #142b32;pointer-events:none}.map-notice{position:absolute;bottom:calc(100% + 8px);left:0;max-width:100%;font-size:12px;color:#e1eeed;background:#142b32e6;border-radius:9px;padding:5px 9px;margin:0}.navigation-app .map-notice button{min-height:24px;padding:2px 8px;margin-left:6px;font-size:12px}
</style>
<style>.app-transit-label{text-align:center;white-space:nowrap;font-size:11px;color:#62b7ff;text-shadow:0 1px 2px #142b32}.map-day .app-transit-label{color:#347ec3;text-shadow:0 1px 2px white}.app-transit-label span{border-bottom:2px solid currentColor}</style>

<style>
.app-place-label{pointer-events:none;text-align:center;white-space:nowrap;line-height:24px;font-size:12px;font-weight:600;color:#eaf4f2;text-shadow:0 0 3px #142b32,0 1px 3px #142b32,1px 0 2px #142b32}
.app-place-province{font-size:13px;letter-spacing:.5px;font-weight:500;color:#b7cecc}
.map-day .app-place-label{color:#34444e;text-shadow:0 0 3px white,0 1px 3px white,1px 0 2px white}
.map-day .app-place-province{color:#657475}
</style>

<style scoped>
.service-area-card{position:absolute;z-index:500;left:16px;bottom:102px;width:min(330px,calc(100% - 90px));padding:11px 15px;display:grid;gap:6px;background:#123f38ed;color:white}.service-area-card>strong{font-size:13px;color:#85dfbd}.service-area-item{display:flex;justify-content:space-between;gap:12px;align-items:baseline;font-size:14px}.service-area-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.service-area-item b{flex-shrink:0;font-size:12px;font-weight:600}.service-area-card small{font-size:10px;color:#c2d7d0}@media(max-width:700px){.service-area-card{left:10px;bottom:82px;width:min(300px,calc(100% - 74px));padding:8px 11px}}
.map-controls .dimension-mode{font-size:15px;font-weight:700}
.map-controls .view-mode{display:grid;place-items:center}
.map-controls .view-mode svg{width:24px;height:24px}
.map-controls .active{background:#e4f8ef;border-color:#19b88b;color:#078161}
.traffic-legend{display:flex;gap:10px;font-size:11px;white-space:nowrap}.traffic-legend span{display:flex;align-items:center;gap:4px}.traffic-legend i{display:inline-block;width:15px;height:4px;border-radius:3px}.traffic-clear{background:#1688ef}.traffic-slow{background:#f5a623}.traffic-jam{background:#e44650}.traffic-message{max-width:205px;line-height:1.35;color:#a7523e}
.traffic-warning{margin:0 0 7px;font-size:12px;color:#a7523e}
</style>

<style scoped>
.search-message{margin:10px 0 0;font-size:12px;color:#80634c}
.search-tips button{display:flex;flex-direction:column;gap:5px;white-space:normal;line-height:1.4;padding:12px 8px}
.search-tips button:hover{background:#e4f8ef}.search-tips strong{font-weight:500}
.search-tips{overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#b2cec5 transparent}
</style>


<style scoped>
.route-options button{flex-direction:column;align-items:flex-start;justify-content:center;gap:5px;min-width:160px;text-align:left;padding:10px 12px}
.route-options .route-duration{font-size:19px;line-height:1.25;font-variant-numeric:tabular-nums}
.route-options .route-cost{font-size:12px;color:inherit;opacity:.85}
.route-options small{white-space:normal}
</style>
