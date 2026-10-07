<script setup lang="ts">
import { navigationEngine, navigationEngineNotice } from '@/functions/navigationEngine';
import { createRouteFusion, type FusionPosition } from './amapRouteFusion';
import { navigationViewport } from './amapNavigationViewport';
import { remainingRouteSections } from './amapRemainingRoute';
import { remainingCongestionPath, type CongestionRun } from './amapRouteTraffic';
import { findParallelRoute, type RoadKind } from './amapParallelRoad';
import { computed, nextTick, watch, watchEffect, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref } from 'vue';
import axios from 'axios';
import { publishBackgroundNavigation, clearBackgroundNavigation } from '@/stores/backgroundNavigation';
const viewActive = ref(true);
import { navigationVoicePhrase } from './amapVoicePhrases';
import { turnVoiceDistances } from './amapTurnVoice';
import { upcomingServiceAreas, shouldAnnounceServiceArea, type UpcomingServiceArea } from './amapServiceAreas';
import { advanceDemoProgress, demoCruiseSpeed } from './amapSimulation';
import NavigationTurnIcon from '@/components/NavigationTurnIcon.vue';
import { createLivePositionGate } from './amapLivePosition';
import AmapNavigation3D from './AmapNavigation3D.vue';
import TmcLoginDialog from './TmcLoginDialog.vue';
import AmapJunctionPreview from './AmapJunctionPreview.vue';
import AmapLaneGuide from './AmapLaneGuide.vue';
import { upcomingLaneGuide } from './amapLaneGuidance';

import { prepareLocalSpeech, preloadLocalSpeech, cancelLocalSpeechPreload, speakLocal, stopLocalSpeech, localSpeechState } from '@/functions/localSpeech';
import { useGeoLocationStore, type GeoLocation } from '@/stores/geoLocation';
const geoLocation = useGeoLocationStore();
import L from 'leaflet';
import 'leaflet-rotate';
import { bearingBetween, movementHeading, smoothHeading } from './amapHeading';
import { placeNavigationPoint, type Place } from './amapSearch';
import { clearBrowserFavoritePlaces, loadBrowserFavoritePlaces } from './amapFavoritePlaces';
import { searchWebPlaces } from './amapWebSearch';
import { attachAppMap, type AppMapAppearance } from './amapVectorMap';
const mapStatus = ref('');
const tmcLoginVisible = ref(false);
let resumePlanAfterTmcLogin = false;
function updateMapStatus(message: string, dimension: '2d' | '3d') {
  if (dimension === '2d') mapStatus.value = message;
  else map3DStatus.value = message;
  if (message.startsWith('TMC 登录已失效')) tmcLoginVisible.value = true;
}
const trafficEnabled = ref(true);
const trafficUpdatedAt = ref(0);
const liveSpeed = ref<number | null>(null);
const speedEstimated = ref(false);
const speedFixTrusted = ref(false);
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
function resumeAfterTmcLogin() {
  tmcLoginVisible.value = false;
  void refreshFavoritePlaces();
  appMap?.retry();
  map3D.value?.retry();
  if (resumePlanAfterTmcLogin) {
    resumePlanAfterTmcLogin = false;
    void plan();
  }
}
function retryActiveMap() {
  const message = show3D.value ? map3DStatus.value : mapStatus.value;
  if (message.startsWith('TMC 登录已失效')) { tmcLoginVisible.value = true; return; }
  if (show3D.value) map3D.value?.retry();
  else appMap?.retry();
}
import 'leaflet/dist/leaflet.css';
import { browserNavigationPoint } from '@/functions/navigationCoordinates';
import { formatRouteDuration, formatRouteTolls } from './amapRouteSummary';
import { createPositionTransition } from './amapPositionTransition';
import { cumulative, instruction, matchPosition, meters, pointAt, type AppRoute, type Point } from './amapNavigation';
import { createTrafficSignalReminder, greenWaveSpeedWindow, mergeTrafficSignalLights, recentTrafficSignalFix, trustedTrafficSignalFix, upcomingRouteTrafficLight, upcomingTrafficSignal, type LiveTrafficLight } from './amapTrafficSignals';
import { cameraEventAhead, createSpeedLimitSectionEvents, createSpeedReminder, speedWarningLevel, upcomingSpeedLimit, upcomingSpeedSign, type SpeedLimitSection, type SpeedSignPoint } from './amapSpeedLimit';
import { cameraAssetReady, cameraSign, mapSignUrl, routeCameraSigns, trafficLightAssetReady, trafficLightSign, type MapSign, type TrafficLightColor } from './amapMapSigns';
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
const routeToken = ref('');
const liveLights = ref<LiveTrafficLight[]>([]), liveUpdatedAt = ref(0), signalClock = ref(Date.now());
const signalFixTrusted = ref(false), signalFixAt = ref(0);
const signalHoldPosition = ref<Point | null>(null), signalHoldProgress = ref(0), signalHoldHeading = ref(0);
const signalLastTrustedSpeed = ref<number | null>(null);
let signalTimer: ReturnType<typeof setInterval> | undefined;
let signalBusy = false, signalLastRequest = 0, signalGeneration = 0;
let signalAbort: AbortController | undefined;
const signalReminder = createTrafficSignalReminder();
let signalVoiceAttempt: object | undefined;
let navigationVoiceRequests = 0;
function setSignalFixTrust(trusted: boolean, discard = false) {
  if (trusted) {
    signalFixTrusted.value = true;
    signalFixAt.value = Date.now();
    signalHoldPosition.value = location.value ?? null;
    signalHoldProgress.value = progress.value;
    signalHoldHeading.value = heading.value || 0;
    signalLastTrustedSpeed.value = liveSpeed.value;
    return;
  }
  signalFixTrusted.value = false;
  if (discard) {
    signalGeneration++;
    signalAbort?.abort(); signalAbort = undefined;
    liveLights.value = []; liveUpdatedAt.value = 0; signalFixAt.value = 0;
    signalHoldPosition.value = null; signalHoldProgress.value = 0; signalLastTrustedSpeed.value = null;
    signalLastRequest = 0;
  }
}
const signalStationary = computed(() => signalLastTrustedSpeed.value !== null
  && signalLastTrustedSpeed.value <= 5 && (liveSpeed.value === null || liveSpeed.value <= 5));
const upcomingSignal = computed(() => mode.value !== 'idle' && current.value
  && recentTrafficSignalFix(signalFixAt.value, signalClock.value, signalStationary.value)
  ? upcomingTrafficSignal(current.value, signalFixTrusted.value ? progress.value : signalHoldProgress.value,
    liveLights.value, liveUpdatedAt.value, signalClock.value) : null);
const nextRouteLight = computed(() => mode.value !== 'idle' && current.value
  ? upcomingRouteTrafficLight(current.value, progress.value) : null);
const signalLabel = computed(() => upcomingSignal.value?.color === 'red' ? '红灯'
  : upcomingSignal.value?.color === 'green' ? '绿灯' : '黄灯');
const signalAwaitingUpdate = computed(() => !!upcomingSignal.value
  && signalClock.value - upcomingSignal.value.observedAt > 20_000);
const greenWave = computed(() => signalAwaitingUpdate.value ? null
  : greenWaveSpeedWindow(upcomingSignal.value, signalClock.value, liveSpeed.value));
function announceNearGreen() {
  const cue = signalReminder.update(upcomingSignal.value, signalClock.value);
  if (!cue || muted.value || signalVoiceAttempt || navigationVoiceRequests || localSpeechState.speaking) return;
  const attempt = {}, generation = signalGeneration;
  signalVoiceAttempt = attempt;
  // Give active turn speech priority, but do not suppress every signal at a
  // junction. Check the phase again after synthesis and only consume playback.
  void speakLocal(cue.text, Math.max(0, cue.expiresAt - Date.now()), () => {
    if (muted.value || mode.value === 'idle' || generation !== signalGeneration || navigationVoiceRequests) return false;
    signalClock.value = Date.now();
    const active = signalReminder.update(upcomingSignal.value, signalClock.value);
    return active?.key === cue.key && active.cycle === cue.cycle && active.text === cue.text;
  }).then(started => {
    if (started && generation === signalGeneration) signalReminder.markSpoken(cue);
  }).catch(() => {}).finally(() => {
    if (signalVoiceAttempt === attempt) signalVoiceAttempt = undefined;
  });
}
async function refreshSignals() {
  const now = Date.now();
  const heldStationaryFix = signalStationary.value
    && recentTrafficSignalFix(signalFixAt.value, now, true);
  if (signalBusy || mode.value === 'idle' || !routeToken.value || !signalHoldPosition.value
      || (!heldStationaryFix && (!signalFixTrusted.value || now - signalFixAt.value > 10_000))
      || Date.now() - signalLastRequest < 12000) return;
  signalBusy = true; signalLastRequest = Date.now();
  const generation = signalGeneration;
  const controller = new AbortController();
  signalAbort = controller;
  try {
    const response = await axios.post('/api/amap-app/traffic-signals', {
      routeToken: routeToken.value, routeIndex: selected.value, position: signalHoldPosition.value,
      speed: heldStationaryFix ? 0 : liveSpeed.value === null ? 0 : liveSpeed.value / 3.6,
      heading: signalHoldHeading.value, progress: signalHoldProgress.value,
    }, { timeout: 30000, signal: controller.signal });
    if (generation !== signalGeneration || !navigationRunning()) return;
    const result = response.data?.data;
    if (response.data?.status === 'ok' && result?.state === 'ready' && Array.isArray(result.lights)) {
      liveLights.value = mergeTrafficSignalLights(liveLights.value, result.lights, result.updatedAt, Date.now());
      liveUpdatedAt.value = result.updatedAt;
      signalClock.value = Date.now(); announceNearGreen();
    }
  } catch { /* A missing live signal never blocks route guidance. */ }
  finally { if (signalAbort === controller) signalAbort = undefined; signalBusy = false; }
}
function stopSignals() {
  setSignalFixTrust(false, true);
  signalGeneration++; clearInterval(signalTimer); signalTimer = undefined;
  liveLights.value = []; liveUpdatedAt.value = 0; signalLastRequest = 0;
  signalAbort?.abort(); signalAbort = undefined;
  signalReminder.clear(); signalVoiceAttempt = undefined;
}
const searching = ref(false), searchMessage = ref('');
const query = ref(''), tips = ref<Place[]>([]), picking = ref<'origin' | 'destination'>('destination');
const favoritePlaces = ref<Place[]>([]);
const favoriteLoading = ref(false), favoriteSaving = ref(false), favoriteReady = ref(false), favoriteMessage = ref('');
function favoriteResponsePlaces(body: { status?: string; data?: { places?: Place[] }; message?: string }): Place[] {
  if (body?.status === 'need_login') {
    tmcLoginVisible.value = true;
    throw new Error('请先登录 TMC，才能使用收藏地点');
  }
  if (body?.status !== 'ok' || !Array.isArray(body.data?.places))
    throw new Error(body?.message || '读取收藏地点失败');
  return body.data.places;
}
async function refreshFavoritePlaces() {
  if (favoriteLoading.value || favoriteSaving.value) return;
  favoriteLoading.value = true;
  let serverLoaded = false;
  try {
    const response = await axios.get('/api/amap-app/favorites', { timeout: 10000 });
    let places = favoriteResponsePlaces(response.data);
    if (disposed) return;
    favoritePlaces.value = places;
    favoriteReady.value = true;
    serverLoaded = true;
    const browserFavorites = loadBrowserFavoritePlaces();
    if (browserFavorites.length) {
      const imported = await axios.post('/api/amap-app/favorites',
        { action: 'import', places: browserFavorites }, { timeout: 10000 });
      places = favoriteResponsePlaces(imported.data);
      clearBrowserFavoritePlaces();
    }
    if (disposed) return;
    favoritePlaces.value = places;
    favoriteReady.value = true;
    favoriteMessage.value = '';
  } catch (exception) {
    if (disposed) return;
    if (!serverLoaded) favoriteReady.value = false;
    favoriteMessage.value = axios.isAxiosError(exception)
      ? exception.response?.data?.message || '收藏地点加载失败，请重试'
      : exception instanceof Error ? exception.message : '收藏地点加载失败，请重试';
  } finally { favoriteLoading.value = false; }
}
const visibleFavoritePlaces = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase();
  return keyword ? favoritePlaces.value.filter(place =>
    `${place.name} ${place.address}`.toLocaleLowerCase().includes(keyword)) : favoritePlaces.value;
});
const favoriteIds = computed(() => new Set(favoritePlaces.value.map(place => place.id)));
async function togglePlaceFavorite(place: Place) {
  if (!favoriteReady.value || favoriteLoading.value || favoriteSaving.value) return;
  favoriteSaving.value = true;
  let updated = false;
  try {
    const response = await axios.post('/api/amap-app/favorites', favoriteIds.value.has(place.id)
      ? { action: 'remove', id: place.id } : { action: 'add', place }, { timeout: 10000 });
    favoritePlaces.value = favoriteResponsePlaces(response.data);
    favoriteMessage.value = '';
    updated = true;
  } catch (exception) {
    favoriteMessage.value = axios.isAxiosError(exception)
      ? exception.response?.data?.message || '收藏未保存，请重试点击星标'
      : exception instanceof Error ? exception.message : '收藏未保存，请重试点击星标';
  } finally {
    favoriteSaving.value = false;
    if (updated && loadBrowserFavoritePlaces().length) void refreshFavoritePlaces();
  }
}
const pointPicker = ref<HTMLElement>(), pointMenuOpen = ref(false);
function choosePointType(type: 'origin' | 'destination') {
  picking.value = type;
  pointMenuOpen.value = false;
}
function closePointMenuOnOutsideClick(event: PointerEvent) {
  if (!pointPicker.value?.contains(event.target as Node)) pointMenuOpen.value = false;
}
const origin = ref<Point>([0, 0]), destination = ref<Point>([0, 0]);
const hasOrigin = ref(false), hasDestination = ref(false);
const originName = ref('等待车辆定位'), destinationName = ref('请选择目的地');
const mode = ref<'idle' | 'live' | 'demo'>('idle'), progress = ref(0), guidanceProgress = ref<number>(), following = ref(true), muted = ref(false);
function navigationRunning() { return mode.value !== 'idle'; }
const navigationFixValid = ref(false);
watch(following, value => appMap?.setFollowing(value), { flush: 'sync' });
const status = ref('点击地图选择终点；先定位可使用当前位置作为起点'), location = ref<Point>(), arrived = ref(false);
const roadSwitchOpen = ref(false);
const lastGpsPoint = ref<Point>();
const current = computed(() => routes.value[selected.value]);
const visibleLane = computed(() => mode.value !== 'idle' && !overviewActive.value
  ? upcomingLaneGuide(current.value?.laneGuides, progress.value) : undefined);
const speedLimitSection = ref<SpeedLimitSection>();
const speedLimitEvents = createSpeedLimitSectionEvents();
let speedLimitClearTimer: ReturnType<typeof setTimeout> | undefined;
function clearSpeedLimitTimer() {
  if (speedLimitClearTimer !== undefined) clearTimeout(speedLimitClearTimer);
  speedLimitClearTimer = undefined;
}
function applySpeedLimitEvent(event: { type: 452; speed: number; section?: SpeedLimitSection }) {
  clearSpeedLimitTimer();
  if (event.speed > 0) { speedLimitSection.value = event.section; return; }
  // The APK delays a zero-speed event briefly to avoid flicker at a boundary.
  speedLimitClearTimer = setTimeout(() => { speedLimitSection.value = undefined; speedLimitClearTimer = undefined; }, 250);
}
function clearSpeedGuidance() {
  clearSpeedLimitTimer();
  speedLimitEvents.reset();
  speedLimitSection.value = undefined;
  speedCamera.value = undefined;
  speedReminder.reset();
}
const nextSpeedLimit = computed(() => mode.value !== 'idle' ? upcomingSpeedLimit(current.value?.speedLimits, progress.value) : undefined);
const speedSigns = ref<SpeedSignPoint[]>([]);
const nextSpeedSign = computed(() => mode.value !== 'idle' ? upcomingSpeedSign(speedSigns.value, progress.value) : undefined);
let speedSignRequest = 0;
async function refreshNavigationEvents() {
  const request = ++speedSignRequest;
  speedSigns.value = [];
  if (mode.value === 'idle' || !routeToken.value || !current.value) return;
  const token = routeToken.value, index = selected.value;
  try {
    const response = await axios.post('/api/amap-app/navigation-events', { routeToken: token, routeIndex: index }, { timeout: 35000 });
    if (disposed || request !== speedSignRequest || !navigationRunning() || token !== routeToken.value || index !== selected.value) return;
    const data = response.data?.data;
    if (response.data?.status === 'ok' && data?.state === 'ready'
        && Array.isArray(data.speedSigns) && Array.isArray(data.speedLimits) && Array.isArray(data.speedCameras)) {
      routes.value[index].speedLimits = data.speedLimits;
      routes.value[index].speedCameras = data.speedCameras;
      routes.value[index].laneGuides = Array.isArray(data.laneGuides) ? data.laneGuides : [];
      speedSigns.value = data.speedSigns;
      drawMapSigns();
    }
  } catch { /* The signed route still works when optional sign data is unavailable. */ }
}
const speedCamera = ref<{ at: number; limit: number; distance: number; type: number }>();
function applySpeedCameraEvent(event: ReturnType<typeof cameraEventAhead>) {
  const camera = event.naviCamera[0];
  const speeds = camera?.speed.filter(value => Number.isInteger(value) && value >= 5 && value <= 160 && value !== 255);
  speedCamera.value = camera && speeds?.length
    ? { at: Math.round((progress.value + camera.distance) * 100) / 100, limit: Math.max(...speeds), distance: camera.distance, type: camera.type }
    : undefined;
}
const speedLimit = computed(() => speedLimitSection.value?.limit);
const warningLevel = computed(() => mode.value === 'live' && !speedEstimated.value
  ? speedWarningLevel(liveSpeed.value, speedLimit.value) : 0);
const overSpeed = computed(() => warningLevel.value > 0);
const severeOverSpeed = computed(() => warningLevel.value === 2 && speedFixTrusted.value);
const speedReminder = createSpeedReminder();
const announcedSpeedLimits = new Set<NonNullable<typeof nextSpeedLimit.value>['section']>();
const announcedSpeedCameras = new Set<number>();
const announcedSpeedSigns = new Set<number>();
watch([mode, routeToken, selected], () => {
  clearSpeedLimitTimer();
  speedLimitEvents.reset();
  speedLimitSection.value = undefined;
  speedCamera.value = undefined;
  speedReminder.reset();
  announcedSpeedLimits.clear();
  announcedSpeedCameras.clear();
  announcedSpeedSigns.clear();
  void refreshNavigationEvents();
  stopSignals();
  if (mode.value !== 'idle' && routeToken.value) {
    signalTimer = setInterval(() => { signalClock.value = Date.now(); announceNearGreen(); void refreshSignals(); }, 1000);
    void refreshSignals();
  }
});
const congestionRuns = computed(() => current.value && trafficEnabled.value ? current.value.trafficRuns || [] : []);
const navigationCongestionRuns = computed(() => congestionRuns.value);
const trafficUpdatedLabel = computed(() => trafficUpdatedAt.value
  ? new Date(trafficUpdatedAt.value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '规划时');
watch(trafficEnabled, () => draw(false));
let routeTrafficTimer: ReturnType<typeof setInterval> | undefined;
let routeTrafficRequest = 0;
async function refreshRouteTraffic() {
  const request = ++routeTrafficRequest;
  if (mode.value === 'idle' || !trafficEnabled.value || !routeToken.value || !current.value) return;
  const token = routeToken.value, index = selected.value;
  try {
    const response = await axios.post('/api/amap-app/route-traffic',
      { routeToken: token, routeIndex: index }, { timeout: 45000 });
    if (disposed || request !== routeTrafficRequest || !navigationRunning()
        || token !== routeToken.value || index !== selected.value) return;
    const data = response.data?.data;
    if (response.data?.status === 'ok' && data?.state === 'ready' && Array.isArray(data.trafficRuns)) {
      routes.value[index].trafficRuns = data.trafficRuns;
      trafficUpdatedAt.value = data.updatedAt * 1000;
      draw(false);
    }
  } catch { /* Preserve the last verified App route state when refresh fails. */ }
}
watch([mode, routeToken, selected, trafficEnabled], ([, , , enabled], previous) => {
  routeTrafficRequest++;
  if (routeTrafficTimer) clearInterval(routeTrafficTimer);
  routeTrafficTimer = mode.value !== 'idle' && trafficEnabled.value && routeToken.value
    ? setInterval(() => void refreshRouteTraffic(), 120000) : undefined;
  if (enabled && previous?.[3] === false && routeTrafficTimer) void refreshRouteTraffic();
});
watch(routeToken, () => { trafficUpdatedAt.value = routeToken.value ? Date.now() : 0; });
const next = computed(() => current.value ? instruction(current.value,
  mode.value === 'live' ? guidanceProgress.value ?? progress.value : progress.value) : undefined);
type JunctionPicture = { state: 'ready'; width: number; height: number; roadJpeg: string; arrowPng: string };
const junctionPicture = ref<{ key: string; picture: JunctionPicture }>();
const junctionRequested = new Set<string>();
const junctionRetried = new Set<string>();
let junctionRetryTimer: ReturnType<typeof setTimeout> | undefined;
const junctionKey = computed(() => `${routeToken.value}:${selected.value}:${next.value?.key ?? -1}`);
const junctionCandidate = computed(() => {
  if (mode.value === 'idle' || !viewActive.value || !routeToken.value || !next.value || !current.value) return false;
  // The App may supply a raster junction view for turns as well as forks.
  // Ask once for each actual maneuver; a vector-only/no-picture answer stays hidden.
  return next.value.key < current.value.steps.length - 1 && next.value.text !== '继续直行';
});
const visibleJunction = computed(() => junctionCandidate.value && !overviewActive.value
  && next.value!.distance <= 450 && junctionPicture.value?.key === junctionKey.value ? junctionPicture.value.picture : undefined);
function clearJunctionRetry() {
  if (junctionRetryTimer) clearTimeout(junctionRetryTimer);
  junctionRetryTimer = undefined;
}
function retryJunctionOnce(key: string) {
  if (disposed || key !== junctionKey.value || junctionRetried.has(key)) return;
  junctionRetried.add(key);
  clearJunctionRetry();
  junctionRetryTimer = setTimeout(() => {
    junctionRetryTimer = undefined;
    if (disposed || key !== junctionKey.value) return;
    junctionRequested.delete(key);
    if (junctionCandidate.value && next.value && next.value.distance <= 700) requestJunctionImage();
  }, 20000);
}
watch(routeToken, () => {
  clearJunctionRetry(); junctionRequested.clear(); junctionRetried.clear(); junctionPicture.value = undefined;
});
watch(junctionKey, () => clearJunctionRetry());
function requestJunctionImage() {
  if (!junctionCandidate.value || !next.value || next.value.distance > 700) return;
  const key = junctionKey.value;
  if (junctionRequested.has(key)) return;
  junctionRequested.add(key);
  void axios.post('/api/amap-app/junction-image', {
    routeToken: routeToken.value, routeIndex: selected.value, stepIndex: next.value.key,
  }, { timeout: 35000 }).then(response => {
    const picture = response.data?.data as JunctionPicture | { state: 'absent' | 'unavailable' } | undefined;
    if (!disposed && key === junctionKey.value && response.data?.status === 'ok'
        && picture?.state === 'ready' && picture.roadJpeg && picture.arrowPng) {
      junctionPicture.value = { key, picture };
    } else if (response.data?.status === 'ok' && picture?.state !== 'absent') {
      retryJunctionOnce(key);
    }
  }).catch(() => retryJunctionOnce(key));
}
watch([junctionKey, junctionCandidate, () => next.value?.distance], requestJunctionImage);
const serviceAreas = computed(() => upcomingServiceAreas(current.value, progress.value));
function serviceAreaDistance(area: UpcomingServiceArea) {
  return progress.value >= area.from ? '当前路段' : `约 ${formatDistance(area.distance)}后`;
}
const remaining = computed(() => current.value ? Math.max(0, cumulative(current.value)[current.value.path.length - 1] - progress.value) : 0);
let map: L.Map, marker: L.Marker | undefined, startMarker: L.Marker | undefined, endMarker: L.Marker | undefined, lines: L.Polyline[] = [];
let lightMarkers: { point: Point; marker: L.Marker; color?: TrafficLightColor; seconds?: number }[] = [], cameraMarkers: L.Marker[] = [];
let liveLightMarker: L.Marker | undefined;
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
let controller: AbortController | undefined, disposed = false, generation = 0, locationGeneration = 0, offCount = 0, lastReplan = 0, spoken = '', lastTurnVoiceAttemptAt = 0, lastTurnVoiceAttemptKey = '';
const announcedServiceAreas = new Set<string>();
const formatDistance = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)} 公里` : `${Math.round(n / 10) * 10} 米`;
function speak(text: string, maxDelayMs = 15000, isRelevant?: () => boolean): Promise<boolean> {
  if (muted.value) return Promise.resolve(false);
  navigationVoiceRequests++;
  return speakLocal(text, maxDelayMs, isRelevant).catch(() => false)
    .finally(() => { navigationVoiceRequests--; });
}
function prepareVoice() { if (!muted.value) void prepareLocalSpeech().catch(e => { localSpeechState.error=String(e); }); }

watch([current, () => next.value?.key, mode, muted], () => {
  cancelLocalSpeechPreload();
  if (muted.value || mode.value === 'idle') return;
  const turn = next.value;
  void preloadLocalSpeech([
    ...(turn ? [navigationVoicePhrase(turn, false), navigationVoicePhrase(turn, true)] : []),
    '已到达目的地附近', '红灯即将变绿', '绿灯亮了',
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
    routes.value = data.routes; routeToken.value = data.routeToken || ''; selected.value = index;
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
  viewActive.value = false; appMap?.setActive(false); appMap?.releaseMemory(); cancelSearch();
  if (mode.value === 'idle') { resumeLocationOnActivate = trackingLocation; stop(); }
});
watch(show3D, enabled => {
  // The 3D ground has its own decoded-tile warm-up. Keep the hidden 2D layer
  // idle so both renderers do not compete for the single map helper.
  appMap?.setActive(!enabled && viewActive.value);
  appMap?.setRoute(enabled ? undefined : current.value, progress.value);
});
onActivated(async () => {
  viewActive.value = true;
  if (favoriteReady.value) void refreshFavoritePlaces();
  await nextTick();
  if (disposed || !map || !viewActive.value) return;
  map.invalidateSize({ pan: false }); appMap?.setActive(!show3D.value); endpoints(); draw(false);
  if (location.value) animatePosition(location.value, true);
  applyOrientation();
  if (resumeLocationOnActivate) { resumeLocationOnActivate = false; locate(false, true); }
});

function endpoints() {
  if (!map || !viewActive.value) return;
  if ((hasOrigin.value || hasDestination.value) && !appMap) {
    appMap = attachAppMap(map, message => updateMapStatus(message, '2d'));
    appMap.setFollowing(following.value);
  }
  startMarker?.remove(); endMarker?.remove();
  const pin = (text: string, color: string) => L.divIcon({ className: '', html: `<span style="display:block;background:${color};color:white;border:2px solid white;border-radius:50%;width:26px;height:26px;text-align:center;line-height:23px;font-size:12px">${text}</span>`, iconSize: [26,26], iconAnchor: [13,13] });
  if (hasOrigin.value) startMarker = L.marker(latLng(origin.value), { icon: pin('起', '#0ca87f') }).addTo(map);
  if (hasDestination.value) endMarker = L.marker(latLng(destination.value), { icon: pin('终', '#f38159') }).addTo(map);
}
function mapSignIcon(sign: MapSign) {
  return L.icon({ iconUrl: mapSignUrl(sign), iconSize: [sign.width, sign.height],
    iconAnchor: [sign.anchorX, sign.height], className: 'amap-map-sign' });
}
function updateLiveLightMarker() {
  if (!map) return;
  if (mode.value === 'idle' || overviewActive.value) {
    liveLightMarker?.remove(); liveLightMarker = undefined;
    return;
  }
  const signal = upcomingSignal.value;
  let matched = false;
  for (const item of lightMarkers) {
    const color = signal && meters(item.point, signal.point) <= 25 ? signal.color : undefined;
    const seconds = color ? signal?.seconds : undefined;
    if (item.color !== color || item.seconds !== seconds) {
      item.marker.setIcon(mapSignIcon(trafficLightSign(color, seconds)));
      item.color = color; item.seconds = seconds;
    }
    if (color) matched = true;
  }
  liveLightMarker?.remove(); liveLightMarker = undefined;
  if (signal && !matched) liveLightMarker = L.marker(latLng(signal.point), {
    icon: mapSignIcon(trafficLightSign(signal.color, signal.seconds)), interactive: false, zIndexOffset: 520,
  }).addTo(map);
}
function drawMapSigns() {
  if (!map || !viewActive.value) return;
  lightMarkers.forEach(item => item.marker.remove()); lightMarkers = [];
  cameraMarkers.forEach(item => item.remove()); cameraMarkers = [];
  liveLightMarker?.remove(); liveLightMarker = undefined;
  for (const point of mode.value !== 'idle' && !overviewActive.value ? current.value?.trafficLights || [] : []) {
    const marker = L.marker(latLng(point), { icon: mapSignIcon(trafficLightSign()),
      interactive: false, zIndexOffset: 500 }).addTo(map);
    lightMarkers.push({ point, marker });
  }
  for (const sign of routeCameraSigns(current.value)) {
    cameraMarkers.push(L.marker(latLng(sign.displayPoint), { icon: mapSignIcon(cameraSign(sign.type, sign.limit)),
      interactive: false, zIndexOffset: 510,
      title: `${sign.type === 25 || sign.type === 26 ? '区间' : '固定'}测速 · ${sign.limit} km/h`,
    }).addTo(map));
  }
  updateLiveLightMarker();
}
void trafficLightAssetReady.then(ready => { if (ready && !disposed) drawMapSigns(); });
void cameraAssetReady.then(ready => { if (ready && !disposed) drawMapSigns(); });
watch(() => { const signal = upcomingSignal.value; return signal ? `${signal.point.join(',')}:${signal.color}:${signal.seconds}` : ''; }, updateLiveLightMarker);
watch([mode, overviewActive], drawMapSigns);
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
  drawMapSigns();
  for (const run of congestionRuns.value) {
    const path = remainingCongestionPath(run, mode.value === 'idle' ? 0 : progress.value);
    const line = L.polyline(path.map(latLng), { color: run.status === 4 ? '#923d6d' : run.status === 3 ? '#e44650' : '#f5a623', weight: 8,
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
function clearRoute() { overviewActive.value = false; overviewGeneration++; stop(); controller?.abort(); generation++; busy.value = false; routes.value = []; routeToken.value = ''; heading.value = undefined; headingAnchor = undefined; applyOrientation(); draw(false); }
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
  setPoint(placeNavigationPoint(place), place.name);
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
    if (response.data.status === 'need_login') { resumePlanAfterTmcLogin = true; tmcLoginVisible.value = true; return; }
    const data = response.data.data;
    if (response.data.status !== 'ok' || data?.state !== 'ready' || !data.routes?.length) throw new Error(response.data.message || '这条路线暂未成功解析，请更换地点或重试');
    routes.value = data.routes; routeToken.value = data.routeToken || ''; selected.value = 0; progress.value = 0; offCount = 0; spoken = '';
    announcedServiceAreas.clear(); draw(!replan);
    status.value = replan ? '路线已重新规划' : '路线已就绪，选择方案后开始导航';
    if (replan) speak('已为您重新规划路线');
  } catch (exception) {
    if (id !== generation || disposed) return;
    error.value = axios.isAxiosError(exception) ? exception.response?.data?.message || '路线请求失败，请重试' : (exception as Error).message;
    if (replan) status.value = '偏离路线，重算失败；请稍后重试';
    else { routes.value = []; routeToken.value = ''; draw(false); }
  } finally { if (id === generation) busy.value = false; }
}
function updatePosition(point: Point, accuracy = 0, gpsHeading?: number | null, speed?: number | null, recovered = false, fusion?: FusionPosition) {
  const route = current.value;
  const navigating = !!route && mode.value !== 'idle';
  speedFixTrusted.value = mode.value === 'live' && Number.isFinite(accuracy) && accuracy <= 25 && !fusion?.estimated;
  // A low-quality raw fix must not drag the 3D car into buildings while the
  // route remains visible. Hold the last trusted map-matched position.
  if (navigating && (!Number.isFinite(accuracy) || accuracy > 60)) {
    setSignalFixTrust(false); clearSpeedGuidance();
    status.value = '定位精度不足，等待更准确的位置';
    return;
  }
  // Fusion already selected an along-route position. Rematching it globally
  // could jump to the adjoining arm of a loop ramp or an overlapping bridge.
  const match = navigating ? fusion?.progress !== undefined && fusion.state !== 'off-route'
    ? { point, progress: fusion.progress, distance: 0 }
    : matchPosition(route, point, progress.value, recovered, { heading: gpsHeading, speed, accuracy }) : undefined;
  const onRoute = match && fusion?.state !== 'off-route' && match.distance <= Math.max(40, accuracy * 1.5);
  const visualPoint = onRoute ? match.point : point;
  const firstNavigationFix = navigating && !navigationFixValid.value;
  const direction = movementHeading(headingAnchor, visualPoint, accuracy, gpsHeading, speed);
  if (direction !== undefined) { heading.value = smoothHeading(heading.value, direction); headingAnchor = visualPoint; }
  else if (!headingAnchor && accuracy <= 60) headingAnchor = visualPoint;
  location.value = visualPoint;
  if (navigating) navigationFixValid.value = true;
  if (viewActive.value) {
  if (!marker) marker = L.marker(latLng(visualPoint), { icon: L.divIcon({ className: '', html: '<div class="amap-vehicle">▲</div>', iconSize: [36,36], iconAnchor: [18,18] }), rotateWithView: true, zIndexOffset: 1000 }).addTo(map);
  else if (!map.hasLayer(marker)) marker.addTo(map);
  animatePosition(visualPoint, firstNavigationFix);
  }
  if (!route || mode.value === 'idle') { setSignalFixTrust(false); return; }
  if (!onRoute) {
    speedFixTrusted.value = false;
    clearSpeedGuidance();
    offCount++;
    setSignalFixTrust(false, fusion?.state === 'off-route' || offCount >= 3);
    status.value = '已偏离路线';
    if (mode.value === 'live' && offCount >= 3 && !busy.value && Date.now() - lastReplan > 20000) {
      lastReplan = Date.now(); origin.value = point; originName.value = '当前位置'; status.value = '正在重新规划'; void plan(true);
    }
    return;
  }
  offCount = 0; progress.value = fusion?.progress ?? (recovered ? match.progress : Math.max(progress.value, match.progress));
  const signalTrusted = mode.value === 'demo' || (mode.value === 'live' && trustedTrafficSignalFix(accuracy, fusion));
  setSignalFixTrust(signalTrusted);
  if (signalTrusted) void refreshSignals();
  const event = speedLimitEvents.update(current.value.speedLimits, progress.value);
  if (event) applySpeedLimitEvent(event);
  applySpeedCameraEvent(cameraEventAhead(current.value.speedCameras, progress.value));
  trimDrivenRoute();
  appMap?.setRoute(current.value, progress.value);
  if (recovered) spoken = '';
  status.value = mode.value === 'demo' ? '模拟导航 · 2 倍速 · 非车辆实时位置'
    : '实时导航中 · 车机定位';
  if (fusion) status.value = fusion.state === 'tracking' ? '实时导航中 · 路线融合' : fusion.state === 'recovering' ? '定位恢复 · 平滑校正中' : fusion.state === 'waiting' ? '推算已暂停 · 等待可靠定位' : `定位精度下降 · 估算位置（${fusion.estimationSeconds ?? 0} 秒）`;
  if (!fusion?.estimated && remaining.value < 25 && meters(point, current.value.path[current.value.path.length - 1]) < 40) {
    finishNavigationFollow('已到达目的地附近，继续跟随车辆'); arrived.value = true; speak('已到达目的地附近'); return;
  }
  if (fusion?.state === 'waiting') { speedFixTrusted.value = false; clearSpeedGuidance(); return; }
  const turn = next.value;
  const voiceDistances = turnVoiceDistances(liveSpeed.value);
  if (!muted.value && turn && turn.distance <= voiceDistances.ahead) {
    const near = turn.distance <= voiceDistances.near;
    const key = `${turn.key}:${near ? 'near' : 'ahead'}`;
    if (key !== spoken && (key !== lastTurnVoiceAttemptKey || Date.now() - lastTurnVoiceAttemptAt >= 1500)) {
      spoken = key; lastTurnVoiceAttemptAt = Date.now(); lastTurnVoiceAttemptKey = key;
      const activeRoute = current.value;
      void speak(navigationVoicePhrase(turn, near), 4000, () =>
        mode.value !== 'idle' && current.value === activeRoute && next.value?.key === turn.key
        && next.value.distance > 8 && (near
          ? next.value.distance <= voiceDistances.near + 30 : next.value.distance > voiceDistances.near)
      ).then(started => { if (!started && spoken === key) spoken = ''; });
    }
  }
  // Secondary alerts must not replace a turn instruction while approaching a junction.
  const canAnnounceOther = !turn || turn.distance > Math.max(450, voiceDistances.ahead);
  const reliableSpeed = !fusion?.estimated && accuracy <= 25
    && (turn?.distance ?? Infinity) > 100 ? liveSpeed.value : null;
  if (canAnnounceOther && mode.value !== 'demo' && speedReminder.update(speedLimitSection.value, reliableSpeed, Date.now())) {
    void speak(`当前道路限速${speedLimit.value}公里，您已超速，请减速慢行`);
  } else if (canAnnounceOther && reliableSpeed !== null
      && speedCamera.value && speedCamera.value.distance <= 200
      && !announcedSpeedCameras.has(speedCamera.value.at)) {
    announcedSpeedCameras.add(speedCamera.value.at);
    void speak(`前方${speedCamera.value.type === 25 || speedCamera.value.type === 26 ? '区间测速' : '测速'}限速${speedCamera.value.limit}公里，请留意道路标志`);
  } else if (canAnnounceOther && reliableSpeed !== null
      && !speedCamera.value && nextSpeedSign.value && nextSpeedSign.value.distance <= 200
      && !announcedSpeedSigns.has(nextSpeedSign.value.sign.at)) {
    announcedSpeedSigns.add(nextSpeedSign.value.sign.at);
    void speak(`前方限速标志${nextSpeedSign.value.sign.limit}公里，请留意道路标志`);
  } else if (canAnnounceOther && reliableSpeed !== null
      && !speedCamera.value
      && nextSpeedLimit.value && nextSpeedLimit.value.distance <= 200
      && nextSpeedLimit.value.section.limit !== speedLimit.value
      && !announcedSpeedLimits.has(nextSpeedLimit.value.section)) {
    announcedSpeedLimits.add(nextSpeedLimit.value.section);
    void speak(`前方限速${nextSpeedLimit.value.section.limit}公里，请留意道路标志`);
  }
  const area = serviceAreas.value[0];
  if (!muted.value && canAnnounceOther && area && !announcedServiceAreas.has(area.key) &&
      shouldAnnounceServiceArea(area, progress.value, turn?.distance ?? Infinity)) {
    announcedServiceAreas.add(area.key);
    void speak(`前方有${area.name}，请留意入口`);
  }
}
function toggleVoice() { muted.value = !muted.value; if (muted.value) stopLocalSpeech(); else { spoken = ''; prepareVoice(); } }
let routeFusion: ReturnType<typeof createRouteFusion> | undefined;
let fusionTimer: ReturnType<typeof setInterval> | undefined;
function renderFusion(result?: FusionPosition) {
  if (!result || disposed || mode.value !== 'live') return;
  liveSpeed.value = result.speed * 3.6;
  speedEstimated.value = !!result.estimated;
  guidanceProgress.value = result.guidanceProgress;
  updatePosition(result.point, 0, result.heading, result.speed, result.state === 'off-route', result);
}
function stopFusion() { clearInterval(fusionTimer); fusionTimer = undefined; routeFusion = undefined; guidanceProgress.value = undefined; }
function startFusion() {
  stopFusion();
  if (navigationEngine.value !== 'route-fusion' || mode.value !== 'live' || !current.value) return;
  routeFusion = createRouteFusion(current.value);
  fusionTimer = setInterval(() => renderFusion(routeFusion?.tick(performance.now())), 250);
}
watch(current, () => {
  if (mode.value === 'live') { navigationFixValid.value = false; marker?.remove(); }
  startFusion();
});
let trackingLocation = false, resumeLocationOnActivate = false;
watch(navigationEngine, () => startFusion());
function stop(keepLocation = false) {
  routeTrafficRequest++;
  if (routeTrafficTimer) clearInterval(routeTrafficTimer);
  routeTrafficTimer = undefined;
  clearSpeedLimitTimer();
  speedLimitEvents.reset();
  speedLimitSection.value = undefined;
  speedCamera.value = undefined;
  speedReminder.reset();
  announcedSpeedLimits.clear();
  announcedSpeedCameras.clear();
  announcedSpeedSigns.clear();
  speedSignRequest++;
  speedSigns.value = [];
  stopSignals();
  stopFusion();
  roadSwitchOpen.value = false;
  announcedServiceAreas.clear();
  cancelLocalSpeechPreload();
  if (!keepLocation) {
    trackingLocation = false;
    locationGeneration++;
    if (positionWatch !== undefined) navigator.geolocation?.clearWatch(positionWatch);
    positionWatch = undefined; liveSpeed.value = null; speedEstimated.value = false;
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
  const initialSpeed = demoCruiseSpeed(current.value.speedLimits, 0);
  liveSpeed.value = initialSpeed; speedEstimated.value = false;
  map.setZoom(navigationViewport(liveSpeed.value).zoom); draw(false);
  updatePosition(current.value.path[0], 0, heading.value, initialSpeed / 3.6);
  let lastTick = performance.now();
  simulation = setInterval(() => {
    const route = current.value;
    if (!route) return;
    const now = performance.now();
    const travel = advanceDemoProgress(route.speedLimits, progress.value, now - lastTick);
    lastTick = now;
    liveSpeed.value = travel.speedKmh;
    const point = pointAt(route, travel.progress);
    updatePosition(point, 0, bearingBetween(point, pointAt(route, travel.progress + 25)), travel.speedKmh / 3.6);
  }, 250);
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
    navigationFixValid.value = false; marker?.remove();
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
    speedEstimated.value = false;
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
function move3DMapCenter(point: Point) {
  if (map && !following.value) map.setView(latLng(point), map.getZoom(), { animate: false });
}
function zoomMap(steps: number) {
  overviewActive.value = false; overviewGeneration++;
  if (show3D.value) map3D.value?.zoomBy(steps);
  else { following.value = false; if (steps > 0) map?.zoomIn(); else map?.zoomOut(); }
}
function beginMapTouch(event: TouchEvent) {
  if (event.touches.length === 2) pauseMapFollowing();
}
onMounted(() => {
  document.addEventListener('pointerdown', closePointMenuOnOutsideClick);
  void refreshFavoritePlaces();
  if (!mapElement.value) return;
  mapElement.value.addEventListener('touchstart', beginMapTouch, { passive: true, capture: true });
  map = L.map(mapElement.value, { rotate: true, rotateControl: false, touchRotate: true, shiftKeyRotate: false, zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 18, zoomSnap: .25 }).setView([20, 0], 3);
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
onBeforeUnmount(() => { document.removeEventListener('pointerdown', closePointMenuOnOutsideClick); clearJunctionRetry(); cancelPositionAnimation(); clearBackgroundNavigation(); mapElement.value?.removeEventListener('touchstart', beginMapTouch, true); disposed = true; generation++; cancelSearch(); controller?.abort(); stop(); resizeObserver?.disconnect(); appMap?.dispose(); map?.remove(); });
</script>

<template>
  <section class="navigation-app" :class="{ 'map-day': mapAppearance.theme === 'day' }">
    <div ref="mapElement" class="navigation-map" aria-label="高德导航地图"></div>
    <AmapNavigation3D v-if="show3D && viewActive" ref="map3D" :center="mapCenter" :position="mode === 'live' && !navigationFixValid ? undefined : displayedPosition || location" :heading="displayedHeading" :bearing="orientation === 'heading' ? displayedHeading : 0" :zoom="mapZoom" :route="current" :progress="progress" :traffic-runs="navigationCongestionRuns" :cameras="current?.speedCameras" :signal="upcomingSignal" :navigating="mode !== 'idle'" :following="following" :heading-up="mode !== 'idle' && orientation === 'heading'" :theme="mapAppearance.theme" @status="updateMapStatus($event, '3d')" @failed="fail3D" @pick="mode === 'idle' && !busy && setPoint($event, '地图选点')" @interaction="pauseMapFollowing" @viewcenter="move3DMapCenter" />
    <div v-if="severeOverSpeed" class="overspeed-halo" aria-hidden="true">
      <span class="overspeed-halo-side overspeed-halo-left"></span>
      <span class="overspeed-halo-side overspeed-halo-right"></span>
      <span class="overspeed-halo-beam overspeed-halo-beam-left"></span>
      <span class="overspeed-halo-beam overspeed-halo-beam-right"></span>
      <svg class="overspeed-halo-top" viewBox="0 0 800 200" preserveAspectRatio="none"><image href="/amap/overspeed/images/red-left.png" width="200" height="800" transform="translate(800 0) rotate(90)" /></svg>
      <svg class="overspeed-halo-bottom" viewBox="0 0 800 200" preserveAspectRatio="none"><image href="/amap/overspeed/images/red-left.png" width="200" height="800" transform="translate(800 0) rotate(90)" /></svg>
    </div>
    <TmcLoginDialog :open="tmcLoginVisible && viewActive" @close="tmcLoginVisible = false" @logged-in="resumeAfterTmcLogin" />
    <div v-if="!mapReady"  class="map-loading">{{ error || '正在加载地图…' }}</div>
    <header ref="topPanel" v-if="mode === 'idle'" class="route-search glass" aria-label="路线搜索">
      <div class="search-line"><div ref="pointPicker" class="point-picker" @keydown.esc="pointMenuOpen = false">
          <button type="button" class="point-picker-trigger" aria-label="选择起点或终点" :aria-expanded="pointMenuOpen" @click="pointMenuOpen = !pointMenuOpen">
            <span class="point-picker-dot" :class="picking"></span>{{ picking === 'destination' ? '终点' : '起点' }}<span class="point-picker-chevron" :class="{ open: pointMenuOpen }" aria-hidden="true"></span>
          </button>
          <div v-if="pointMenuOpen" class="point-picker-menu" role="group" aria-label="选点类型">
            <button type="button" class="point-picker-option" :class="{ selected: picking === 'destination' }" @click="choosePointType('destination')"><span class="point-picker-dot destination"></span>终点</button>
            <button type="button" class="point-picker-option" :class="{ selected: picking === 'origin' }" @click="choosePointType('origin')"><span class="point-picker-dot origin"></span>起点</button>
          </div>
        </div>
        <input v-model="query" :aria-label="picking === 'destination' ? '搜索目的地' : '搜索起点'" placeholder="搜索地点、地址，或输入经纬度" maxlength="100" @keydown.enter="!$event.isComposing && search()" />
        <button :disabled="!mapReady || busy || searching || !query.trim()" @click="search">{{ searching ? '搜索中' : '搜索' }}</button><button :disabled="!mapReady || busy" @click="locate(false)">定位</button></div>
      <p v-if="searchMessage" class="search-message" role="status">{{ searchMessage }}</p>
      <p v-if="favoriteLoading && !favoriteReady" class="favorite-status" role="status">正在加载收藏地点…</p>
      <div v-if="favoriteMessage" class="favorite-status" role="status"><span>{{ favoriteMessage }}</span><button type="button" :disabled="favoriteLoading || favoriteSaving" @click="refreshFavoritePlaces">重试</button></div>
      <section v-if="visibleFavoritePlaces.length" class="place-section" aria-label="收藏地点">
        <h3>收藏地点</h3>
        <div class="place-list favorite-list"><div v-for="place in visibleFavoritePlaces" :key="place.id" class="place-row">
          <button type="button" class="place-select" @click="selectPlace(place)"><strong>{{ place.name }}</strong><small>{{ place.address || '已收藏地点' }}</small></button>
          <button type="button" class="favorite-toggle saved" :disabled="favoriteLoading || favoriteSaving || !favoriteReady" :aria-label="`取消收藏 ${place.name}`" :title="`取消收藏 ${place.name}`" aria-pressed="true" @click="togglePlaceFavorite(place)">★</button>
        </div></div>
      </section>
      <section v-if="tips.length" class="place-section" aria-label="地点搜索结果">
        <h3>搜索结果</h3>
        <div class="place-list search-tips"><div v-for="tip in tips" :key="tip.id" class="place-row">
          <button type="button" class="place-select" @click="selectPlace(tip)"><strong>{{ tip.name }}</strong><small>{{ tip.address }}</small></button>
          <button type="button" class="favorite-toggle" :class="{ saved: favoriteIds.has(tip.id) }" :disabled="favoriteLoading || favoriteSaving || !favoriteReady" :aria-label="`${favoriteIds.has(tip.id) ? '取消收藏' : '收藏'} ${tip.name}`" :title="`${favoriteIds.has(tip.id) ? '取消收藏' : '收藏'} ${tip.name}`" :aria-pressed="favoriteIds.has(tip.id)" @click="togglePlaceFavorite(tip)">{{ favoriteIds.has(tip.id) ? '★' : '☆' }}</button>
        </div></div>
      </section>
    </header>
    <div v-else ref="topPanel" class="navigation-guidance">
      <div v-if="next" class="turn-card glass" :class="{ 'has-junction': visibleJunction, 'has-lanes': visibleLane }" aria-live="polite">
        <div class="turn-summary"><NavigationTurnIcon class="turn-arrow" :arrow="next.arrow" /><div><small>{{ mode === 'demo' ? '模拟导航' : '实时导航' }}</small><h2>{{ formatDistance(next.distance) }}后{{ next.text }}</h2><p>{{ next.road }}</p></div></div>
        <AmapLaneGuide v-if="visibleLane" :guide="visibleLane" />
        <AmapJunctionPreview v-if="visibleJunction" :road-jpeg="visibleJunction.roadJpeg" :arrow-png="visibleJunction.arrowPng" :width="visibleJunction.width" :height="visibleJunction.height" />
      </div>
      <div v-if="!overviewActive && (upcomingSignal || nextRouteLight)" class="signal-card glass" role="status">
        <span class="signal-icon" :class="upcomingSignal?.color" aria-hidden="true"><span class="signal-lamp red"></span><span class="signal-lamp yellow"></span><span class="signal-lamp green"></span></span><div><strong>{{ upcomingSignal ? `${signalLabel} ${upcomingSignal.seconds} 秒${signalAwaitingUpdate ? ' · 待更新' : ''}` : '前方红绿灯' }}</strong><small>前方 {{ Math.round(upcomingSignal?.distance ?? nextRouteLight!.distance) }} 米</small><small v-if="greenWave" class="green-wave">{{ greenWave.atCurrentSpeed ? '按当前车速预计绿灯通过' : `绿波参考 ${greenWave.min}–${greenWave.max} km/h` }} · 遵守道路限速</small></div>
      </div>
    </div>
    <div v-if="mode !== 'idle' && (liveSpeed !== null || speedLimit !== undefined || speedCamera || nextSpeedSign || nextSpeedLimit)" class="speed-badges" :aria-label="speedLimit === undefined ? '当前车速' : '当前车速与道路限速'">
      <div v-if="liveSpeed !== null" class="speed-current" :class="{ 'speed-over': overSpeed, 'speed-severe': severeOverSpeed }" :aria-label="severeOverSpeed ? `严重超速，当前 ${Math.round(liveSpeed)} 公里每小时` : undefined"><strong>{{ Math.round(liveSpeed) }}</strong><small>{{ mode === 'demo' ? '模拟 km/h' : speedEstimated ? '估 km/h' : 'km/h' }}</small></div>
      <div v-if="speedLimit !== undefined" class="speed-road"><strong>{{ speedLimit }}</strong><small>限速</small></div>
      <div v-if="speedCamera" class="speed-ahead glass">前方{{ speedCamera.type === 25 || speedCamera.type === 26 ? '区间测速' : '测速' }} {{ formatDistance(speedCamera.distance) }} <b>{{ speedCamera.limit }}</b> km/h</div>
      <div v-else-if="nextSpeedSign" class="speed-ahead glass">前方限速标志 {{ formatDistance(nextSpeedSign.distance) }} <b>{{ nextSpeedSign.sign.limit }}</b> km/h</div>
      <div v-else-if="nextSpeedLimit" class="speed-ahead glass">前方 {{ formatDistance(nextSpeedLimit.distance) }} <b>{{ nextSpeedLimit.section.limit }}</b> km/h</div>
    </div>
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
          <template v-if="overviewActive"><path d="M6 18c5 0 2-10 11-11"/><circle cx="6" cy="18" r="2" fill="currentColor" stroke="none"/><circle cx="18" cy="6" r="2.5"/></template>
          <template v-else-if="orientation === 'heading'"><path d="m12 3 8 17-8-4-8 4Z" fill="currentColor" stroke="none"/></template>
          <template v-else><circle cx="12" cy="12" r="9"/><path d="M9 16V8l6 8V8"/></template>
        </svg>
      </button>
      <button aria-label="放大" @click="zoomMap(1)">＋</button>
      <button aria-label="缩小" @click="zoomMap(-1)">−</button>
    </div>
    <div v-if="layerMenu" class="layer-menu glass" role="group" aria-label="地图图层设置">
      <strong>地图图层</strong>
      <div class="map-themes"><button :class="{ active: mapAppearance.theme === 'day' }" @click="mapAppearance.theme = 'day'">日间</button><button :class="{ active: mapAppearance.theme === 'night' }" @click="mapAppearance.theme = 'night'">夜间</button></div>
      <template v-if="!show3D">
        <label><input type="checkbox" v-model="mapAppearance.surfaces" />地块与水域</label>
        <label><input type="checkbox" v-model="mapAppearance.roads" />道路</label>
        <label><input type="checkbox" v-model="mapAppearance.labels" />道路名称</label>
        <label><input type="checkbox" v-model="mapAppearance.places" />省市名称</label>
        <label><input type="checkbox" v-model="mapAppearance.transit" />公共交通标注</label>
      </template>
      <label><input type="checkbox" v-model="trafficEnabled" />导航线路路况</label>
      <div v-if="trafficEnabled" class="traffic-legend"><span><i class="traffic-clear"></i>引导线</span><span><i class="traffic-slow"></i>缓行</span><span><i class="traffic-jam"></i>拥堵</span><span><i class="traffic-severe"></i>严重拥堵</span></div>
      <small v-if="trafficEnabled && current" class="traffic-message">高德 App 路线数据 · {{ trafficUpdatedLabel }}更新</small>
    </div>
    <footer ref="footerPanel" class="navigation-footer glass">
      <p v-if="show3D ? map3DStatus : mapStatus" class="map-notice">{{ show3D ? map3DStatus : mapStatus }} <button v-if="!(show3D ? map3DStatus : mapStatus).startsWith('路线总览') && !(show3D ? map3DStatus : mapStatus).startsWith('正在加载')" @click="retryActiveMap">{{ (show3D ? map3DStatus : mapStatus).startsWith('TMC 登录已失效') ? '登录 TMC' : '重试' }}</button></p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="navigationEngine !== 'browser'" class="status" role="status">{{ navigationEngineNotice }}</p>
      <template v-if="mode === 'idle'">
        <div class="destination-line"><span><i class="start-dot"></i>{{ originName }} <b>→</b> <i class="end-dot"></i>{{ destinationName }}</span><button class="primary" :disabled="busy || !mapReady || !hasOrigin || !hasDestination" @click="plan()">{{ busy ? '规划中…' : '规划路线' }}</button></div>
        <div v-if="routes.length" class="route-options"><button v-for="(route, index) in routes" :key="route.id" :class="{ selected: selected === index }" @click="choose(index)"><strong class="route-duration">{{ formatRouteDuration(route.duration) }}</strong><small v-if="route.trafficLightCount !== undefined" class="route-lights">红绿灯 {{ route.trafficLightCount }} 处</small><span class="route-cost">{{ formatDistance(route.distance) }} · {{ formatRouteTolls(route) }}</span><small class="route-label">{{ route.labels.join(' · ') || `方案 ${index + 1}` }}</small></button></div>
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
.navigation-guidance{position:absolute;z-index:501;top:14px;left:16px;width:calc(100% - 90px);display:flex;align-items:flex-start;gap:8px}
@media(max-width:700px){.navigation-guidance{top:10px;left:10px;width:calc(100% - 76px)}}
.layer-menu{position:absolute;z-index:600;right:64px;top:20px;padding:14px;display:grid;gap:12px;min-width:180px}.layer-menu label{display:flex;gap:9px;align-items:center}.map-themes{display:flex;gap:8px}.map-themes .active{background:#e4f8ef;border-color:#19b88b}.navigation-app{position:relative;width:100%;height:100%;min-height:360px;overflow:hidden;background:#e7ece8;color:#203a39}.navigation-map{position:absolute;inset:0;z-index:0}.route-search,.turn-card,.navigation-footer,.map-controls{z-index:500}.glass{background:rgba(255,255,255,.94);backdrop-filter:blur(18px);box-shadow:0 6px 24px #183c3420;border:1px solid #ffffffc9;border-radius:18px}.route-search{position:absolute;top:14px;left:16px;width:min(430px,calc(100% - 90px));padding:12px 16px}.search-line{display:flex;gap:8px}.search-line input{width:0;flex:1;border:0;background:transparent;outline:none;color:inherit}.search-line select{border:0;background:transparent;color:#6b817b}.search-tips{max-height:220px;overflow:auto}.search-tips button{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid #e8edea;border-radius:0}.search-tips small{color:#87928f}.navigation-app button{min-height:38px;padding:7px 14px;border:1px solid #dbe6e0;border-radius:11px;background:white;color:#33504b;cursor:pointer;white-space:nowrap}.navigation-app button:disabled{opacity:.55;cursor:wait}.navigation-app .primary{background:#0eaa80;color:white;border-color:#0eaa80;font-weight:600}.map-controls{position:absolute;right:14px;top:20px;display:flex;flex-direction:column;gap:8px}.map-controls button{width:40px;height:40px;padding:0;font-size:23px;box-shadow:0 3px 10px #25453518}.navigation-footer{position:absolute;left:16px;right:16px;bottom:14px;padding:12px 16px}.destination-line,.footer-line{display:flex;align-items:center;gap:12px}.destination-line>span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.destination-line b{margin:0 10px;color:#899e96}.start-dot,.end-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;background:#14b88d}.end-dot{background:#f58d66}.footer-line{margin-top:8px}.status{flex:1;color:#73877f;font-size:12px}.route-options{display:flex;gap:8px;margin:10px 0;overflow:auto}.route-options button{flex:1;display:flex;align-items:center;justify-content:space-between;gap:8px}.route-options small{color:#7d8e85;font-size:11px}.route-options .selected{background:#e4f8ef;border-color:#19b88b;color:#078161}.turn-card{position:absolute;left:16px;top:14px;display:flex;align-items:center;gap:14px;max-width:calc(100% - 90px);padding:14px 20px;background:#123f38f2;color:white}.turn-arrow{width:50px;height:58px;flex-shrink:0;display:block}.turn-card h2{font-size:21px;margin:4px 0}.turn-card p{margin:0;opacity:.8}.turn-card small{color:#85dfbd}.trip{flex:1;display:flex;flex-direction:column;gap:4px}.trip small{color:#69827a;font-size:12px}.map-loading{pointer-events:none;position:absolute;inset:0;display:grid;place-items:center}.error{color:#b64d38;font-size:13px;margin:0 0 8px}@media(max-width:700px){.route-search{top:10px;left:10px;padding:10px}.navigation-footer{left:10px;right:10px;bottom:10px;padding:10px}.turn-card{padding:10px;gap:9px}.turn-card h2{font-size:18px}.status{font-size:11px}.navigation-app button{padding:7px 10px}.route-options button{flex-direction:column;gap:3px}.footer-line{gap:7px}}
.search-line{align-items:center;min-width:0}.point-picker{position:relative;flex:none}.navigation-app .point-picker-trigger{display:flex;align-items:center;gap:5px;min-height:36px;padding:5px 8px;border:1px solid #cee7dc;border-radius:10px;background:#eef8f2;color:#176b4e;font-size:13px;font-weight:700;box-shadow:none}.point-picker-dot{width:8px;height:8px;flex:none;border-radius:50%}.point-picker-dot.destination{background:#f18662}.point-picker-dot.origin{background:#13b987}.point-picker-chevron{width:6px;height:6px;margin:-3px 1px 0 2px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(45deg);transition:transform .16s}.point-picker-chevron.open{margin-top:3px;transform:rotate(225deg)}
.point-picker-menu{position:absolute;z-index:20;top:calc(100% + 6px);left:0;display:grid;gap:2px;min-width:112px;padding:5px;border:1px solid #dcebe3;border-radius:12px;background:#fff;box-shadow:0 10px 30px #183c3426}.navigation-app .point-picker-option{display:flex;align-items:center;gap:8px;width:100%;min-height:36px;padding:6px 10px;border:0;border-radius:8px;background:transparent;color:#39534b;text-align:left;font-size:13px}.navigation-app .point-picker-option:hover,.navigation-app .point-picker-option.selected{background:#e5f7ed;color:#087e55}.navigation-app .point-picker-trigger:focus-visible,.navigation-app .point-picker-option:focus-visible{outline:2px solid #0d9f75;outline-offset:2px}
@media(max-width:520px){.search-line{display:grid;grid-template-columns:72px minmax(0,1fr);gap:6px}.search-line input{min-width:0;width:100%;box-sizing:border-box}.search-line>button{width:100%;min-width:0}}
.route-options button{flex:1 0 180px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 8px;text-align:left;align-items:center}.route-options .route-lights{justify-self:end}.route-options .route-cost,.route-options .route-label{grid-column:1/-1;overflow:hidden;text-overflow:ellipsis;max-width:100%;white-space:nowrap}
.signal-card{display:flex;flex:0 1 235px;align-items:center;gap:12px;padding:10px 14px;color:#213c36;max-width:100%;box-sizing:border-box;min-width:0}.signal-card>div{min-width:0}.signal-card strong{display:block;font-size:19px;font-variant-numeric:tabular-nums}.signal-card small{display:block;color:#6f837b;font-size:12px}.signal-icon{width:24px;height:38px;box-sizing:border-box;display:flex;flex:none;flex-direction:column;align-items:center;justify-content:space-evenly;padding:3px 0;border:2px solid #b7c8d5;border-radius:12px;background:#293443;box-shadow:0 1px 4px #172a3150}.signal-lamp{width:8px;height:8px;border-radius:50%;background:#626d76;box-shadow:inset 0 1px 2px #111a27}.signal-icon.red .signal-lamp.red{background:#ff4a51;box-shadow:0 0 7px #ff4a51,inset 0 1px 2px #ffffff88}.signal-icon.yellow .signal-lamp.yellow{background:#ffd243;box-shadow:0 0 7px #ffd243,inset 0 1px 2px #ffffff88}.signal-icon.green .signal-lamp.green{background:#37db75;box-shadow:0 0 7px #37db75,inset 0 1px 2px #ffffff88}
.signal-card .green-wave{margin-top:5px;color:#087f5b;font-weight:600}
</style>
<style>.amap-vehicle{width:36px;height:36px;display:grid;place-items:center;border:3px solid white;border-radius:50%;background:#078cda;color:white;font-size:24px;box-shadow:0 2px 12px #06365466}</style>

<style>
.navigation-map.leaflet-container{background:#142b32}.map-day .navigation-map.leaflet-container{background:#e8eced}.map-day .app-road-label{color:#485759;text-shadow:0 1px 3px white,1px 0 3px white}.app-road-label{color:#e1eeed;text-align:center;white-space:nowrap;font-size:11px;text-shadow:0 1px 3px #142b32,1px 0 3px #142b32;pointer-events:none}.map-notice{position:absolute;bottom:calc(100% + 8px);right:0;max-width:min(360px,45%);font-size:12px;color:#e1eeed;background:#142b32e6;border-radius:9px;padding:5px 9px;margin:0;overflow-wrap:anywhere}.navigation-app .map-notice button{min-height:24px;padding:2px 8px;margin-left:6px;font-size:12px}
</style>
<style>.app-transit-label{text-align:center;white-space:nowrap;font-size:11px;color:#62b7ff;text-shadow:0 1px 2px #142b32}.map-day .app-transit-label{color:#347ec3;text-shadow:0 1px 2px white}.app-transit-label span{border-bottom:2px solid currentColor}</style>

<style>
.app-place-label{pointer-events:none;text-align:center;white-space:nowrap;line-height:24px;font-size:12px;font-weight:600;color:#eaf4f2;text-shadow:0 0 3px #142b32,0 1px 3px #142b32,1px 0 2px #142b32}
.app-place-province{font-size:13px;letter-spacing:.5px;font-weight:500;color:#b7cecc}
.map-day .app-place-label{color:#34444e;text-shadow:0 0 3px white,0 1px 3px white,1px 0 2px white}
.map-day .app-place-province{color:#657475}
</style>

<style scoped>
.turn-card .turn-summary{display:flex;align-items:center;gap:10px;min-width:0}
.turn-card .turn-summary>div{min-width:0}
.navigation-guidance .turn-card{position:relative;left:auto;top:auto;flex:0 1 auto;min-width:0;max-width:min(300px,100%);box-sizing:border-box;padding:10px 14px;border-radius:14px}
.turn-card .turn-arrow{width:36px;height:44px}
.turn-card h2{font-size:18px;line-height:1.25;margin:3px 0;overflow-wrap:anywhere}
.turn-card p{font-size:12px;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.turn-card small{font-size:10px;line-height:1.2}
.navigation-guidance .turn-card.has-junction,.navigation-guidance .turn-card.has-lanes{display:block;width:min(280px,100%);max-width:100%;padding:0;overflow:hidden}
.turn-card.has-junction .turn-summary,.turn-card.has-lanes .turn-summary{min-height:62px;padding:8px 10px;box-sizing:border-box}
.turn-card.has-junction .turn-summary small,.turn-card.has-lanes .turn-summary small{display:none}
.turn-card.has-junction .turn-arrow,.turn-card.has-lanes .turn-arrow{width:30px;height:38px}
.turn-card.has-junction h2,.turn-card.has-lanes h2{font-size:17px;margin:0 0 3px}
.turn-card :deep(.lane-guide){box-sizing:border-box;padding:5px 8px 6px}
.turn-card :deep(.lane-guide small){font-size:10px;margin-bottom:1px}
.turn-card :deep(.lane-arrow){max-width:42px;height:44px}
@media(max-width:700px){.turn-card .turn-summary{gap:8px}.navigation-guidance .turn-card{padding:9px 11px;max-width:min(280px,100%)}.navigation-guidance .turn-card.has-junction,.navigation-guidance .turn-card.has-lanes{width:min(260px,100%);padding:0}.turn-card.has-junction .turn-summary,.turn-card.has-lanes .turn-summary{padding:7px 9px;min-height:58px}}
@media(max-width:520px){.navigation-guidance{gap:6px}.navigation-guidance .turn-card{padding:8px 10px}.turn-card .turn-summary{gap:6px}.turn-card .turn-arrow{width:30px;height:38px}.turn-card h2,.turn-card.has-junction h2,.turn-card.has-lanes h2{font-size:16px}.navigation-guidance .turn-card.has-junction,.navigation-guidance .turn-card.has-lanes{width:min(240px,100%);padding:0}.turn-card.has-junction .turn-summary,.turn-card.has-lanes .turn-summary{padding:7px 8px}.turn-card :deep(.lane-arrow){height:40px}.signal-card{flex-basis:145px;gap:6px;padding:8px}.signal-card strong{font-size:14px}.signal-card small{font-size:10px}}
.service-area-card{position:absolute;z-index:500;left:16px;bottom:102px;width:min(330px,calc(100% - 90px));padding:11px 15px;display:grid;gap:6px;background:#123f38ed;color:white}.service-area-card>strong{font-size:13px;color:#85dfbd}.service-area-item{display:flex;justify-content:space-between;gap:12px;align-items:baseline;font-size:14px}.service-area-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.service-area-item b{flex-shrink:0;font-size:12px;font-weight:600}.service-area-card small{font-size:10px;color:#c2d7d0}@media(max-width:700px){.service-area-card{left:10px;bottom:82px;width:min(300px,calc(100% - 74px));padding:8px 11px}}
.map-controls .dimension-mode{font-size:15px;font-weight:700}
.map-controls .view-mode{display:grid;place-items:center}
.map-controls .view-mode svg{width:24px;height:24px}
.map-controls .active{background:#e4f8ef;border-color:#19b88b;color:#078161}
.traffic-legend{display:flex;gap:10px;font-size:11px;white-space:nowrap;flex-wrap:wrap}.traffic-legend span{display:flex;align-items:center;gap:4px}.traffic-legend i{display:inline-block;width:15px;height:4px;border-radius:3px}.traffic-clear{background:#1688ef}.traffic-slow{background:#f5a623}.traffic-jam{background:#e44650}.traffic-severe{background:#923d6d}.traffic-message{max-width:205px;line-height:1.35;color:#607b87}
.speed-badges{position:absolute;z-index:502;left:16px;bottom:110px;display:flex;align-items:flex-end;gap:8px;pointer-events:none}.speed-current,.speed-road{display:flex;flex-direction:column;align-items:center;justify-content:center;font-variant-numeric:tabular-nums;border-radius:50%;background:#fff;box-shadow:0 4px 16px #172e3a35}.speed-current{width:68px;height:68px;color:#354c58;border:5px solid #e5edf0}.speed-current.speed-over{color:#e33436;border-color:#ee3438}.speed-current strong{font-size:28px;line-height:1}.speed-current small{font-size:10px}.speed-road{width:50px;height:50px;border:4px solid #ee3438;color:#1f2b30}.speed-road strong{font-size:21px;line-height:1}.speed-road small{font-size:9px}@media(max-width:700px){.speed-badges{left:10px;bottom:90px}.speed-current{width:58px;height:58px}.speed-current strong{font-size:23px}.speed-road{width:44px;height:44px}.speed-road strong{font-size:18px}}
.speed-ahead{padding:7px 10px;font-size:12px;color:#253b40;white-space:nowrap}.speed-ahead b{display:inline-grid;place-items:center;border:2px solid #ee3438;border-radius:50%;width:29px;height:29px;font-size:14px;margin:0 3px}
.speed-badges ~ .service-area-card{bottom:195px}@media(max-width:700px){.speed-badges ~ .service-area-card{bottom:165px}}
.overspeed-halo{position:absolute;inset:0;z-index:480;overflow:hidden;pointer-events:none}
.overspeed-halo-side,.overspeed-halo-beam{position:absolute;top:0;bottom:0;left:0;width:clamp(42px,8.2vh,96px);background-size:100% 100%;background-repeat:no-repeat}
.overspeed-halo-side{background-image:url('/amap/overspeed/images/red-left.png');animation:overspeed-source-pulse 2s ease-in-out infinite}
.overspeed-halo-right,.overspeed-halo-beam-right{left:auto;right:0;scale:-1 1}
.overspeed-halo-beam{bottom:auto;height:85%;background-image:url('/amap/overspeed/images/beam1.png');transform-origin:top;animation:overspeed-source-beam 2s ease-in-out infinite}
.overspeed-halo-top,.overspeed-halo-bottom{position:absolute;left:0;width:100%;height:clamp(48px,10vw,120px);animation:overspeed-source-pulse 2s ease-in-out infinite}
.overspeed-halo-top{top:0}.overspeed-halo-bottom{bottom:0;scale:1 -1}
.speed-current.speed-severe{color:#fff;background:#cb202d;border-color:#ff7780;box-shadow:0 0 0 5px #ff25344d,0 0 24px 9px #ff253473;animation:overspeed-speed-pulse 2s ease-in-out infinite}
@keyframes overspeed-source-pulse{0%,50%,100%{opacity:0}25%{opacity:1}}
@keyframes overspeed-source-beam{0%,49%{opacity:0;transform:translateY(-35%) scaleY(0)}62%{opacity:1;transform:translateY(-18%) scaleY(.55)}85%{opacity:1;transform:translateY(18%) scaleY(1)}100%{opacity:0;transform:translateY(35%) scaleY(1)}}
@keyframes overspeed-speed-pulse{0%,100%{box-shadow:0 0 0 3px #ff253440,0 0 13px 3px #ff253455}25%,75%{box-shadow:0 0 0 8px #ff253466,0 0 28px 11px #ff253499}}
@media(prefers-reduced-motion:reduce){.overspeed-halo-side,.overspeed-halo-top,.overspeed-halo-bottom,.speed-current.speed-severe{animation:none}.overspeed-halo-side,.overspeed-halo-top,.overspeed-halo-bottom{opacity:.65}.overspeed-halo-beam{display:none}}
</style>

<style scoped>
.search-message{margin:10px 0 0;font-size:12px;color:#80634c}
.favorite-status{display:flex;align-items:center;gap:8px;margin:8px 0 0;color:#80634c;font-size:12px}.favorite-status span{min-width:0;flex:1}.navigation-app .favorite-status button{min-height:28px;padding:3px 9px;font-size:12px}
.search-tips button{display:flex;flex-direction:column;gap:5px;white-space:normal;line-height:1.4;padding:12px 8px}
.search-tips button:hover{background:#e4f8ef}.search-tips strong{font-weight:500}
.search-tips{overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#b2cec5 transparent}
.place-section{margin-top:9px}.place-section h3{margin:0 0 4px;color:#59796e;font-size:12px;font-weight:700}.place-list{max-height:min(22vh,180px);overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#b2cec5 transparent}.place-row{display:flex;align-items:center;border-bottom:1px solid #e8edea}.place-row:last-child{border-bottom:0}.navigation-app .place-list .place-select{flex:1;min-width:0;width:0;display:flex;flex-direction:column;align-items:flex-start;gap:3px;min-height:48px;padding:7px 8px;border:0;border-radius:8px;background:transparent;line-height:1.4;text-align:left}.place-select strong,.place-select small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.place-select strong{font-weight:600}.place-select small{color:#7d9088;font-size:11px}.navigation-app .place-list .place-select:hover{background:#e4f8ef}.navigation-app .place-list .favorite-toggle{flex:none;display:grid;place-items:center;width:42px;min-width:42px;min-height:42px;padding:0;border:0;border-radius:10px;background:transparent;color:#79948a;font-size:25px;line-height:1;white-space:nowrap}.navigation-app .place-list .favorite-toggle:hover{background:#eef8f2}.navigation-app .place-list .favorite-toggle.saved{color:#e1a627}
</style>


<style scoped>
.route-options button{flex-direction:column;align-items:flex-start;justify-content:center;gap:5px;min-width:160px;text-align:left;padding:10px 12px}
.route-options .route-duration{font-size:19px;line-height:1.25;font-variant-numeric:tabular-nums}
.route-options .route-cost{font-size:12px;color:inherit;opacity:.85}
.route-options small{white-space:normal}
</style>
