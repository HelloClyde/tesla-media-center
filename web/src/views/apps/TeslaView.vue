<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { configureStreetSun, applyStreetLighting, VEHICLE_SUN_DIRECTION } from './teslaSceneLighting';
import { captureStreetReflections } from './teslaReflections';
import { createVehicleWipers } from './teslaWipers';
import { createOfficialDoorController, isOfficialVehicle, loadVehicleModel, prepareOfficialVehicle } from './teslaOfficialModel';
import { createVehicleWeather, applyWeatherLighting } from './teslaWeather';
import { fetchVehicleWeather, weatherLabels, type SceneWeather } from './teslaWeatherData';
import TeslaWeatherIcon from './TeslaWeatherIcon.vue';
import { Sky } from 'three/examples/jsm/objects/Sky.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { del, get, post } from '@/functions/requests';
import getAMap from '@/functions/amapConfig';
import { repairVehicleInterior } from './teslaInterior';
import { createVehicleLights } from './teslaLights';
import { createVehicleStreet } from './teslaStreet';
import { createVehicleRoadMesh, ROAD_TEXTURE_LENGTH } from './teslaRoad';
import { GPS_SPEED_MAX_AGE_MS, visualTravelSpeedMps, wheelAngularSpeed } from './teslaMotion';
import { createGpsSpeedTracker, speedFromLiveGpsFix } from './teslaGpsSpeed';
import { useGeoLocationStore, type GeoLocation } from '@/stores/geoLocation';
import { APPEARANCE_KEY, paintFinishes, defaultAppearance, normalizeAppearance, createVehicleAppearance } from './teslaAppearance';

function savedAppearance() {
  try { return normalizeAppearance(JSON.parse(localStorage.getItem(APPEARANCE_KEY) || 'null')); }
  catch { return { ...defaultAppearance }; }
}
const appearance = reactive(savedAppearance());
const appearanceOpen = ref(false);
const appearanceSaveError = ref(false);
let vehicleAppearance: ReturnType<typeof createVehicleAppearance> | undefined;
watch(appearance, () => {
  vehicleAppearance?.update(appearance);
  try { localStorage.setItem(APPEARANCE_KEY, JSON.stringify(normalizeAppearance(appearance))); appearanceSaveError.value=false; }
  catch { appearanceSaveError.value=true; }
});

const pageRef = ref<HTMLElement | null>(null);
const vehicleVisualRef = ref<HTMLElement | null>(null);
const mapContainer = ref<HTMLElement | null>(null);
const rawTableWrapRef = ref<HTMLElement | null>(null);
const rawTableRef = ref<any>(null);

let mapInstance: any = null;
let teslaPageDisposed = false;
let trackMapGeneration = 0;
let trackMapLoading = false;
let polylines: any[] = [];
let vehicleMarker: any = null;
let trackRenderVersion = 0;
let autoSyncTimer: number | null = null;
let pageObserver: IntersectionObserver | null = null;
let gAMap: any = null;
let lastForcedSyncAt = 0;
let tabPollInFlight = false;
let pendingTabRefreshOptions: { allowForceSync?: boolean; immediate?: boolean; includeMeta?: boolean } | null = null;
let vehicleScene: THREE.Scene | null = null;
let streetReflectionsReady = false;
let streetReflectionsDirty = true;
let vehicleEnvironment: THREE.WebGLRenderTarget | null = null;
let vehicleSky: Sky | null = null;
let vehicleLights: ReturnType<typeof createVehicleLights> | undefined;
const weatherMode=ref<SceneWeather|'auto'>('auto');
try { const saved=localStorage.getItem('tmc.tesla.weather');if(saved==='auto'||saved&&saved in weatherLabels)weatherMode.value=saved as SceneWeather|'auto'; } catch {}
const weatherMenuOpen = ref(false);
const weatherChoices: { value: SceneWeather | 'auto'; label: string }[] = [
  { value: 'auto', label: '自动' },
  ...Object.entries(weatherLabels).map(([value, label]) => ({ value: value as SceneWeather, label })),
];
function chooseWeather(value: SceneWeather | 'auto') {
  weatherMode.value = value;
  weatherMenuOpen.value = false;
}
const automaticWeather=ref<SceneWeather>('clear');
const weatherStatus=ref('等待车辆位置');
const activeWeather=computed(()=>weatherMode.value==='auto'?automaticWeather.value:weatherMode.value);
const weatherAvailable=computed(()=>weatherMode.value!=='auto'||weatherStatus.value.startsWith('当地天气 · '));
const weatherDisplayLabel=computed(()=>weatherAvailable.value ? weatherLabels[activeWeather.value] : weatherStatus.value==='正在获取天气' ? '获取中' : '暂无天气');
let vehicleWipers: ReturnType<typeof createVehicleWipers> | undefined;
let wipersMoving = false;
let vehicleWeather:ReturnType<typeof createVehicleWeather>|undefined;
let weatherTimer:number|undefined,weatherRequest:AbortController|undefined;
async function refreshWeather(){
  weatherRequest?.abort();
  if(weatherMode.value!=='auto'||!state.documentVisible||!state.pageExposed||state.activeTab!=='status')return;
  const lat=state.latestSample?.latitude,lon=state.latestSample?.longitude;
  if(lat==null||lon==null){weatherStatus.value='等待车辆位置';return;}
  const request=new AbortController();weatherRequest=request;
  const timeout=window.setTimeout(()=>request.abort(),10000);
  weatherStatus.value='正在获取天气';
  try { const value=await fetchVehicleWeather(Number(lat),Number(lon),request.signal);
    if(weatherRequest!==request||weatherMode.value!=='auto')return;
    automaticWeather.value=value;weatherStatus.value='当地天气 · '+weatherLabels[value];
  } catch {if(weatherRequest===request)weatherStatus.value='天气获取失败，可手动选择';}
  finally {window.clearTimeout(timeout);}
}
const headlights = ref(false);
watch(headlights, value => { vehicleLights?.setEnabled(value); renderVehicleViewer(false); });
let vehicleStreet: ReturnType<typeof createVehicleStreet> | undefined;
let sunLight: THREE.DirectionalLight | undefined;
let skyLight: THREE.HemisphereLight | undefined;
const sceneNight = ref((() => { try { return localStorage.getItem('tmc.tesla.scene-night') === 'true'; } catch { return false; } })());
headlights.value = sceneNight.value;
function updateSceneLighting() {
  if (!vehicleScene || !vehicleSky || !vehicleRenderer || !sunLight || !skyLight) return;
  const night = sceneNight.value;
  vehicleLights?.setEnabled(headlights.value);
  vehicleSky.visible = !night;
  vehicleScene.background = new THREE.Color(night ? '#070e20' : '#c6d9e5');
  const [fogStart, fogEnd] = activeWeather.value === 'fog' ? [35, 145]
    : activeWeather.value === 'snow' ? [65, 235]
    : activeWeather.value === 'rain' ? [75, 280]
    : activeWeather.value === 'cloudy' ? [95, 325] : [110, 390];
  vehicleScene.fog = new THREE.Fog(night ? '#070e20' : '#c6d9e5', fogStart, fogEnd);
  applyStreetLighting(vehicleScene, sunLight, skyLight, night);
  vehicleStreet?.setNight(night);
  vehicleStreet?.setWeather(activeWeather.value, night);
  vehicleWeather?.set(activeWeather.value,night);
  if(vehicleRoadMesh)applyWeatherLighting(vehicleScene,sunLight,vehicleSky,vehicleRoadMesh,activeWeather.value,night);
  // Reuse the captured streetscape; a six-face recapture stalls the UI on each toggle.
  renderVehicleViewer(false);
}
watch(sceneNight, () => { headlights.value = sceneNight.value; updateSceneLighting(); try { localStorage.setItem('tmc.tesla.scene-night', String(sceneNight.value)); } catch { /* Optional persistence. */ } });
let vehicleCamera: THREE.PerspectiveCamera | null = null;
let vehicleRenderer: THREE.WebGLRenderer | null = null;
let vehicleModelRoot: THREE.Group | null = null;
let vehicleModelPivot: THREE.Group | null = null;
let vehicleRoadMesh: THREE.Mesh | null = null;
let vehicleModelBasePositionY = 0;
let vehicleControls: OrbitControls | null = null;
let vehicleCameraDirty = false;
let resizeHandler: (() => void) | null = null;
let vehicleViewerInitialized = false;
let vehicleResetViewTimer: number | null = null;
let vehicleAnimationFrame: number | null = null;
let vehicleRenderLoopFrame: number | null = null;
let vehicleViewTween: {
  startTime: number;
  durationMs: number;
  fromPosition: THREE.Vector3;
  toPosition: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toTarget: THREE.Vector3;
} | null = null;
let vehiclePoseTween: {
  startTime: number;
  durationMs: number;
  fromRotationY: number;
  toRotationY: number;
} | null = null;
let vehicleMotionState = {
  lastFrameTime: 0,
  roadOffset: 0,
  bobPhase: 0,
};
let vehicleWheelMeshes: Array<{ mesh: THREE.Object3D; axis: 'x' | 'y' | 'z'; direction: 1 | -1 }> = [];
let vehicleSplitWheelGroups: THREE.Group[] = [];
let vehicleDoorNodes: THREE.Object3D[] = [];
let officialDoorController: ReturnType<typeof createOfficialDoorController> | undefined;
const modelDoorsOpen = ref(false);
const DEFAULT_VEHICLE_CAMERA_POSITION = new THREE.Vector3(0, 3.4, 8.2);
const DEFAULT_VEHICLE_CAMERA_TARGET = new THREE.Vector3(0, 1.35, 0);
const DRIVE_VEHICLE_CAMERA_POSITION = new THREE.Vector3(-3.6, 2.8, 7.1);
const DRIVE_VEHICLE_CAMERA_TARGET = new THREE.Vector3(0, 1.2, 0);
const REVERSE_VEHICLE_CAMERA_POSITION = new THREE.Vector3(3.6, 2.9, 7.2);
const REVERSE_VEHICLE_CAMERA_TARGET = new THREE.Vector3(0, 1.2, 0);
const PARK_VEHICLE_CAMERA_POSITION = DEFAULT_VEHICLE_CAMERA_POSITION.clone();
const PARK_VEHICLE_CAMERA_TARGET = DEFAULT_VEHICLE_CAMERA_TARGET.clone();
const VEHICLE_MAX_RENDER_PIXELS = 1_400_000;

function vehiclePixelRatio(width: number, height: number) {
  return Math.min(window.devicePixelRatio || 1, 1, Math.sqrt(VEHICLE_MAX_RENDER_PIXELS / Math.max(1, width * height)));
}

type TeslaTabName = 'status' | 'track' | 'trip' | 'raw' | 'settings';

const ACTIVE_TAB_POLL_INTERVAL_MS: Record<TeslaTabName, number> = {
  status: 1000,
  track: 1000,
  trip: 15000,
  raw: 5000,
  settings: 10000,
};

const state = reactive({
  activeTab: 'status',
  settings: {
    mode: 'owner_api',
    clientId: '',
    apiBaseUrl: '',
    authBaseUrl: '',
    tokenPath: '',
    accessToken: '',
    refreshToken: '',
    hasAccessToken: false,
    hasRefreshToken: false,
    dbPath: '',
    retentionDays: 30,
    maxStorageMb: 256,
  },
  status: {
    configured: false,
    authorized: false,
    liveAuthorized: false,
    profile: null as any,
    profileError: null as any,
    cacheAvailable: false,
    cachedVehicleCount: 0,
    lastSyncAt: 0,
  },
  vehicles: [] as any[],
  selectedVin: '',
  latestSample: null as any,
  trackPoints: [] as any[],
  trips: [] as any[],
  selectedTrip: null as any,
  rawRows: [] as any[],
  rawTotal: 0,
  rawPage: 1,
  rawPageSize: 50,
  rawDetailVisible: false,
  rawDetailRow: null as any,
  settingsLoading: false,
  statusLoading: false,
  syncLoading: false,
  tripsLoading: false,
  tripTrackLoading: false,
  rawLoading: false,
  storageLoading: false,
  mapReady: false,
  mapError: '',
  visualError: '',
  visualLoading: false,
  storage: {
    dbPath: '',
    dbSizeMb: 0,
    sampleCount: 0,
    vehicleCount: 0,
    oldestTimestampMs: 0,
    latestTimestampMs: 0,
    retentionDays: 30,
    maxStorageMb: 256,
    effectivePollIntervalSec: 60,
    currentBackoffSec: 0,
    backgroundSyncRunning: false,
    collectionMode: 'rest',
    lastStreamResult: '',
    streamPhase: 'idle',
  },
  documentVisible: typeof document === 'undefined' ? true : document.visibilityState === 'visible',
  pageExposed: true,
});

const geoLocation = useGeoLocationStore();
const gpsSpeedTracker = createGpsSpeedTracker();
const gpsSpeedKmh = ref<number | null>(null);
const gpsSpeedMessage = ref('等待 GPS 定位');
let gpsSpeedExpiry: number | undefined;
let gpsSpeedWatchId: number | undefined;
function receiveGpsSpeed(position: GeoLocation) {
  // The Debug page reads this same store value directly. Some head units provide a
  // valid coords.speed with a position timestamp that does not match Date.now().
  const nativeSpeedKmh = speedFromLiveGpsFix(position.speed);
  const speed = nativeSpeedKmh ?? gpsSpeedTracker.accept({ ...position, speed: null, timestamp: Date.now() });
  if (speed === null) {
    if (gpsSpeedKmh.value === null)
      gpsSpeedMessage.value = position.accuracy > 30 ? 'GPS 精度不足' : '正在计算 GPS 速度';
    return;
  }
  gpsSpeedKmh.value = speed;
  gpsSpeedMessage.value = '';
  window.clearTimeout(gpsSpeedExpiry);
  gpsSpeedExpiry = window.setTimeout(() => { gpsSpeedKmh.value = null; gpsSpeedMessage.value = 'GPS 信号中断'; },
    GPS_SPEED_MAX_AGE_MS);
}
function handleGpsSpeedError(error: GeolocationPositionError) {
  gpsSpeedMessage.value = !window.isSecureContext ? '定位需要 HTTPS' :
    error.code === 1 ? '请允许位置权限' : error.code === 2 ? 'GPS 暂不可用' : '等待 GPS 定位';
}

const selectedVehicle = computed(() => {
  return state.vehicles.find((item: any) => item.vin === state.selectedVin) || null;
});

const debugShiftState = computed(() => {
  if (typeof window === 'undefined') {
    return '';
  }
  const searchParams = new URLSearchParams(window.location.search);
  const hashQuery = window.location.hash.includes('?')
    ? window.location.hash.slice(window.location.hash.indexOf('?') + 1)
    : '';
  const hashParams = new URLSearchParams(hashQuery);
  const shift = String(hashParams.get('shift') || searchParams.get('shift') || '').toUpperCase();
  return ['P', 'D', 'R'].includes(shift) ? shift : '';
});

const currentShiftState = computed(() => {
  if (debugShiftState.value) {
    return debugShiftState.value;
  }
  const shift = String(state.latestSample?.shift_state || '').toUpperCase();
  if (shift === 'D' || shift === 'R' || shift === 'P') {
    if (shift !== 'P' || gpsSpeedKmh.value === null || gpsSpeedKmh.value < 2) return shift;
  }
  if (gpsSpeedKmh.value !== null && gpsSpeedKmh.value >= 2) return 'D';
  if (String(state.latestSample?.vehicle_state || '').toLowerCase() === 'driving') {
    return 'D';
  }
  return 'P';
});

const vehicleVisualStatus = computed(() => {
  if (currentShiftState.value === 'D') {
    return {
      label: 'D 档',
      description: '行驶状态，车头朝前。',
      accent: 'status-pill--ok',
    };
  }
  if (currentShiftState.value === 'R') {
    return {
      label: 'R 档',
      description: '倒车状态，车尾朝前。',
      accent: 'status-pill--warn',
    };
  }
  return {
    label: 'P 档',
    description: '展示模式，车辆横向停放。',
    accent: '',
  };
});

const currentVehicleSpeedKmh = computed(() => {
  return gpsSpeedKmh.value ?? 0;
});

const RAW_COLUMN_ORDER = [
  'timestamp_ms',
  'id',
  'vin',
  'display_name',
  'vehicle_state',
  'latitude',
  'longitude',
  'coord_type',
  'native_lat',
  'native_lng',
  'heading',
  'native_heading',
  'speed',
  'speed_unit',
  'shift_state',
  'battery_level',
  'usable_battery_level',
  'charging_state',
  'charge_limit_soc',
  'odometer',
  'distance_unit',
  'locked',
  'inside_temp',
  'outside_temp',
  'is_climate_on',
  'sentry_mode',
  'created_at',
];

const RAW_PREVIEW_COLUMNS = [
  'timestamp_ms',
  'vehicle_state',
  'shift_state',
  'speed',
  'battery_level',
];

const rawColumns = computed(() => {
  const keySet = new Set<string>();
  for (const row of state.rawRows) {
    Object.keys(row || {}).forEach((key) => keySet.add(key));
  }
  const keys = Array.from(keySet);
  return keys.sort((a, b) => {
    const aIndex = RAW_COLUMN_ORDER.indexOf(a);
    const bIndex = RAW_COLUMN_ORDER.indexOf(b);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex) - (bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex);
    }
    return a.localeCompare(b);
  });
});

const rawPreviewColumns = computed(() => {
  const keySet = new Set<string>();
  for (const row of state.rawRows) {
    Object.keys(row || {}).forEach((key) => keySet.add(key));
  }
  return RAW_PREVIEW_COLUMNS.filter((key) => keySet.has(key));
});

const rawDetailEntries = computed(() => {
  const row = state.rawDetailRow || {};
  return rawColumns.value
    .filter((key) => Object.prototype.hasOwnProperty.call(row, key))
    .map((key) => ({
      key,
      value: formatRawCell(row, key),
    }));
});

const sampleCards = computed(() => {
  const sample = state.latestSample || {};
  const speedUnit = sample.speed_unit || 'km/h';
  const distanceUnit = sample.distance_unit || 'km';
  return [
    { label: '车速', value: sample.speed != null ? `${sample.speed} ${speedUnit}` : '-' },
    { label: '档位', value: sample.shift_state || '-' },
    { label: '车内温度', value: sample.inside_temp != null ? `${sample.inside_temp}°C` : '-' },
    { label: '车外温度', value: sample.outside_temp != null ? `${sample.outside_temp}°C` : '-' },
    { label: '里程', value: sample.odometer != null ? `${sample.odometer} ${distanceUnit}` : '-' },
    { label: '充电状态', value: sample.charging_state || '-' },
    { label: '充电上限', value: sample.charge_limit_soc != null ? `${sample.charge_limit_soc}%` : '-' },
    { label: '哨兵模式', value: sample.sentry_mode != null ? (sample.sentry_mode ? '开启' : '关闭') : '-' },
    { label: '空调', value: sample.is_climate_on != null ? (sample.is_climate_on ? '开启' : '关闭') : '-' },
  ];
});

function formatTimestamp(timestampMs?: number) {
  if (!timestampMs) {
    return '-';
  }
  const date = new Date(timestampMs);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
}

function formatDuration(totalSec?: number) {
  if (!totalSec) {
    return '0 分钟';
  }
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  if (hours > 0) {
    return `${hours}小时${minutes}分钟`;
  }
  return `${minutes}分钟`;
}

function formatRawCell(row: any, key: string) {
  const value = row?.[key];
  if (value == null || value === '') {
    return '-';
  }
  if (key === 'timestamp_ms') {
    return formatTimestamp(Number(value));
  }
  if (key === 'created_at') {
    return formatTimestamp(Number(value) * 1000);
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return String(value);
}

function getVehicleOrientationByShift(shiftState: string) {
  if (shiftState === 'D') {
    return Math.PI;
  }
  if (shiftState === 'R') {
    return 0;
  }
  return Math.PI / 2;
}

function getVehicleCameraPresetByShift(shiftState: string) {
  if (shiftState === 'D') {
    return {
      position: DRIVE_VEHICLE_CAMERA_POSITION,
      target: DRIVE_VEHICLE_CAMERA_TARGET,
    };
  }
  if (shiftState === 'R') {
    return {
      position: REVERSE_VEHICLE_CAMERA_POSITION,
      target: REVERSE_VEHICLE_CAMERA_TARGET,
    };
  }
  return {
    position: PARK_VEHICLE_CAMERA_POSITION,
    target: PARK_VEHICLE_CAMERA_TARGET,
  };
}

function splitMeshIntoConnectedParts(sourceMesh: THREE.Mesh) {
  const geometry = sourceMesh.geometry;
  const position = geometry.getAttribute('position');
  const index = geometry.getIndex();
  if (!position || !index) {
    return [];
  }

  const indexArray = Array.from(index.array as ArrayLike<number>);
  const triangleCount = Math.floor(indexArray.length / 3);
  const vertexTriangleMap: number[][] = Array.from({ length: position.count }, () => []);
  for (let triangleIndex = 0; triangleIndex < triangleCount; triangleIndex += 1) {
    const base = triangleIndex * 3;
    vertexTriangleMap[indexArray[base]]?.push(triangleIndex);
    vertexTriangleMap[indexArray[base + 1]]?.push(triangleIndex);
    vertexTriangleMap[indexArray[base + 2]]?.push(triangleIndex);
  }

  const visited = new Uint8Array(triangleCount);
  const parts: Array<{ geometry: THREE.BufferGeometry; center: THREE.Vector3; size: THREE.Vector3 }> = [];

  for (let startTriangle = 0; startTriangle < triangleCount; startTriangle += 1) {
    if (visited[startTriangle]) {
      continue;
    }
    const queue = [startTriangle];
    visited[startTriangle] = 1;
    const triangles: number[] = [];
    const vertexSet = new Set<number>();

    while (queue.length > 0) {
      const triangleIndex = queue.pop() as number;
      triangles.push(triangleIndex);
      const base = triangleIndex * 3;
      const a = indexArray[base];
      const b = indexArray[base + 1];
      const c = indexArray[base + 2];
      vertexSet.add(a);
      vertexSet.add(b);
      vertexSet.add(c);
      [a, b, c].forEach((vertexIndex) => {
        vertexTriangleMap[vertexIndex]?.forEach((neighborTriangle) => {
          if (!visited[neighborTriangle]) {
            visited[neighborTriangle] = 1;
            queue.push(neighborTriangle);
          }
        });
      });
    }

    const orderedVertices = Array.from(vertexSet);
    const vertexMap = new Map<number, number>();
    orderedVertices.forEach((vertexIndex, newIndex) => {
      vertexMap.set(vertexIndex, newIndex);
    });

    const componentGeometry = new THREE.BufferGeometry();
    Object.entries(geometry.attributes).forEach(([name, attribute]) => {
      const sourceAttribute = attribute as THREE.BufferAttribute;
      const itemSize = sourceAttribute.itemSize;
      const TargetArray = sourceAttribute.array.constructor as unknown as new (size: number) => ArrayLike<number>;
      const targetArray = new TargetArray(orderedVertices.length * itemSize) as any;
      orderedVertices.forEach((vertexIndex, newIndex) => {
        for (let itemOffset = 0; itemOffset < itemSize; itemOffset += 1) {
          targetArray[newIndex * itemSize + itemOffset] = (sourceAttribute.array as any)[vertexIndex * itemSize + itemOffset];
        }
      });
      componentGeometry.setAttribute(name, new THREE.BufferAttribute(targetArray, itemSize, sourceAttribute.normalized));
    });

    const IndexArrayCtor = orderedVertices.length > 65535 ? Uint32Array : Uint16Array;
    const componentIndices = new IndexArrayCtor(triangles.length * 3);
    triangles.forEach((triangleIndex, offset) => {
      const base = triangleIndex * 3;
      componentIndices[offset * 3] = vertexMap.get(indexArray[base]) as number;
      componentIndices[offset * 3 + 1] = vertexMap.get(indexArray[base + 1]) as number;
      componentIndices[offset * 3 + 2] = vertexMap.get(indexArray[base + 2]) as number;
    });
    componentGeometry.setIndex(new THREE.BufferAttribute(componentIndices, 1));
    componentGeometry.computeBoundingBox();
    const bbox = componentGeometry.boundingBox || new THREE.Box3();
    const center = bbox.getCenter(new THREE.Vector3());
    const size = bbox.getSize(new THREE.Vector3());
    componentGeometry.translate(-center.x, -center.y, -center.z);
    parts.push({ geometry: componentGeometry, center, size });
  }

  return parts;
}

function detectVehicleWheelMeshes(model: THREE.Object3D, modelBounds: THREE.Box3) {
  const official = isOfficialVehicle(model);
  const namedWheelNodes: Array<{ mesh: THREE.Object3D; axis: 'x' | 'y' | 'z'; direction: 1 | -1 }> = [];
  model.traverse((child: THREE.Object3D) => {
    if (!(official ? /^Wheel_(?:LF|RF|LR|RR)$/i : /^Wheel_(?:FL|FR|RL|RR)$/i).test(child.name || '')) {
      return;
    }
    namedWheelNodes.push({
      mesh: child,
      axis: official ? 'z' : 'x',
      direction: child.userData.spinDirection === 1 ? 1 : child.userData.spinDirection === -1 ? -1 : official ? (/_(?:LF|LR)$/i.test(child.name) ? 1 : -1) : (child.position.x >= 0 ? -1 : 1),
    });
  });

  if (namedWheelNodes.length > 0) {
    vehicleWheelMeshes = namedWheelNodes;
    return;
  }

  const size = modelBounds.getSize(new THREE.Vector3());
  const center = modelBounds.getCenter(new THREE.Vector3());
  const wheelCandidates: Array<{ mesh: THREE.Mesh; axis: 'x' | 'y' | 'z'; direction: 1 | -1; score: number }> = [];
  const splitGroups: THREE.Group[] = [];

  model.updateMatrixWorld(true);
  model.traverse((child: THREE.Object3D) => {
    if (!(child as THREE.Mesh).isMesh) {
      return;
    }
    const mesh = child as THREE.Mesh;
    const materialNames = (Array.isArray(mesh.material) ? mesh.material : [mesh.material])
      .map((material) => String(material?.name || ''))
      .join(' ')
      .toLowerCase();
    const searchText = `${child.name} ${mesh.name} ${materialNames}`.toLowerCase();
    const namedWheelSource = /(pneu|tire|tyre|wheel|rim)/.test(searchText);
    const parts = splitMeshIntoConnectedParts(mesh);
    if (parts.length < 4) {
      return;
    }
    const candidateParts = parts.filter((part) => {
      const lowEnough = part.center.y < center.y;
      const sideEnough = Math.abs(part.center.x - center.x) > size.x * 0.18;
      const endEnough = Math.abs(part.center.z - center.z) > size.z * 0.18;
      const compactEnough = part.size.x < size.x * 0.42 && part.size.y < size.y * 0.55 && part.size.z < size.z * 0.28;
      return lowEnough && sideEnough && endEnough && compactEnough;
    });

    if (candidateParts.length < 4) {
      return;
    }

    if (!namedWheelSource && candidateParts.length !== parts.length) {
      return;
    }

    const splitGroup = new THREE.Group();
    splitGroup.name = `${mesh.name || child.name || 'wheel'}__split`;
    splitGroup.position.copy(mesh.position);
    splitGroup.quaternion.copy(mesh.quaternion);
    splitGroup.scale.copy(mesh.scale);
    splitGroup.matrixAutoUpdate = true;

    candidateParts.forEach((part, index) => {
      const partMesh = new THREE.Mesh(part.geometry, mesh.material);
      partMesh.name = `${splitGroup.name}_${index}`;
      partMesh.position.copy(part.center);
      splitGroup.add(partMesh);

      const dimensions = [
        { axis: 'x' as const, value: part.size.x },
        { axis: 'y' as const, value: part.size.y },
        { axis: 'z' as const, value: part.size.z },
      ].sort((a, b) => a.value - b.value);
      const axis = dimensions[0].axis;
      const direction = part.center.x >= center.x ? -1 : 1;
      const score = Math.abs(part.center.x - center.x) + Math.abs(part.center.z - center.z) - part.size.length();
      wheelCandidates.push({ mesh: partMesh, axis, direction, score });
    });

    mesh.parent?.add(splitGroup);
    mesh.visible = false;
    splitGroups.push(splitGroup);
  });

  vehicleSplitWheelGroups = splitGroups;
  wheelCandidates.sort((a, b) => b.score - a.score);
  vehicleWheelMeshes = wheelCandidates.slice(0, 12).map((candidate) => ({
    mesh: candidate.mesh,
    axis: candidate.axis,
    direction: candidate.direction,
  }));
}

function getVehicleMotionProfile() {
  const speedKmh = currentVehicleSpeedKmh.value;
  const visualSpeedMps = visualTravelSpeedMps(speedKmh);
  if (currentShiftState.value === 'D') {
    return {
      active: true,
      direction: -1,
      moving: visualSpeedMps > 0,
      roadSpeed: visualSpeedMps / ROAD_TEXTURE_LENGTH,
      wheelSpeed: wheelAngularSpeed(speedKmh),
    };
  }
  if (currentShiftState.value === 'R') {
    return {
      active: true,
      direction: 1,
      moving: visualSpeedMps > 0,
      roadSpeed: visualSpeedMps / ROAD_TEXTURE_LENGTH,
      wheelSpeed: wheelAngularSpeed(speedKmh),
    };
  }
  return {
    active: false,
    direction: 0,
    moving: false,
    roadSpeed: 0,
    wheelSpeed: 0,
  };
}

function openRawRowDetail(row: any) {
  state.rawDetailRow = row;
  state.rawDetailVisible = true;
}

function loadSettings() {
  state.settingsLoading = true;
  return get('/api/tesla/settings', '读取 Tesla 配置失败').then((data) => {
    state.settings.mode = data.mode || 'owner_api';
    state.settings.clientId = data.clientId || '';
    state.settings.apiBaseUrl = data.apiBaseUrl || '';
    state.settings.authBaseUrl = data.authBaseUrl || '';
    state.settings.tokenPath = data.tokenPath || '';
    state.settings.accessToken = data.accessToken || '';
    state.settings.refreshToken = data.refreshToken || '';
    state.settings.hasAccessToken = Boolean(data.accessToken || data.hasAccessToken);
    state.settings.hasRefreshToken = Boolean(data.refreshToken || data.hasRefreshToken);
    state.settings.dbPath = data.dbPath || '';
    state.settings.retentionDays = Number(data.retentionDays) || 30;
    state.settings.maxStorageMb = Number(data.maxStorageMb) || 256;
  }).finally(() => {
    state.settingsLoading = false;
  });
}

function saveSettings() {
  state.settingsLoading = true;
  post('/api/tesla/settings', {
    mode: state.settings.mode,
    clientId: state.settings.clientId.trim(),
    apiBaseUrl: state.settings.apiBaseUrl.trim(),
    authBaseUrl: state.settings.authBaseUrl.trim(),
    tokenPath: state.settings.tokenPath.trim(),
    accessToken: state.settings.accessToken.trim(),
    refreshToken: state.settings.refreshToken.trim(),
    retentionDays: state.settings.retentionDays,
    maxStorageMb: state.settings.maxStorageMb,
  }, '保存 Tesla 配置失败').then((data) => {
    state.settings.mode = data.mode || 'owner_api';
    state.settings.clientId = data.clientId || '';
    state.settings.apiBaseUrl = data.apiBaseUrl || '';
    state.settings.authBaseUrl = data.authBaseUrl || '';
    state.settings.tokenPath = data.tokenPath || '';
    state.settings.accessToken = data.accessToken || '';
    state.settings.refreshToken = data.refreshToken || '';
    state.settings.hasAccessToken = Boolean(data.accessToken || data.hasAccessToken);
    state.settings.hasRefreshToken = Boolean(data.refreshToken || data.hasRefreshToken);
    state.settings.dbPath = data.dbPath || '';
    state.settings.retentionDays = Number(data.retentionDays) || 30;
    state.settings.maxStorageMb = Number(data.maxStorageMb) || 256;
    ElMessage.success('Tesla 配置已保存');
    return loadStorage();
  }).finally(() => {
    state.settingsLoading = false;
  });
}

function loadStorage() {
  state.storageLoading = true;
  return get('/api/tesla/storage', '读取 Tesla 存储信息失败').then((data) => {
    state.storage = data;
  }).finally(() => {
    state.storageLoading = false;
  });
}

function clearStorage() {
  state.storageLoading = true;
  post('/api/tesla/storage/clear', {}, '清理 Tesla SQLite 记录失败').then((data) => {
    state.storage = data;
    state.trackPoints = [];
    state.trips = [];
    state.latestSample = null;
    state.selectedTrip = null;
    state.tripTrackLoading = false;
    renderTrackOnMap();
    ElMessage.success('Tesla SQLite 记录已清理');
  }).finally(() => {
    state.storageLoading = false;
  });
}

function loadStatus() {
  state.statusLoading = true;
  return get('/api/tesla/auth/status', '读取 Tesla 授权状态失败').then((data) => {
    state.status = data;
  }).finally(() => {
    state.statusLoading = false;
  });
}

function loadVehicles() {
  return get('/api/tesla/vehicles', '读取车辆列表失败').then((data) => {
    state.vehicles = data || [];
    if (!state.vehicles.some((item: any) => item.vin === state.selectedVin)) {
      state.selectedVin = state.vehicles[0]?.vin || '';
    }
  });
}

function syncLatestSampleFromSelectedVehicle() {
  const vehicle = selectedVehicle.value;
  if (vehicle?.latestSample) {
    state.latestSample = vehicle.latestSample;
    return;
  }
  if (!state.selectedTrip) {
    state.latestSample = null;
  }
}

function loadVehicleStatus() {
  if (!state.selectedVin) {
    state.latestSample = null;
    return Promise.resolve();
  }
  return get(`/api/tesla/status?vin=${encodeURIComponent(state.selectedVin)}`, '读取车辆状态失败').then((data) => {
    if (data.vehicle) {
      const index = state.vehicles.findIndex((item: any) => item.vin === data.vehicle.vin);
      if (index >= 0) {
        state.vehicles[index] = data.vehicle;
      } else {
        state.vehicles = [data.vehicle, ...state.vehicles];
      }
    }
    state.latestSample = data.latestSample || data.vehicle?.latestSample || null;
    if (data.lastSyncAt) {
      state.status.lastSyncAt = data.lastSyncAt;
    }
  });
}

function loadTrack() {
  state.tripTrackLoading = false;
  if (!state.selectedVin) {
    state.trackPoints = [];
    state.latestSample = null;
    renderTrackOnMap();
    return Promise.resolve();
  }
  let url = `/api/tesla/history/track?vin=${encodeURIComponent(state.selectedVin)}&limit=600`;
  if (state.selectedTrip?.startTimeMs && state.selectedTrip?.endTimeMs) {
    url += `&startMs=${state.selectedTrip.startTimeMs}&endMs=${state.selectedTrip.endTimeMs}`;
  }
  return get(url, '读取轨迹失败').then((data) => {
    state.trackPoints = data.points || [];
    state.latestSample = data.latest || null;
    renderTrackOnMap();
  });
}

function syncSelectedTripWithTrips() {
  const trips = state.trips || [];
  if (trips.length === 0) {
    state.selectedTrip = null;
    return;
  }
  const selectedKey = state.selectedTrip ? `${state.selectedTrip.startTimeMs}-${state.selectedTrip.endTimeMs}` : '';
  const matched = trips.find((trip: any) => `${trip.startTimeMs}-${trip.endTimeMs}` === selectedKey);
  state.selectedTrip = matched || trips[0];
}

function loadTrips() {
  if (!state.selectedVin) {
    state.trips = [];
    state.selectedTrip = null;
    state.tripTrackLoading = false;
    return Promise.resolve();
  }
  state.tripsLoading = true;
  return get(`/api/tesla/history/trips?vin=${encodeURIComponent(state.selectedVin)}&limit=20000`, '读取行程失败').then((data) => {
    state.trips = data.items || [];
    syncSelectedTripWithTrips();
  }).finally(() => {
    state.tripsLoading = false;
  });
}

function loadRawRows() {
  if (!state.selectedVin) {
    state.rawRows = [];
    state.rawTotal = 0;
    return Promise.resolve();
  }
  state.rawLoading = true;
  return get(
    `/api/tesla/history/raw?vin=${encodeURIComponent(state.selectedVin)}&page=${state.rawPage}&pageSize=${state.rawPageSize}`,
    '读取原始记录失败'
  ).then((data) => {
    state.rawRows = data.items || [];
    state.rawTotal = Number(data.total) || 0;
  }).finally(() => {
    state.rawLoading = false;
  });
}

function handleVehicleChange() {
  state.selectedTrip = null;
  state.rawPage = 1;
  state.tripTrackLoading = false;
  return Promise.all([loadTrips(), loadRawRows()]).then(() => loadTrack());
}

function openTripTrack(trip: any) {
  state.selectedTrip = trip;
  state.activeTab = 'track';
  state.tripTrackLoading = true;
  const tripKey = `${trip.startTimeMs}-${trip.endTimeMs}`;
  return get(
    `/api/tesla/history/trips/detail?vin=${encodeURIComponent(state.selectedVin)}&startMs=${trip.startTimeMs}&endMs=${trip.endTimeMs}&limit=20000`,
    '读取行程轨迹失败'
  ).then((data) => {
    const selectedKey = state.selectedTrip ? `${state.selectedTrip.startTimeMs}-${state.selectedTrip.endTimeMs}` : '';
    if (selectedKey !== tripKey) {
      return;
    }
    const items = data.items || [];
    state.trackPoints = items.filter((item: any) => item.longitude != null && item.latitude != null);
    state.latestSample = data.latest || items[items.length - 1] || null;
    nextTick(() => {
      renderTrackOnMap();
    });
  }).finally(() => {
    const selectedKey = state.selectedTrip ? `${state.selectedTrip.startTimeMs}-${state.selectedTrip.endTimeMs}` : '';
    if (selectedKey === tripKey) {
      state.tripTrackLoading = false;
    }
  });
}

function showAllTrack() {
  state.selectedTrip = null;
  state.tripTrackLoading = false;
  loadTrack();
}

function deleteTrip(trip: any) {
  del('/api/tesla/history/trips', {
    vin: state.selectedVin,
    startTimeMs: trip.startTimeMs,
    endTimeMs: trip.endTimeMs,
  }, '删除行程失败').then(() => {
    if (state.selectedTrip?.startTimeMs === trip.startTimeMs && state.selectedTrip?.endTimeMs === trip.endTimeMs) {
      state.selectedTrip = null;
    }
    Promise.all([loadTrips(), loadStorage()]).then(() => {
      return loadTrack();
    }).then(() => {
      ElMessage.success('行程已删除');
    });
  });
}

function handleRawPageChange(page: number) {
  state.rawPage = page;
  loadRawRows();
}

function latestSampleAgeMs() {
  const ts = Number(state.latestSample?.timestamp_ms || 0);
  if (!ts) {
    return Number.POSITIVE_INFINITY;
  }
  return Date.now() - ts;
}

function shouldForceFreshSync() {
  if (!state.status.configured || state.syncLoading) {
    return false;
  }
  const selectedState = String(selectedVehicle.value?.state || '').toLowerCase();
  const latestState = String(state.latestSample?.vehicle_state || '').toLowerCase();
  const ageMs = latestSampleAgeMs();

  if (!Number.isFinite(ageMs)) {
    return true;
  }
  if (selectedState && latestState && selectedState !== latestState && ageMs > 30 * 1000) {
    return true;
  }
  if (selectedState === 'online' && ageMs > 60 * 1000) {
    return true;
  }
  if (latestState === 'online' || latestState === 'driving') {
    return ageMs > 60 * 1000;
  }
  return ageMs > 2 * 60 * 1000;
}

function maybeForceFreshSync(tabName: TeslaTabName = state.activeTab as TeslaTabName): Promise<void> {
  if (tabName === 'track' && state.selectedTrip) {
    return Promise.resolve();
  }
  const now = Date.now();
  if (!shouldForceFreshSync()) {
    return Promise.resolve();
  }
  if (now - lastForcedSyncAt < 45 * 1000) {
    return Promise.resolve();
  }
  lastForcedSyncAt = now;
  return syncVehicles(false, tabName);
}

function clearTabData(_tabName: TeslaTabName) {
  state.vehicles = [];
  state.selectedVin = '';
  state.trackPoints = [];
  state.latestSample = null;
  state.trips = [];
  state.selectedTrip = null;
  state.tripTrackLoading = false;
  state.rawRows = [];
  state.rawTotal = 0;
  renderTrackOnMap();
  updateVehicleVisualState();
}

function refreshTabData(tabName: TeslaTabName, options?: { allowForceSync?: boolean; includeStorage?: boolean; includeMeta?: boolean }): Promise<void> {
  const allowForceSync = options?.allowForceSync ?? true;
  const includeStorage = options?.includeStorage ?? tabName === 'settings';
  const includeMeta = options?.includeMeta ?? true;

  const baseTasks: Promise<any>[] = [];
  if (includeMeta) {
    baseTasks.push(loadStatus());
  }
  if (includeStorage) {
    baseTasks.push(loadStorage());
  }

  return Promise.all(baseTasks).then(() => {
    if (includeMeta && !state.status.configured && !state.status.cacheAvailable) {
      clearTabData(tabName);
      return;
    }
    const ensureVehicles = includeMeta ? loadVehicles() : Promise.resolve();
    return ensureVehicles.then(() => {
      if (tabName === 'status') {
        return loadVehicleStatus();
      }
      if (tabName === 'track') {
        if (state.selectedTrip) {
          return Promise.resolve();
        }
        return loadTrack();
      }
      if (tabName === 'trip') {
        return loadTrips();
      }
      if (tabName === 'raw') {
        return loadRawRows();
      }
      return Promise.resolve();
    });
  }).then(() => {
    if (allowForceSync && (tabName === 'status' || tabName === 'track')) {
      return maybeForceFreshSync(tabName);
    }
    return Promise.resolve();
  });
}

function isTeslaPageVisible() {
  return state.documentVisible && state.pageExposed;
}

function stopAutoSyncTimer() {
  if (autoSyncTimer !== null) {
    window.clearInterval(autoSyncTimer);
    autoSyncTimer = null;
  }
}

function refreshActiveTabData(options?: { allowForceSync?: boolean; immediate?: boolean; includeMeta?: boolean }): Promise<void> {
  const allowForceSync = options?.allowForceSync ?? true;
  const immediate = options?.immediate ?? false;
  const includeMeta = options?.includeMeta ?? immediate;

  if (!immediate && !isTeslaPageVisible()) {
    return Promise.resolve();
  }
  if (tabPollInFlight) {
    pendingTabRefreshOptions = {
      allowForceSync: (pendingTabRefreshOptions?.allowForceSync ?? false) || allowForceSync,
      immediate: (pendingTabRefreshOptions?.immediate ?? false) || immediate,
      includeMeta: (pendingTabRefreshOptions?.includeMeta ?? false) || includeMeta,
    };
    return Promise.resolve();
  }
  tabPollInFlight = true;
  return refreshTabData(state.activeTab as TeslaTabName, { allowForceSync, includeMeta }).finally(() => {
    tabPollInFlight = false;
    const pending = pendingTabRefreshOptions;
    pendingTabRefreshOptions = null;
    if (pending) {
      void refreshActiveTabData(pending);
    }
  });
}

function startAutoSyncTimer() {
  stopAutoSyncTimer();
  if (!isTeslaPageVisible()) {
    return;
  }
  autoSyncTimer = window.setInterval(() => {
    refreshActiveTabData({ includeMeta: false });
  }, ACTIVE_TAB_POLL_INTERVAL_MS[state.activeTab as TeslaTabName]);
}

function restartAutoSyncTimer() {
  startAutoSyncTimer();
}

function handleDocumentVisibilityChange() {
  state.documentVisible = document.visibilityState === 'visible';
  restartAutoSyncTimer();
  if (isTeslaPageVisible()) {
    refreshActiveTabData({ immediate: true });
  }
}

function observePageExposure() {
  if (!pageRef.value || typeof IntersectionObserver === 'undefined') {
    state.pageExposed = true;
    restartAutoSyncTimer();
    return;
  }
  pageObserver = new IntersectionObserver((entries) => {
    const entry = entries[0];
    state.pageExposed = Boolean(entry?.isIntersecting && entry.intersectionRatio >= 0.15);
    restartAutoSyncTimer();
    if (isTeslaPageVisible()) {
      refreshActiveTabData({ immediate: true });
    }
  }, {
    threshold: [0, 0.15, 0.5],
  });
  pageObserver.observe(pageRef.value);
}

function syncVehicles(showMessage = false, tabName: TeslaTabName = state.activeTab as TeslaTabName): Promise<void> {
  state.syncLoading = true;
  const includeMetaAfterSync = tabName !== 'status';
  return post('/api/tesla/sync', {
    vin: state.selectedVin || undefined,
  }, '同步 Tesla 数据失败').then(() => {
    return refreshTabData(tabName, {
      allowForceSync: false,
      includeStorage: true,
      includeMeta: includeMetaAfterSync,
    }).then(() => {
      if (showMessage) {
        ElMessage.success('Tesla 数据已同步');
      }
    });
  }).finally(() => {
    state.syncLoading = false;
  });
}

function initVehicleViewer() {
  if (vehicleViewerInitialized || !vehicleVisualRef.value) {
    return;
  }
  state.visualLoading = true;
  state.visualError = '';
  const manager = new THREE.LoadingManager();
  let resourceFailed = false;

  const container = vehicleVisualRef.value;
  vehicleScene = new THREE.Scene();
  vehicleScene.background = new THREE.Color('#c6d9e5');
  vehicleScene.fog = new THREE.Fog('#c6d9e5', 65, 220);

  vehicleCamera = new THREE.PerspectiveCamera(32, 1, 0.1, 1200);
  vehicleCamera.position.copy(DEFAULT_VEHICLE_CAMERA_POSITION);
  vehicleCamera.lookAt(DEFAULT_VEHICLE_CAMERA_TARGET);

  vehicleRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  const initialWidth = container.clientWidth || 640, initialHeight = container.clientHeight || 420;
  vehicleRenderer.setPixelRatio(vehiclePixelRatio(initialWidth, initialHeight));
  vehicleRenderer.setSize(initialWidth, initialHeight);
  vehicleRenderer.outputColorSpace = THREE.SRGBColorSpace;
  vehicleRenderer.toneMapping = THREE.ACESFilmicToneMapping;
  vehicleRenderer.toneMappingExposure = 1;
  vehicleRenderer.shadowMap.enabled = true;
  vehicleRenderer.shadowMap.autoUpdate = false;
  vehicleRenderer.shadowMap.needsUpdate = true;
  vehicleRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.innerHTML = '';
  container.appendChild(vehicleRenderer.domElement);

  vehicleControls = new OrbitControls(vehicleCamera, vehicleRenderer.domElement);
  vehicleControls.enablePan = false;
  vehicleControls.enableDamping = true;
  vehicleControls.dampingFactor = 0.08;
  vehicleControls.rotateSpeed = 0.8;
  vehicleControls.minDistance = 5.5;
  vehicleControls.maxDistance = 11;
  vehicleControls.minPolarAngle = Math.PI / 3.6;
  vehicleControls.maxPolarAngle = Math.PI / 2.05;
  vehicleControls.target.copy(DEFAULT_VEHICLE_CAMERA_TARGET);
  vehicleControls.addEventListener('change', () => { vehicleCameraDirty = true; });
  vehicleControls.addEventListener('start', () => {
    if (vehicleResetViewTimer !== null) {
      window.clearTimeout(vehicleResetViewTimer);
      vehicleResetViewTimer = null;
    }
    stopVehicleViewTween();
  });
  vehicleControls.addEventListener('end', () => {
    scheduleVehicleViewReset();
  });

  // The visible sky, paint reflections and sunlight share one sun direction.
  vehicleSky = new Sky();
  vehicleSky.scale.setScalar(450);
  const sun = VEHICLE_SUN_DIRECTION.clone();
  const uniforms = vehicleSky.material.uniforms;
  uniforms.turbidity.value = 3;
  uniforms.rayleigh.value = 1.6;
  uniforms.mieCoefficient.value = .004;
  uniforms.mieDirectionalG.value = .8;
  uniforms.sunPosition.value.copy(sun);
  vehicleScene.add(vehicleSky);
  const environmentScene = new THREE.Scene();
  const reflectionSky = vehicleSky.clone();
  environmentScene.add(reflectionSky);
  const pmrem = new THREE.PMREMGenerator(vehicleRenderer);
  vehicleEnvironment = pmrem.fromScene(environmentScene, .04, .1, 1000);
  vehicleScene.environment = vehicleEnvironment.texture;
  vehicleScene.environmentIntensity = .22;
  pmrem.dispose();
  skyLight = new THREE.HemisphereLight('#dcecff', '#655b4d', .65);
  vehicleScene.add(skyLight);
  const keyLight = new THREE.DirectionalLight('#fff1dc', 3);
  sunLight = keyLight;
  configureStreetSun(keyLight);
  vehicleScene.add(keyLight);

  vehicleModelPivot = new THREE.Group();
  vehicleModelPivot.position.y = 0.85;
  vehicleScene.add(vehicleModelPivot);

  const activeRenderer = vehicleRenderer;
  let resolveModelReady: (ready: boolean) => void = () => {};
  const modelReady = new Promise<boolean>(resolve => { resolveModelReady = resolve; });
  manager.onError = () => {
    resourceFailed = true;
    if (vehicleRenderer !== activeRenderer) return;
    state.visualError = '场景资源加载失败，请刷新重试';
    state.visualLoading = false;
  };
  vehicleRoadMesh = createVehicleRoadMesh(manager);
  vehicleModelPivot.add(vehicleRoadMesh);
  vehicleWeather=createVehicleWeather();vehicleModelPivot.add(vehicleWeather.group);
  vehicleStreet = createVehicleStreet(manager);
  const loadedStreet=vehicleStreet;
  loadedStreet.ready.then(()=>{if(vehicleStreet===loadedStreet){streetReflectionsReady=true;streetReflectionsDirty=true;renderVehicleViewer();}});
  vehicleStreet.group.position.y = vehicleRoadMesh.position.y;
  vehicleModelPivot.add(vehicleStreet.group);
  updateSceneLighting();

  manager.onLoad = async () => {
    const [carLoaded] = await Promise.all([modelReady, loadedStreet.ready]);
    if (vehicleRenderer !== activeRenderer) return;
    if (resourceFailed || !carLoaded || !vehicleModelRoot) {
      state.visualError = '场景资源加载失败，请刷新重试';
      state.visualLoading = false;
      return;
    }
    streetReflectionsReady = true;
    streetReflectionsDirty = true;
    try {
      resizeVehicleViewer();
      // Render the complete scene and its reflections before revealing it.
      renderVehicleViewer();
      // The first visible headlight switch otherwise compiles spotlight/lens
      // shaders and allocates its shadow map on the user's click. Warm that
      // path while the loading cover is still shown, then restore daylight.
      if (!headlights.value && vehicleLights && vehicleScene && vehicleCamera) {
        vehicleLights.setEnabled(true);
        try {
          activeRenderer.shadowMap.needsUpdate = true;
          activeRenderer.render(vehicleScene, vehicleCamera);
        } finally {
          vehicleLights.setEnabled(false);
        }
        renderVehicleViewer(false);
      }
      state.visualLoading = false;
    } catch (error) {
      console.error(error);
      state.visualError = '场景渲染失败，请刷新重试';
      state.visualLoading = false;
    }
  };
  const loader = new GLTFLoader(manager);
  loader.setMeshoptDecoder(MeshoptDecoder);
  state.visualLoading = true;
  loadVehicleModel(loader).then((gltf) => {
    if (vehicleRenderer !== activeRenderer) return;
    const model = gltf.scene;
    const official = prepareOfficialVehicle(model);
    if (official) model.rotation.y = Math.PI; // Tesla's export faces -Z; this viewer expects +Z.
    else repairVehicleInterior(model);
    vehicleWipers = createVehicleWipers(model);
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxAxis = Math.max(size.x, size.y, size.z) || 1;
    const scale = 4.8 / maxAxis;

    model.position.copy(center).multiplyScalar(-scale);
    model.position.y += size.y * scale * 0.08;
    model.scale.setScalar(scale);
    if (vehicleRoadMesh) vehicleRoadMesh.position.y = -size.y * scale * .42 - .012;
    if (vehicleStreet && vehicleRoadMesh) vehicleStreet.group.position.y = vehicleRoadMesh.position.y;
    model.traverse((child: THREE.Object3D) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.castShadow = true;
        mesh.receiveShadow = false;
      }
    });

    vehicleModelRoot = model;
    vehicleLights = createVehicleLights(model);
    vehicleLights.setEnabled(headlights.value);
    vehicleAppearance?.dispose();
    vehicleAppearance = createVehicleAppearance(model);
    vehicleAppearance.update(appearance);
    vehicleDoorNodes = [];
    officialDoorController = official ? createOfficialDoorController(model, gltf.animations) : undefined;
    if (!official) model.traverse(child => {
      if (child.userData.partType === 'door' && /^Door_(FL|FR|RL|RR)$/.test(child.name)) vehicleDoorNodes.push(child);
    });
    vehicleModelBasePositionY = model.position.y;
    vehicleModelPivot?.add(model);
    vehicleModelPivot?.updateMatrixWorld(true);
    detectVehicleWheelMeshes(model, new THREE.Box3().setFromObject(model));
    updateVehicleVisualState(true);
    vehicleWeather?.setImpactSurface(model);
    resizeVehicleViewer();
    resolveModelReady(true);
  }).catch((error: unknown) => {
    if (vehicleRenderer !== activeRenderer) return;
    console.error(error);
    state.visualError = '车辆模型加载失败';
    state.visualLoading = false;
    resolveModelReady(false);
  });

  resizeHandler = () => {
    resizeVehicleViewer();
  };
  window.addEventListener('resize', resizeHandler);
  vehicleViewerInitialized = true;
  startVehicleRenderLoop();
}

function resizeVehicleViewer() {
  if (!vehicleVisualRef.value || !vehicleRenderer || !vehicleCamera) {
    return;
  }
  const width = vehicleVisualRef.value.clientWidth || 640;
  const height = vehicleVisualRef.value.clientHeight || 420;
  const ratio = vehiclePixelRatio(width, height);
  if (Math.abs(vehicleRenderer.getPixelRatio() - ratio) > .01) vehicleRenderer.setPixelRatio(ratio);
  vehicleRenderer.setSize(width, height);
  vehicleCamera.aspect = width / height;
  vehicleCamera.updateProjectionMatrix();
  renderVehicleViewer();
}

let lastShadowUpdate = 0;
function renderVehicleViewer(refreshShadows = true) {
  if (!vehicleRenderer || !vehicleScene || !vehicleCamera) {
    return;
  }
  if (refreshShadows) vehicleRenderer.shadowMap.needsUpdate = true;
  if (streetReflectionsReady && streetReflectionsDirty && vehicleModelRoot) {
    streetReflectionsDirty=false;
    vehicleScene.updateMatrixWorld(true);
    const position=vehicleModelRoot.getWorldPosition(new THREE.Vector3());position.y+=1.3;
    const reflection=captureStreetReflections(vehicleRenderer,vehicleScene,vehicleModelRoot,position);
    vehicleScene.environment=reflection.texture;
    vehicleEnvironment?.dispose();vehicleEnvironment=reflection;
  }
  vehicleRenderer.render(vehicleScene, vehicleCamera);
}

function updateVehicleMotion(now: number) {
  const profile = getVehicleMotionProfile();
  vehicleStreet?.setParked(!profile.moving);
  const deltaSec = vehicleMotionState.lastFrameTime ? Math.min((now - vehicleMotionState.lastFrameTime) / 1000, 0.05) : 0;
  vehicleMotionState.lastFrameTime = now;
  vehicleWeather?.update(deltaSec,currentVehicleSpeedKmh.value/3.6);
  wipersMoving = vehicleWipers?.update(deltaSec, activeWeather.value === 'rain') ?? false;
  for (const door of vehicleDoorNodes) {
    const angle = modelDoorsOpen.value ? Number(door.userData.openAngle) || 0 : 0;
    door.rotation.y = THREE.MathUtils.damp(door.rotation.y, angle, 9, deltaSec);
  }
  officialDoorController?.update(deltaSec, modelDoorsOpen.value);

  if (!profile.active) {
    vehicleMotionState.roadOffset = 0;
    vehicleRoadMesh?.userData.updateTravel?.(0);
    vehicleMotionState.bobPhase = 0;
    if (vehicleRoadMesh) {
      const material = vehicleRoadMesh.material as THREE.MeshStandardMaterial;
      const parkTexture = vehicleRoadMesh.userData.parkTexture as THREE.Texture | null | undefined;
      if (parkTexture && material.map !== parkTexture) {
        material.map = parkTexture;
        material.color.set('#ffffff');
        material.needsUpdate = true;
      }
      if (material.map) {
        material.map.offset.y = 0;
      }
    }
    if (vehicleModelRoot) {
      vehicleModelRoot.position.y = vehicleModelBasePositionY;
    }
    return;
  }

  if (vehicleRoadMesh) {
    const material = vehicleRoadMesh.material as THREE.MeshStandardMaterial;
    const driveTexture = vehicleRoadMesh.userData.driveTexture as THREE.Texture | null | undefined;
    if (driveTexture && material.map !== driveTexture) {
      material.map = driveTexture;
      material.color.set('#ffffff');
      material.needsUpdate = true;
    }
    if (profile.moving) {
      vehicleMotionState.roadOffset += deltaSec * profile.roadSpeed * profile.direction;
    }
    if (material.map) {
      material.map.offset.y = vehicleMotionState.roadOffset;
      vehicleRoadMesh.userData.updateTravel?.(vehicleMotionState.roadOffset * ROAD_TEXTURE_LENGTH);
    }
  }

  if (!profile.moving) {
    return;
  }

  // Road texture repeats once per street block; scenery uses that same physical displacement.
  vehicleStreet?.advance(deltaSec * profile.roadSpeed * ROAD_TEXTURE_LENGTH * profile.direction);

  vehicleWheelMeshes.forEach(({ mesh, axis, direction }) => {
    mesh.rotation[axis] += deltaSec * profile.wheelSpeed * profile.direction * direction;
  });
}

function startVehicleRenderLoop() {
  if (vehicleRenderLoopFrame !== null) {
    return;
  }
  const frame = () => {
    vehicleRenderLoopFrame = window.requestAnimationFrame(frame);
    if (!vehicleRenderer || !vehicleScene || !vehicleCamera) {
      return;
    }
    if (!state.documentVisible || state.activeTab !== 'status') return;
    const now = performance.now();
    updateVehiclePoseTween(now);
    updateVehicleMotion(now);
    const cameraUpdated = vehicleControls?.update();
    const cameraChanged = cameraUpdated || vehicleCameraDirty;
    vehicleCameraDirty = false;
    const doorsMoving = officialDoorController?.moving(modelDoorsOpen.value) || vehicleDoorNodes.some(door => Math.abs(door.rotation.y - (modelDoorsOpen.value ? Number(door.userData.openAngle) || 0 : 0)) > .002);
    const moving = getVehicleMotionProfile().moving || doorsMoving || !!vehiclePoseTween;
    const weatherMoving = activeWeather.value === 'rain' || activeWeather.value === 'snow' || wipersMoving;
    if (!moving && !weatherMoving && !cameraChanged && !vehicleViewTween && !streetReflectionsDirty) return;
    if (moving && now - lastShadowUpdate >= 80) {
      vehicleRenderer.shadowMap.needsUpdate = true;
      lastShadowUpdate = now;
    }
    renderVehicleViewer(false);
  };
  vehicleRenderLoopFrame = window.requestAnimationFrame(frame);
}

function stopVehicleRenderLoop() {
  if (vehicleRenderLoopFrame !== null) {
    window.cancelAnimationFrame(vehicleRenderLoopFrame);
    vehicleRenderLoopFrame = null;
  }
}

function normalizeAngleDelta(angle: number) {
  let normalized = angle;
  while (normalized > Math.PI) {
    normalized -= Math.PI * 2;
  }
  while (normalized < -Math.PI) {
    normalized += Math.PI * 2;
  }
  return normalized;
}

function stopVehiclePoseTween() {
  vehiclePoseTween = null;
}

function updateVehiclePoseTween(now: number) {
  if (!vehicleModelPivot || !vehiclePoseTween) {
    return;
  }
  const progress = Math.min((now - vehiclePoseTween.startTime) / vehiclePoseTween.durationMs, 1);
  const eased = easeInOutCubic(progress);
  const delta = normalizeAngleDelta(vehiclePoseTween.toRotationY - vehiclePoseTween.fromRotationY);
  vehicleModelPivot.rotation.y = vehiclePoseTween.fromRotationY + delta * eased;
  if (progress >= 1) {
    vehicleModelPivot.rotation.y = vehiclePoseTween.toRotationY;
    stopVehiclePoseTween();
  }
}

function animateVehiclePose(toRotationY: number, durationMs = 720) {
  if (!vehicleModelPivot) {
    return;
  }
  stopVehiclePoseTween();
  vehiclePoseTween = {
    startTime: performance.now(),
    durationMs,
    fromRotationY: vehicleModelPivot.rotation.y,
    toRotationY,
  };
}

function updateVehicleVisualState(immediate = false) {
  if (!vehicleModelPivot) {
    return;
  }
  const targetRotationY = getVehicleOrientationByShift(currentShiftState.value);
  const preset = getVehicleCameraPresetByShift(currentShiftState.value);
  if (vehicleResetViewTimer !== null) {
    window.clearTimeout(vehicleResetViewTimer);
    vehicleResetViewTimer = null;
  }
  if (immediate) {
    stopVehiclePoseTween();
    vehicleModelPivot.rotation.y = targetRotationY;
    if (vehicleCamera && vehicleControls) {
      vehicleCamera.position.copy(preset.position);
      vehicleControls.target.copy(preset.target);
      vehicleControls.update();
    }
  } else {
    animateVehiclePose(targetRotationY);
    animateVehicleView(preset.position, preset.target, 720);
  }
  renderVehicleViewer();
}

function scheduleVehicleViewReset() {
  if (vehicleResetViewTimer !== null) {
    window.clearTimeout(vehicleResetViewTimer);
  }
  vehicleResetViewTimer = window.setTimeout(() => {
    resetVehicleView();
  }, 3000);
}

function easeInOutCubic(progress: number) {
  return progress < 0.5
    ? 4 * progress * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 3) / 2;
}

function stopVehicleViewTween() {
  if (vehicleAnimationFrame !== null) {
    window.cancelAnimationFrame(vehicleAnimationFrame);
    vehicleAnimationFrame = null;
  }
  vehicleViewTween = null;
}

function animateVehicleView(toPosition: THREE.Vector3, toTarget: THREE.Vector3, durationMs = 900) {
  if (!vehicleCamera || !vehicleControls) {
    return;
  }
  stopVehicleViewTween();
  vehicleViewTween = {
    startTime: performance.now(),
    durationMs,
    fromPosition: vehicleCamera.position.clone(),
    toPosition: toPosition.clone(),
    fromTarget: vehicleControls.target.clone(),
    toTarget: toTarget.clone(),
  };

  const step = (now: number) => {
    if (!vehicleCamera || !vehicleControls || !vehicleViewTween) {
      stopVehicleViewTween();
      return;
    }
    const progress = Math.min((now - vehicleViewTween.startTime) / vehicleViewTween.durationMs, 1);
    const eased = easeInOutCubic(progress);
    vehicleCamera.position.lerpVectors(vehicleViewTween.fromPosition, vehicleViewTween.toPosition, eased);
    vehicleControls.target.lerpVectors(vehicleViewTween.fromTarget, vehicleViewTween.toTarget, eased);
    if (progress < 1) {
      vehicleAnimationFrame = window.requestAnimationFrame(step);
      return;
    }
    stopVehicleViewTween();
  };

  vehicleAnimationFrame = window.requestAnimationFrame(step);
}

function resetVehicleView() {
  const preset = getVehicleCameraPresetByShift(currentShiftState.value);
  animateVehicleView(preset.position, preset.target);
}

function disposeVehicleViewer() {
  vehicleCameraDirty = false;
  vehicleLights?.dispose(); vehicleLights = undefined;
  vehicleWeather?.dispose();vehicleWeather=undefined;
  vehicleWipers = undefined; wipersMoving = false;
  vehicleStreet?.dispose(); vehicleStreet = undefined;
  sunLight?.shadow.dispose(); sunLight = undefined; skyLight = undefined;
  streetReflectionsReady=false;streetReflectionsDirty=true;
  vehicleEnvironment?.dispose(); vehicleEnvironment = null;
  vehicleSky?.geometry.dispose(); vehicleSky?.material.dispose(); vehicleSky = null;
  vehicleAppearance?.dispose(); vehicleAppearance = undefined;
  if (vehicleResetViewTimer !== null) {
    window.clearTimeout(vehicleResetViewTimer);
    vehicleResetViewTimer = null;
  }
  stopVehicleViewTween();
  stopVehiclePoseTween();
  stopVehicleRenderLoop();
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler);
    resizeHandler = null;
  }
  if (vehicleControls) {
    vehicleControls.dispose();
    vehicleControls = null;
  }
  if (vehicleRenderer) {
    vehicleRenderer.forceContextLoss();
    vehicleRenderer.dispose();
    vehicleRenderer.domElement.remove();
  }
  if (vehicleRoadMesh) {
    vehicleRoadMesh.userData.disposeDetails?.();
    vehicleRoadMesh.geometry.dispose();
    const material = vehicleRoadMesh.material as THREE.MeshStandardMaterial;
    vehicleRoadMesh.userData.driveTexture?.dispose();
    vehicleRoadMesh.userData.parkTexture?.dispose();
    material.alphaMap?.dispose();
    material.bumpMap?.dispose();
    vehicleRoadMesh.children.forEach(child => {
      const mesh = child as THREE.Mesh;
      mesh.geometry?.dispose();
      (mesh.material as THREE.Material)?.dispose();
    });
    material.dispose();
  }
  if (vehicleModelRoot) {
    vehicleModelRoot.traverse((child: THREE.Object3D) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.geometry?.dispose();
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        materials.forEach((material: THREE.Material) => material?.dispose());
      }
    });
  }
  vehicleScene = null;
  vehicleCamera = null;
  vehicleRenderer = null;
  vehicleModelRoot = null;
  vehicleModelPivot = null;
  vehicleRoadMesh = null;
  vehicleWheelMeshes = [];
  vehicleDoorNodes = [];
  officialDoorController = undefined;
  modelDoorsOpen.value = false;
  vehicleModelBasePositionY = 0;
  vehicleMotionState = {
    lastFrameTime: 0,
    roadOffset: 0,
    bobPhase: 0,
  };
  vehicleViewerInitialized = false;
}

function logoutTesla() {
  post('/api/tesla/auth/logout', {}, '断开 Tesla 连接失败').then(() => {
    state.status.authorized = false;
    state.status.profile = null;
    state.vehicles = [];
    state.trackPoints = [];
    state.trips = [];
    state.latestSample = null;
    renderTrackOnMap();
    ElMessage.success('Tesla 已断开连接');
  });
}

function initMap() {
  if (mapInstance || trackMapLoading || teslaPageDisposed || state.activeTab !== 'track') return;
  const generation = ++trackMapGeneration;
  trackMapLoading = true;
  getAMap().then((AMap) => {
    if (teslaPageDisposed || generation !== trackMapGeneration || state.activeTab !== 'track') return;
    gAMap = AMap;
    if (!mapContainer.value) {
      return;
    }
    mapInstance = new AMap.Map(mapContainer.value, {
      zoom: 11,
      center: [120.2169, 30.2783],
      mapStyle: 'amap://styles/whitesmoke',
      viewMode: '2D',
    });
    state.mapReady = true;
    renderTrackOnMap();
  }).catch((error) => {
    if (teslaPageDisposed || generation !== trackMapGeneration) return;
    console.error(error);
    state.mapError = '高德地图初始化失败，请检查 Key 配置';
  }).finally(() => {
    if (generation === trackMapGeneration) trackMapLoading = false;
  });
}
function destroyTrackMap() {
  trackMapGeneration++;
  trackMapLoading = false;
  trackRenderVersion++;
  mapInstance?.destroy?.();
  mapInstance = null;
  gAMap = null;
  polylines = [];
  vehicleMarker = null;
  state.mapReady = false;
}

function renderTrackOnMap() {
  if (!mapInstance || !gAMap) {
    return;
  }
  const renderVersion = ++trackRenderVersion;
  if (polylines.length > 0) {
    mapInstance.remove(polylines);
    polylines = [];
  }
  if (vehicleMarker) {
    mapInstance.remove(vehicleMarker);
    vehicleMarker = null;
  }

  const rawPoints = state.trackPoints
    .filter((item: any) => item.longitude != null && item.latitude != null)
    .map((item: any) => ({
      point: [Number(item.longitude), Number(item.latitude)],
      coordType: String(item.coord_type || '').toLowerCase(),
      timestampMs: Number(item.timestamp_ms || 0),
    }));

  const drawPoints = (points: any[]) => {
    if (renderVersion !== trackRenderVersion) {
      return;
    }
    const segments: any[][] = [];
    let currentSegment: any[] = [];
    const segmentGapMs = 10 * 60 * 1000;

    points.forEach((item: any, index: number) => {
      const prev = points[index - 1];
      const gapMs = prev ? Math.abs((item.timestampMs || 0) - (prev.timestampMs || 0)) : 0;
      if (currentSegment.length > 0 && gapMs > segmentGapMs) {
        segments.push(currentSegment);
        currentSegment = [];
      }
      currentSegment.push(item.point);
    });
    if (currentSegment.length > 0) {
      segments.push(currentSegment);
    }

    polylines = segments
      .filter((segment) => segment.length > 1)
      .map((segment) => new gAMap.Polyline({
        path: segment,
        strokeColor: '#409EFF',
        strokeWeight: 6,
        lineJoin: 'round',
        lineCap: 'round',
      }));

    if (polylines.length > 0) {
      mapInstance.add(polylines);
    }

    const latestPoint = points[points.length - 1]?.point;
    if (latestPoint) {
      vehicleMarker = new gAMap.Marker({
        position: latestPoint,
        title: selectedVehicle.value?.displayName || state.selectedVin,
      });
      mapInstance.add(vehicleMarker);
      mapInstance.setFitView([vehicleMarker, ...polylines].filter(Boolean), false, [80, 80, 80, 80]);
    }
  };

  if (rawPoints.length === 0) {
    return;
  }

  const finalPoints = rawPoints.map((item) => ({ ...item }));
  const gpsPoints = rawPoints
    .map((item, index) => ({ ...item, index }))
    .filter((item) => !['gcj', 'gcj02', 'gcj-02'].includes(item.coordType));

  if (gpsPoints.length === 0 || typeof gAMap.convertFrom !== 'function') {
    drawPoints(finalPoints);
    return;
  }

  gAMap.convertFrom(gpsPoints.map((item) => item.point), 'gps', (status: string, result: any) => {
    if (renderVersion !== trackRenderVersion) {
      return;
    }
    if (status === 'complete' && result?.locations?.length === gpsPoints.length) {
      result.locations.forEach((item: any, idx: number) => {
        finalPoints[gpsPoints[idx].index] = {
          ...finalPoints[gpsPoints[idx].index],
          point: [item.lng, item.lat],
        };
      });
    }
    drawPoints(finalPoints);
  });
}

onMounted(() => {
  geoLocation.addListener('tesla-status-speed', receiveGpsSpeed);
  geoLocation.addErrorListener('tesla-status-speed', handleGpsSpeedError);
  if (navigator.geolocation) {
    geoLocation.init();
    geoLocation.refresh();
    // Match the H5 API test on the Debug page, including its high-accuracy watch.
    try {
      gpsSpeedWatchId = navigator.geolocation.watchPosition(position => {
        const { coords } = position;
        receiveGpsSpeed({ latitude: coords.latitude, longitude: coords.longitude,
          accuracy: coords.accuracy, speed: coords.speed, timestamp: position.timestamp, source: 'gps',
          altitude: coords.altitude, altitudeAccuracy: coords.altitudeAccuracy, heading: coords.heading });
      }, handleGpsSpeedError, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    } catch { gpsSpeedMessage.value = '连续定位不可用'; }
  }
  else gpsSpeedMessage.value = window.isSecureContext ? '浏览器不支持定位' : '定位需要 HTTPS';
  void refreshWeather();weatherTimer=window.setInterval(()=>void refreshWeather(),15*60*1000);
  document.addEventListener('visibilitychange', handleDocumentVisibilityChange);
  Promise.all([loadSettings(), refreshActiveTabData({ immediate: true })]).finally(() => {
    restartAutoSyncTimer();
  });
  if (state.activeTab === 'track') nextTick(initMap);
  nextTick(() => {
    if (state.activeTab === 'status') {
      initVehicleViewer();
      startVehicleRenderLoop();
      resizeVehicleViewer();
      updateVehicleVisualState(true);
    }
    observePageExposure();
  });
});

onBeforeUnmount(() => {
  teslaPageDisposed = true;
  destroyTrackMap();
  geoLocation.removeListener('tesla-status-speed');
  if (gpsSpeedWatchId !== undefined) navigator.geolocation?.clearWatch(gpsSpeedWatchId);
  window.clearTimeout(gpsSpeedExpiry);
  weatherRequest?.abort();weatherRequest=undefined;window.clearInterval(weatherTimer);
  document.removeEventListener('visibilitychange', handleDocumentVisibilityChange);
  stopAutoSyncTimer();
  if (pageObserver) {
    pageObserver.disconnect();
    pageObserver = null;
  }
  disposeVehicleViewer();
});

watch(()=>[state.documentVisible,state.pageExposed,state.activeTab],()=>void refreshWeather());
watch(weatherMode,()=>{try{localStorage.setItem('tmc.tesla.weather',weatherMode.value);}catch{}void refreshWeather();});
watch(activeWeather,()=>updateSceneLighting());
watch(()=>[state.latestSample?.latitude==null?'':Number(state.latestSample.latitude).toFixed(1),state.latestSample?.longitude==null?'':Number(state.latestSample.longitude).toFixed(1)].join(','),()=>void refreshWeather());

watch(() => state.activeTab, (tabName) => {
  restartAutoSyncTimer();
  refreshActiveTabData({ immediate: true, includeMeta: tabName !== 'status' });
  if (tabName === 'status') {
    nextTick(() => {
      initVehicleViewer();
      startVehicleRenderLoop();
      resizeVehicleViewer();
      updateVehicleVisualState(true);
    });
  } else {
    stopVehicleRenderLoop();
  }
  if (tabName === 'track') {
    nextTick(() => {
      initMap();
      if (mapInstance && typeof mapInstance.resize === 'function') {
        mapInstance.resize();
      }
      renderTrackOnMap();
    });
  } else destroyTrackMap();
});

watch(currentShiftState, () => {
  updateVehicleVisualState();
});
</script>

<template>
  <div ref="pageRef" class="tesla-page" :class="{ 'tesla-page--visual': state.activeTab === 'status' }">
    <section class="tesla-tabs-card">
      <el-tabs v-model="state.activeTab" class="tesla-tabs">
        <el-tab-pane label="车辆状态" name="status">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card tesla-card--visual" v-loading="state.visualLoading" element-loading-text="正在加载车辆、场景与贴图…" element-loading-background="#111c26">
              <div v-if="state.visualError" class="map-empty">{{ state.visualError }}</div>
              <div v-else class="vehicle-visual-shell" :class="{ 'vehicle-visual-shell--loading': state.visualLoading }" :aria-busy="state.visualLoading">
                <div class="vehicle-speed-hud" aria-label="当前 GPS 车速" :title="gpsSpeedMessage || '车机 GPS 速度'">
                  <span class="vehicle-speed-hud__label">GPS 车速</span>
                  <div class="vehicle-speed-hud__reading">
                    <strong>{{ gpsSpeedKmh === null ? '—' : Math.round(gpsSpeedKmh) }}</strong>
                    <span>km/h</span>
                  </div>
                  <small v-if="gpsSpeedKmh === null" class="vehicle-speed-hud__hint">{{ gpsSpeedMessage }}</small>
                </div>
                <div class="vehicle-visual-overlay">
                  <div class="vehicle-overlay-card vehicle-overlay-card--weather" :title="weatherMode === 'auto' ? weatherStatus + ' · Open-Meteo' : '手动场景天气'">
                    <TeslaWeatherIcon :weather="weatherAvailable ? activeWeather : undefined" />
                    <div class="vehicle-weather-summary">
                      <span>{{ weatherMode === 'auto' ? '当地天气' : '场景天气' }}</span>
                      <strong>{{ weatherDisplayLabel }}</strong>
                    </div>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>当前档位</span>
                    <strong :class="vehicleVisualStatus.accent">{{ vehicleVisualStatus.label }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>当前车况</span>
                    <strong>{{ state.latestSample?.vehicle_state || selectedVehicle?.state || '-' }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>总公里数</span>
                    <strong>{{ state.latestSample?.odometer != null ? `${Math.round(Number(state.latestSample.odometer))} ${state.latestSample.distance_unit || 'km'}` : '-' }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>电量</span>
                    <strong>{{ state.latestSample?.battery_level != null ? `${state.latestSample.battery_level}%` : '-' }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>车内温度</span>
                    <strong>{{ state.latestSample?.inside_temp != null ? `${state.latestSample.inside_temp}°C` : '-' }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>车外温度</span>
                    <strong>{{ state.latestSample?.outside_temp != null ? `${state.latestSample.outside_temp}°C` : '-' }}</strong>
                  </div>
                </div>
                <div ref="vehicleVisualRef" class="vehicle-visual-stage"></div>
                <div class="vehicle-map-controls" role="toolbar" aria-label="车辆场景选项">
                <button class="model-door-preview" :aria-pressed="modelDoorsOpen" :disabled="state.visualLoading"
                  title="仅演示模型，不控制真实车辆" @click="modelDoorsOpen = !modelDoorsOpen">
                  {{ modelDoorsOpen ? '收起车门' : '展开车门' }}
                </button>
                  <button :aria-pressed="headlights" aria-label="切换车辆灯光" @click="headlights = !headlights">{{ headlights ? '车灯 · 开' : '车灯 · 关' }}</button>
                  <button :aria-pressed="sceneNight" aria-label="切换昼夜场景" @click="sceneNight = !sceneNight">{{ sceneNight ? '夜间' : '白天' }}</button>
                  <el-popover v-model:visible="weatherMenuOpen" trigger="click" placement="top-end" :width="188" :offset="12" :show-arrow="false" popper-class="vehicle-weather-popper">
                    <template #reference>
                      <button class="vehicle-weather-trigger" type="button" aria-label="选择场景天气" aria-haspopup="menu" :aria-expanded="weatherMenuOpen" :title="weatherMode === 'auto' ? weatherStatus + ' · Open-Meteo' : '场景天气'">
                        天气 · {{ weatherMode === 'auto' ? '自动' : weatherLabels[weatherMode] }} <span class="vehicle-weather-caret" aria-hidden="true"></span>
                      </button>
                    </template>
                    <div class="vehicle-weather-options" role="menu" aria-label="场景天气">
                      <button v-for="choice in weatherChoices" :key="choice.value" type="button" role="menuitemradio" :aria-checked="weatherMode === choice.value" @click="chooseWeather(choice.value)">
                        {{ choice.label }} <span v-if="weatherMode === choice.value" class="vehicle-weather-selected" aria-hidden="true"></span>
                      </button>
                    </div>
                  </el-popover>
                  <el-popover v-model:visible="appearanceOpen" trigger="click" placement="top-end" :width="300">
                    <template #reference><button aria-label="自定义车辆外观">车辆外观</button></template>
                    <div class="vehicle-appearance-editor">
                      <strong>车辆外观</strong>
                      <label>车衣颜色 <input v-model="appearance.color" type="color" aria-label="车衣颜色" /></label>
                      <div class="vehicle-paint-swatches">
                        <button v-for="item in [['珍珠白','#eaf0f3'],['曜石黑','#202328'],['冷光银','#9ea7af'],['深海蓝','#163b70'],['烈焰红','#a51c30'],['松石绿','#467f78']]" :key="item[1]" :title="item[0]" :aria-label="item[0]" :aria-pressed="appearance.color===item[1]" :style="{background:item[1]}" @click="appearance.color=item[1]"></button>
                      </div>
                      <label>车衣材质 <el-select v-model="appearance.finish" aria-label="车衣材质"><el-option v-for="finish in paintFinishes" :key="finish.value" :label="finish.label" :value="finish.value" /></el-select></label>
                      <label>牌照文字 <el-input v-model="appearance.plate" aria-label="牌照文字" maxlength="10" placeholder="例如：沪AD12345" @change="appearance.plate=normalizeAppearance(appearance).plate" /></label>
                      <label>牌照样式 <el-select v-model="appearance.plateStyle" aria-label="牌照样式"><el-option label="新能源绿牌" value="green"/><el-option label="蓝牌" value="blue"/><el-option label="黑牌" value="black"/><el-option label="白牌" value="white"/></el-select></label>
                      <small>{{ appearanceSaveError ? '浏览器未能保存设置，刷新后可能丢失' : '实时预览，自动保存在当前浏览器' }}</small>
                      <el-button @click="Object.assign(appearance, defaultAppearance)">恢复默认</el-button>
                    </div>
                  </el-popover>

                </div>
              </div>
            </article>
          </section>
        </el-tab-pane>

        <el-tab-pane label="轨迹" name="track">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card tesla-card--map" v-loading="state.tripTrackLoading">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">Track</p>
                  <h2>轨迹</h2>
                </div>
                <div class="button-row">
                  <div class="status-pill">{{ state.trackPoints.length }} 点</div>
                  <el-button v-if="state.selectedTrip" round @click="showAllTrack">查看全部轨迹</el-button>
                </div>
              </div>
              <div v-if="state.selectedTrip" class="trip-filter-banner">
                当前显示行程：{{ formatTimestamp(state.selectedTrip.startTimeMs) }} - {{ formatTimestamp(state.selectedTrip.endTimeMs) }}
              </div>
              <div v-if="state.mapError" class="map-empty">{{ state.mapError }}</div>
              <div v-else class="map-stage">
                <div ref="mapContainer" class="map-container"></div>
                <div v-if="state.trackPoints.length === 0" class="map-empty map-empty--overlay">当前范围没有轨迹点</div>
              </div>
            </article>
          </section>
        </el-tab-pane>

        <el-tab-pane label="行程" name="trip">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card" v-loading="state.tripsLoading">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">Trips</p>
                  <h2>行程</h2>
                </div>
              </div>
              <div v-if="state.trips.length === 0" class="trip-empty">
                当前车辆还没有可展示的行程记录
              </div>
              <div v-else class="trip-list">
                <div v-for="trip of state.trips" :key="`${trip.startTimeMs}-${trip.endTimeMs}`" class="trip-item">
                  <div class="trip-main">
                    <div>
                      <span class="trip-label">出发</span>
                      <strong>{{ formatTimestamp(trip.startTimeMs) }}</strong>
                    </div>
                    <div>
                      <span class="trip-label">结束</span>
                      <strong>{{ formatTimestamp(trip.endTimeMs) }}</strong>
                    </div>
                  </div>
                  <div class="trip-metrics">
                    <div class="trip-metric">
                      <span>时长</span>
                      <strong>{{ formatDuration(trip.durationSec) }}</strong>
                    </div>
                    <div class="trip-metric">
                      <span>里程</span>
                      <strong>{{ trip.distanceKm }} km</strong>
                    </div>
                    <div class="trip-metric">
                      <span>最高时速</span>
                      <strong>{{ trip.maxSpeed }} {{ trip.speedUnit || 'km/h' }}</strong>
                    </div>
                    <div class="trip-metric">
                      <span>电量变化</span>
                      <strong>{{ trip.startBatteryLevel ?? '-' }}% → {{ trip.endBatteryLevel ?? '-' }}%</strong>
                    </div>
                    <div class="trip-metric">
                      <span>轨迹点</span>
                      <strong>{{ trip.pointCount }}</strong>
                    </div>
                  </div>
                  <div class="trip-actions">
                    <el-button round @click="openTripTrack(trip)">查看轨迹</el-button>
                    <el-button type="danger" plain round @click="deleteTrip(trip)">删除行程</el-button>
                  </div>
                </div>
              </div>
            </article>
          </section>
        </el-tab-pane>

        <el-tab-pane label="原始数据" name="raw">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card" v-loading="state.rawLoading">
              <div v-if="state.rawRows.length === 0" class="trip-empty">
                当前车辆还没有原始样本记录
              </div>
              <template v-else>
                <div ref="rawTableWrapRef" class="raw-table-wrap">
                  <el-table ref="rawTableRef" :data="state.rawRows" size="small" class="raw-table">
                    <el-table-column
                      v-for="key of rawPreviewColumns"
                      :key="key"
                      :prop="key"
                      :label="key"
                      :fixed="key === 'timestamp_ms' ? 'left' : false"
                      min-width="140"
                      show-overflow-tooltip
                    >
                      <template #default="{ row }">{{ formatRawCell(row, key) }}</template>
                    </el-table-column>
                    <el-table-column label="详情" fixed="right" width="100">
                      <template #default="{ row }">
                        <el-button link type="primary" @click.stop="openRawRowDetail(row)">详情</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <div class="raw-pagination">
                  <el-pagination
                    background
                    layout="prev, pager, next"
                    :page-size="state.rawPageSize"
                    :total="state.rawTotal"
                    :current-page="state.rawPage"
                    @current-change="handleRawPageChange"
                  />
                </div>
              </template>
            </article>
          </section>
        </el-tab-pane>

        <el-tab-pane label="设置" name="settings">
          <section class="tesla-grid">
            <article class="tesla-hero">
              <div>
                <p class="tesla-kicker">Tesla Fleet API</p>
                <h1>Tesla 状态与轨迹</h1>
                <p class="tesla-copy">当前是兼容 TeslaMate 个人用法的 Owner API 模式：手动填 access token / refresh token，后端定时拉车辆状态和轨迹。默认按 TeslaMate 文档的 China 配置工作。</p>
              </div>
              <div class="button-row">
                <el-button round @click="loadStatus">刷新授权状态</el-button>
                <el-button type="primary" round :loading="state.syncLoading" @click="syncVehicles(true)">立即同步</el-button>
              </div>
            </article>

            <article class="tesla-card" v-loading="state.settingsLoading">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">Token</p>
                  <h2>Tesla Token</h2>
                </div>
              </div>
              <div class="form-grid">
                <div class="field field-wide">
                  <span>Access Token</span>
                  <el-input v-model="state.settings.accessToken" type="textarea" :rows="3" :placeholder="state.settings.hasAccessToken ? '已配置，留空则不修改' : '粘贴 Tesla access token'" />
                </div>
                <div class="field field-wide">
                  <span>Refresh Token</span>
                  <el-input v-model="state.settings.refreshToken" type="textarea" :rows="3" :placeholder="state.settings.hasRefreshToken ? '已配置，留空则不修改' : '粘贴 Tesla refresh token'" />
                </div>
              </div>
              <p class="helper-text">只需要填写 `Access Token` 和 `Refresh Token`。默认接口参数已经内置，并按 TeslaMate 文档的 China 配置工作；保存时会先校验 `Refresh Token`，已保存的 token 会直接回填到输入框里。</p>
              <div class="button-row">
                <el-button type="primary" round @click="saveSettings">保存配置</el-button>
              </div>
            </article>

            <article class="tesla-card" v-loading="state.storageLoading">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">SQLite</p>
                  <h2>存储管理</h2>
                </div>
                <div class="status-pill" :class="{ 'status-pill--ok': state.storage.backgroundSyncRunning }">
                  {{ state.storage.backgroundSyncRunning ? '后台采集中' : '未运行' }}
                </div>
              </div>
              <div class="meta-stack">
                <div class="meta-line"><span>数据库路径</span><strong>{{ state.storage.dbPath || '-' }}</strong></div>
                <div class="meta-line"><span>当前占用</span><strong>{{ state.storage.dbSizeMb }} MB</strong></div>
                <div class="meta-line"><span>样本数</span><strong>{{ state.storage.sampleCount }}</strong></div>
                <div class="meta-line"><span>车辆缓存数</span><strong>{{ state.storage.vehicleCount }}</strong></div>
                <div class="meta-line"><span>最早记录</span><strong>{{ formatTimestamp(state.storage.oldestTimestampMs) }}</strong></div>
                <div class="meta-line"><span>最新记录</span><strong>{{ formatTimestamp(state.storage.latestTimestampMs) }}</strong></div>
                <div class="meta-line"><span>后台轮询</span><strong>行驶 2.5 秒 / 充电 5 秒 / 在线 60 秒 / 休眠 60 秒</strong></div>
                <div class="meta-line"><span>当前有效轮询</span><strong>{{ state.storage.effectivePollIntervalSec || 0 }} 秒</strong></div>
                <div class="meta-line"><span>当前退避</span><strong>{{ state.storage.currentBackoffSec || 0 }} 秒</strong></div>
                <div class="meta-line"><span>当前采集模式</span><strong>{{ state.storage.collectionMode || 'rest' }}</strong></div>
                <div class="meta-line"><span>流式阶段</span><strong>{{ state.storage.streamPhase || 'idle' }}</strong></div>
                <div class="meta-line"><span>最近流式结果</span><strong>{{ state.storage.lastStreamResult || '-' }}</strong></div>
                <div class="meta-line"><span>记录优化</span><strong>60 秒内相同样本会自动合并</strong></div>
                <div class="meta-line"><span>Token 续期</span><strong>离失效前 30 分钟自动刷新</strong></div>
              </div>
              <div class="form-grid">
                <div class="field">
                  <span>最长保留（天）</span>
                  <el-input-number v-model="state.settings.retentionDays" :min="1" :max="365" />
                </div>
                <div class="field">
                  <span>最大空间（MB）</span>
                  <el-input-number v-model="state.settings.maxStorageMb" :min="16" :max="8192" :step="16" />
                </div>
              </div>
              <div class="button-row">
                <el-button round @click="loadStorage">刷新状态</el-button>
                <el-button type="danger" plain round @click="clearStorage">清理记录</el-button>
              </div>
            </article>

            <article class="tesla-card" v-loading="state.statusLoading">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">Account</p>
                  <h2>授权状态</h2>
                </div>
                <div class="status-pill" :class="{ 'status-pill--ok': state.status.authorized }">
                  {{ state.status.authorized ? '已连接' : '未连接' }}
                </div>
              </div>
              <div class="meta-stack">
                <div class="meta-line"><span>是否已配置</span><strong>{{ state.status.configured ? '是' : '否' }}</strong></div>
                <div class="meta-line"><span>缓存可用</span><strong>{{ state.status.cacheAvailable ? `是（${state.status.cachedVehicleCount} 辆）` : '否' }}</strong></div>
                <div class="meta-line"><span>实时鉴权</span><strong>{{ state.status.liveAuthorized ? '成功' : '失败/未校验' }}</strong></div>
                <div class="meta-line"><span>最近同步</span><strong>{{ formatTimestamp(state.status.lastSyncAt * 1000) }}</strong></div>
                <div class="meta-line"><span>账户</span><strong>{{ state.status.profile?.email || '-' }}</strong></div>
                <div class="meta-line"><span>名称</span><strong>{{ state.status.profile?.fullName || '-' }}</strong></div>
                <div v-if="state.status.profileError?.message" class="meta-line"><span>实时状态</span><strong>{{ state.status.profileError.message }}</strong></div>
              </div>
              <div class="button-row">
                <el-button type="danger" plain round :disabled="!state.status.authorized" @click="logoutTesla">断开连接</el-button>
              </div>
            </article>
          </section>
        </el-tab-pane>
      </el-tabs>
    </section>

    <el-dialog v-model="state.rawDetailVisible" title="原始记录详情" width="min(960px, 92vw)">
      <div class="raw-detail-grid">
        <div v-for="item of rawDetailEntries" :key="item.key" class="raw-detail-item">
          <span>{{ item.key }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.tesla-page {
  display: flex;
  flex-direction: column;
  gap: var(--page-space);
  padding: var(--page-space);
}

.tesla-hero,
.tesla-card,
.tesla-tabs-card {
  border: 1px solid var(--color-border);
  min-width: 0;
  border-radius: var(--panel-radius);
  background: var(--color-surface);
  box-shadow: 0 14px 30px var(--color-shadow);
}

.tesla-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: var(--panel-space);
}

.tesla-kicker {
  margin: 0 0 6px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-soft);
}

.tesla-hero h1,
.card-head h2 {
  margin: 0;
  color: var(--color-heading);
}

.tesla-hero h1 {
  font-size: var(--title-size);
}

.card-head h2 {
  font-size: clamp(18px, 2vw, 24px);
}

.tesla-copy {
  margin: 8px 0 0;
  color: var(--color-text-soft);
  max-width: 720px;
}

.tesla-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 18px;
}

.tesla-grid--content {
  grid-template-columns: 1fr;
}

.tesla-card {
  padding: 22px;
}

.tesla-card--visual {
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.64)),
    linear-gradient(145deg, #edf2f7, #dbe4ee);
}

.tesla-tabs-card {
  padding: 8px 18px 18px;
}

:deep(.tesla-tabs .el-tabs__header) {
  margin: 0 0 12px;
}

:deep(.tesla-tabs .el-tabs__nav-wrap::after) {
  display: none;
}

:deep(.tesla-tabs .el-tabs__item) {
  height: 42px;
  padding: 0 18px;
  border-radius: 999px;
  color: var(--color-text-soft);
}

:deep(.tesla-tabs .el-tabs__item.is-active) {
  color: var(--color-accent);
}

:deep(.tesla-tabs .el-tabs__active-bar) {
  height: 3px;
  border-radius: 999px;
  background: var(--color-accent);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.button-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-wide {
  grid-column: 1 / -1;
}

.field span,
.state-box span,
.meta-line span {
  color: var(--color-text-soft);
  font-size: 13px;
}

.vehicle-overview {
  display: grid;
  grid-template-columns: minmax(260px, 1.5fr) repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.vehicle-main,
.overview-pill {
  min-height: 96px;
  border-radius: 20px;
  border: 1px solid var(--color-border);
  background: linear-gradient(180deg, var(--color-panel-muted), transparent);
}

.vehicle-main {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  padding: 16px 18px;
}

.vehicle-label {
  color: var(--color-text-soft);
  font-size: 13px;
}

.vehicle-select {
  width: 100%;
}

.overview-pill {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  padding: 16px 18px;
}

.overview-pill span {
  color: var(--color-text-soft);
  font-size: 13px;
}

.overview-pill strong {
  color: var(--color-heading);
  font-size: 22px;
  line-height: 1.2;
}

.meta-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
}

.meta-line code,
.meta-line strong {
  color: var(--color-heading);
}

.helper-text {
  margin: 12px 0 0;
  color: var(--color-text-soft);
  font-size: 14px;
  line-height: 1.6;
}

.meta-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.status-pill {
  min-width: 68px;
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--color-panel-muted);
  color: var(--color-text-soft);
  text-align: center;
  font-weight: 600;
}

.status-pill--ok {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.status-pill--warn {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.state-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.state-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
}

.state-box strong {
  font-size: 18px;
  color: var(--color-heading);
}

.trip-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.trip-item {
  border-radius: 20px;
  border: 1px solid var(--color-border);
  background: linear-gradient(180deg, var(--color-panel-muted), transparent);
  padding: 18px;
}

.trip-main {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 14px;
}

.trip-main strong,
.trip-metric strong {
  display: block;
  color: var(--color-heading);
}

.trip-label,
.trip-metric span {
  color: var(--color-text-soft);
  font-size: 13px;
}

.trip-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.trip-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.trip-metric {
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  padding: 12px 14px;
}

.trip-empty {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-soft);
  border-radius: 20px;
  border: 1px dashed var(--color-border);
  background: var(--color-panel-muted);
}

.tesla-card--map {
  min-height: 560px;
}

.vehicle-visual-shell {
  position: relative;
}

.model-door-preview {
  position: absolute;
  left: 18px;
  bottom: 16px;
  z-index: 3;
  padding: 9px 14px;
  color: var(--color-text);
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
  border-radius: 18px;
  cursor: pointer;
}
.model-door-preview[aria-pressed="true"] { color: #168fbb; border-color: #62b8d5; }
.model-door-preview:disabled { opacity: .5; cursor: default; }

.vehicle-visual-overlay {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(180px, calc(100% - 28px));
}

.vehicle-overlay-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
  text-align: right;
}

.vehicle-overlay-card span {
  color: rgba(74, 57, 40, 0.72);
  font-size: 11px;
  text-shadow: 0 2px 8px rgba(255, 255, 255, 0.88);
}

.vehicle-overlay-card strong {
  color: var(--color-heading);
  font-size: 15px;
  line-height: 1.2;
  text-shadow: 0 3px 12px rgba(255, 255, 255, 0.92);
}

.vehicle-overlay-card strong.status-pill--ok {
  color: var(--color-accent);
}

.vehicle-overlay-card strong.status-pill--warn {
  color: #b45309;
}

.vehicle-visual-stage {
  width: 100%;
  height: clamp(320px, calc(100vh - 280px), 620px);
  min-height: 320px;
  border-radius: 24px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.98), rgba(238, 244, 249, 0.76) 56%, rgba(220, 229, 238, 0.28) 100%),
    linear-gradient(180deg, rgba(243, 247, 251, 0.94) 0%, rgba(227, 235, 243, 0.12) 72%, rgba(227, 235, 243, 0.02) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.vehicle-visual-stage :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.map-stage {
  position: relative;
}

.map-container,
.map-empty {
  width: 100%;
  min-height: 500px;
  border-radius: 18px;
  overflow: hidden;
  background: var(--color-panel-muted);
}

.map-empty--overlay {
  position: absolute;
  inset: 0;
}

.trip-filter-banner {
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-panel-muted);
  color: var(--color-text-soft);
}

.raw-toolbar {
  margin-bottom: 12px;
  color: var(--color-text-soft);
  font-size: 13px;
}

.raw-table-wrap {
  margin-bottom: 16px;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-x;
}

.raw-table {
  min-width: max-content;
}

.raw-pagination {
  display: flex;
  justify-content: flex-end;
}

.raw-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.raw-detail-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
}

.raw-detail-item span {
  color: var(--color-text-soft);
  font-size: 12px;
}

.raw-detail-item strong {
  color: var(--color-heading);
  word-break: break-all;
}

.map-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-soft);
}

@media (max-width: 1100px) {
  .tesla-grid,
  .tesla-grid--content,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .vehicle-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .state-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .tesla-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 860px) {
  .vehicle-overview {
    grid-template-columns: 1fr;
  }

  .state-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trip-main,
  .trip-metrics {
    grid-template-columns: 1fr;
  }

  .vehicle-visual-stage {
    height: clamp(280px, calc(100vh - 260px), 420px);
    min-height: 280px;
  }

  .vehicle-visual-overlay {
    width: min(140px, 36%);
  }
}

/* The status view is a full-size scene; all UI floats over the canvas. */
.tesla-page--visual {
  position: absolute;
  inset: 0;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.tesla-page--visual .tesla-tabs-card,
.tesla-page--visual .tesla-card--visual {
  padding: 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.tesla-page--visual .tesla-tabs-card,
.tesla-page--visual .tesla-tabs,
.tesla-page--visual :deep(.el-tabs__content),
.tesla-page--visual :deep(.el-tab-pane),
.tesla-page--visual .tesla-grid--content,
.tesla-page--visual .tesla-card--visual,
.tesla-page--visual .vehicle-visual-shell {
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
}
.tesla-page--visual :deep(.el-tabs__header) {
  position: absolute;
  top: 12px;
  left: 14px;
  right: 14px;
  margin: 0;
  padding: 0 12px;
  z-index: 4;
  border-radius: 16px;
  background: rgba(255, 255, 255, .72);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}
.tesla-page--visual .vehicle-visual-stage {
  position: absolute;
  inset: 0;
  height: 100%;
  min-height: 0;
  border-radius: 0;
}
.tesla-page--visual .vehicle-visual-overlay {
  top: 72px;
  pointer-events: none;
}
@media (max-height: 520px) {
  .tesla-page--visual .vehicle-visual-overlay { gap: 4px; width: 190px; }
  .tesla-page--visual .vehicle-overlay-card { flex-direction: row; align-items: baseline; justify-content: flex-end; gap: 8px; }
  .tesla-page--visual .vehicle-overlay-card strong { font-size: 13px; }
}
.vehicle-appearance-editor{display:flex;flex-direction:column;gap:14px}
.vehicle-appearance-editor label{display:flex;align-items:center;justify-content:space-between;gap:14px;white-space:nowrap}
.vehicle-appearance-editor input[type=color]{width:58px;height:32px;border:0;background:none;cursor:pointer}
.vehicle-appearance-editor small{color:var(--color-text-soft);font-size:12px}
.vehicle-paint-swatches{display:flex;gap:10px}
.vehicle-paint-swatches button{width:30px;height:30px;border-radius:50%;border:2px solid #ffffff;box-shadow:0 0 0 1px #cbd4da;cursor:pointer}
.vehicle-paint-swatches button[aria-pressed=true]{box-shadow:0 0 0 2px #329cff}

</style>

<style scoped>
.vehicle-map-controls{position:absolute;right:18px;bottom:16px;display:flex;align-items:flex-end;gap:8px;z-index:3;flex-wrap:wrap;justify-content:flex-end;max-width:60%}
.vehicle-map-controls button{border:1px solid #cfdfe3;border-radius:22px;background:#ffffffeb;backdrop-filter:blur(16px);padding:9px 14px;color:#365763;font:inherit;font-size:12px;cursor:pointer}
.vehicle-appearance-editor{display:flex;flex-direction:column;gap:14px}
.vehicle-appearance-editor label{display:flex;align-items:center;justify-content:space-between;gap:14px;white-space:nowrap}
.vehicle-appearance-editor input[type=color]{width:58px;height:32px;border:0;background:none;cursor:pointer}
.vehicle-appearance-editor small{color:var(--color-text-soft);font-size:12px}
.vehicle-paint-swatches{display:flex;gap:10px}
.vehicle-paint-swatches button{width:30px;height:30px;border-radius:50%;border:2px solid #ffffff;box-shadow:0 0 0 1px #cbd4da;cursor:pointer}
.vehicle-paint-swatches button[aria-pressed=true]{box-shadow:0 0 0 2px #329cff}

</style>

<style scoped>
</style>

<style scoped>
.vehicle-speed-hud{position:absolute;top:18px;left:20px;z-index:3;pointer-events:none;min-width:108px;padding:10px 16px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.2);background:linear-gradient(135deg,rgba(12,23,32,.72),rgba(12,23,32,.38));color:#fff;text-shadow:0 2px 8px rgba(0,0,0,.35)}
.vehicle-speed-hud__label{font-size:11px;letter-spacing:2px;color:rgba(255,255,255,.72)}
.vehicle-speed-hud__reading{display:flex;align-items:baseline;gap:9px;white-space:nowrap}
.vehicle-speed-hud__reading strong{font-size:clamp(38px,5vw,64px);font-weight:650;line-height:1.05;letter-spacing:-2px;font-variant-numeric:tabular-nums}
.vehicle-speed-hud__reading span{font-size:12px;color:rgba(255,255,255,.8)}
.vehicle-speed-hud__hint{display:block;max-width:160px;margin-top:3px;color:rgba(255,255,255,.8);font-size:10px;line-height:1.3;white-space:normal}
@media(max-height:600px){.vehicle-speed-hud{top:12px;left:14px;padding:8px 12px;min-width:92px}.vehicle-speed-hud__reading strong{font-size:42px}}
</style>

<style scoped>
/* Keep the scene full bleed, with a compact header and a separate speed HUD. */
.tesla-page--visual :deep(.el-tabs__header) {
  top: 12px; left: 18px; right: auto; max-width: calc(100% - 36px);
  padding: 0 8px; border: 1px solid rgba(255,255,255,.14); border-radius: 14px;
  background: rgba(15,24,31,.52); box-shadow: 0 4px 20px #0002;
  --el-text-color-primary: #fff; --el-color-primary: #fff;
}
.tesla-page--visual :deep(.el-tabs__nav-wrap::after),
.tesla-page--visual :deep(.el-tabs__active-bar) { display: none; }
.tesla-page--visual :deep(.el-tabs__item) {
  height: 40px; padding: 0 14px !important; color: #ffffffa8; font-size: 13px;
}
.tesla-page--visual :deep(.el-tabs__item.is-active) { color: #fff; text-shadow: 0 0 12px #fff5; }
.tesla-page--visual .vehicle-speed-hud {
  top: 76px; left: 20px; padding: 8px 12px; border: 0; background: #111d2870;
  border-radius: 12px; backdrop-filter: blur(12px);
}
.vehicle-map-controls {
  position: absolute; left: 14px; right: 14px; bottom: 14px; max-width: none;
  flex-wrap: nowrap; align-items: center; justify-content: center; gap: 6px;
  padding: 8px; border: 1px solid #ffffff24; border-radius: 16px;
  background: #101a25b8; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  overflow-x: auto; scrollbar-width: none;
}
.vehicle-map-controls::-webkit-scrollbar { display: none; }
.vehicle-map-controls button {
  position: static; flex: 0 0 auto; margin: 0; min-height: 40px; box-sizing: border-box;
  padding: 8px 12px; border: 1px solid transparent; border-radius: 10px;
  background: transparent; color: #f1f5f9; font-size: 12px; white-space: nowrap;
  backdrop-filter: none;
}
.vehicle-map-controls button:hover, .vehicle-map-controls button[aria-pressed=true] {
  color: #fff; background: #ffffff1c; border-color: #ffffff26;
}
.vehicle-map-controls button:focus-visible {
  outline: 2px solid #89c7ff; outline-offset: -2px;
}
.vehicle-map-controls .vehicle-weather-trigger { min-height: 48px; padding: 10px 16px; font-size: 14px; background: #ffffff20; border-color: #ffffff30; }
.vehicle-weather-caret {
  display: inline-block; width: 0; height: 0; margin-left: 8px; vertical-align: middle;
  border-right: 5px solid transparent; border-left: 5px solid transparent;
  border-bottom: 6px solid currentColor;
}
.tesla-page--visual .vehicle-visual-overlay {
  top: 76px; right: 20px; width: auto; padding: 12px 14px; gap: 9px;
  border-radius: 12px; background: #101a2575; backdrop-filter: blur(12px);
}
.tesla-page--visual .vehicle-overlay-card { flex-direction: row; justify-content: space-between; align-items: baseline; gap: 18px; }
.tesla-page--visual .vehicle-overlay-card span { color: #ffffffad; text-shadow: none; }
.tesla-page--visual .vehicle-overlay-card strong { color: #fff; text-shadow: none; font-variant-numeric: tabular-nums; }
.tesla-page--visual .vehicle-overlay-card--weather { align-items: center; justify-content: flex-end; gap: 8px; padding-bottom: 9px; border-bottom: 1px solid #ffffff26; }
.vehicle-weather-summary { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.vehicle-overlay-card--weather .vehicle-weather-summary strong { font-size: 16px; }
@media(max-width: 700px) {
  .vehicle-map-controls { left: 8px; right: 8px; bottom: 8px; justify-content: flex-start; gap: 2px; padding: 6px; }
  .vehicle-map-controls button { padding: 8px; }
}
@media(max-height: 520px) {
  .tesla-page--visual .vehicle-visual-overlay { gap: 5px; padding: 8px 10px; }
  .tesla-page--visual .vehicle-speed-hud { top: 70px; }
}
</style>

<style scoped>
.vehicle-visual-shell--loading { visibility: hidden; pointer-events: none; }
</style>

<style>
.el-popper.vehicle-weather-popper.el-popover {
  padding: 8px;
  border: 1px solid #ffffff35;
  border-radius: 14px;
  background: #172430;
  box-shadow: 0 12px 32px #0006;
}
.vehicle-weather-options {
  display: grid;
  gap: 4px;
  max-height: min(340px, calc(100dvh - 110px));
  overflow-y: auto;
}
.vehicle-weather-options button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 50px;
  padding: 10px 14px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #f1f5f9;
  font: inherit;
  font-size: 16px;
  text-align: left;
  cursor: pointer;
}
.vehicle-weather-selected { display: inline-block; width: 8px; height: 13px; margin-right: 4px; border-right: 2px solid currentColor; border-bottom: 2px solid currentColor; transform: rotate(45deg); }
.vehicle-weather-options button:hover,
.vehicle-weather-options button[aria-checked="true"] { background: #ffffff26; }
.vehicle-weather-options button:focus-visible { outline: 2px solid #89c7ff; outline-offset: -2px; }
</style>
