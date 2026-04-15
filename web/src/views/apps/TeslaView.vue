<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { del, get, post } from '@/functions/requests';
import getAMap from '@/functions/amapConfig';

const pageRef = ref<HTMLElement | null>(null);
const vehicleVisualRef = ref<HTMLElement | null>(null);
const mapContainer = ref<HTMLElement | null>(null);
const rawTableWrapRef = ref<HTMLElement | null>(null);
const rawTableRef = ref<any>(null);

let mapInstance: any = null;
let polylines: any[] = [];
let vehicleMarker: any = null;
let autoSyncTimer: number | null = null;
let pageObserver: IntersectionObserver | null = null;
let gAMap: any = null;
let lastForcedSyncAt = 0;
let tabPollInFlight = false;
let pendingTabRefreshOptions: { allowForceSync?: boolean; immediate?: boolean } | null = null;
let vehicleScene: THREE.Scene | null = null;
let vehicleCamera: THREE.PerspectiveCamera | null = null;
let vehicleRenderer: THREE.WebGLRenderer | null = null;
let vehicleModelRoot: THREE.Group | null = null;
let vehicleModelPivot: THREE.Group | null = null;
let vehicleControls: OrbitControls | null = null;
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

const DEFAULT_VEHICLE_CAMERA_POSITION = new THREE.Vector3(0, 3.4, 8.2);
const DEFAULT_VEHICLE_CAMERA_TARGET = new THREE.Vector3(0, 1.35, 0);

type TeslaTabName = 'status' | 'track' | 'trip' | 'raw' | 'settings';

const ACTIVE_TAB_POLL_INTERVAL_MS: Record<TeslaTabName, number> = {
  status: 1000,
  track: 1000,
  trip: 15000,
  raw: 1000,
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
    profile: null as any,
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
    return shift;
  }
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
  return get(
    `/api/tesla/history/trips/detail?vin=${encodeURIComponent(state.selectedVin)}&startMs=${trip.startTimeMs}&endMs=${trip.endTimeMs}&limit=20000`,
    '读取行程轨迹失败'
  ).then((data) => {
    const items = data.items || [];
    state.trackPoints = items.filter((item: any) => item.longitude != null && item.latitude != null);
    state.latestSample = data.latest || items[items.length - 1] || null;
    nextTick(() => {
      renderTrackOnMap();
    });
  }).finally(() => {
    state.tripTrackLoading = false;
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
  if (!state.status.authorized || state.syncLoading) {
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

function refreshTabData(tabName: TeslaTabName, options?: { allowForceSync?: boolean; includeStorage?: boolean }): Promise<void> {
  const allowForceSync = options?.allowForceSync ?? true;
  const includeStorage = options?.includeStorage ?? tabName === 'settings';

  const baseTasks: Promise<any>[] = [loadStatus()];
  if (includeStorage) {
    baseTasks.push(loadStorage());
  }

  return Promise.all(baseTasks).then(() => {
    if (!state.status.authorized) {
      clearTabData(tabName);
      return;
    }
    return loadVehicles().then(() => {
      if (tabName === 'status' || tabName === 'track') {
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

function refreshActiveTabData(options?: { allowForceSync?: boolean; immediate?: boolean }): Promise<void> {
  const allowForceSync = options?.allowForceSync ?? true;
  const immediate = options?.immediate ?? false;

  if (!immediate && !isTeslaPageVisible()) {
    return Promise.resolve();
  }
  if (tabPollInFlight) {
    pendingTabRefreshOptions = {
      allowForceSync: (pendingTabRefreshOptions?.allowForceSync ?? false) || allowForceSync,
      immediate: (pendingTabRefreshOptions?.immediate ?? false) || immediate,
    };
    return Promise.resolve();
  }
  tabPollInFlight = true;
  return refreshTabData(state.activeTab as TeslaTabName, { allowForceSync }).finally(() => {
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
    refreshActiveTabData();
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
  return post('/api/tesla/sync', {
    vin: state.selectedVin || undefined,
  }, '同步 Tesla 数据失败').then(() => {
    return refreshTabData(tabName, {
      allowForceSync: false,
      includeStorage: true,
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
  const container = vehicleVisualRef.value;
  vehicleScene = new THREE.Scene();
  vehicleScene.background = new THREE.Color('#eef2f6');

  vehicleCamera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  vehicleCamera.position.copy(DEFAULT_VEHICLE_CAMERA_POSITION);
  vehicleCamera.lookAt(DEFAULT_VEHICLE_CAMERA_TARGET);

  vehicleRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  vehicleRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  vehicleRenderer.setSize(container.clientWidth || 640, container.clientHeight || 420);
  vehicleRenderer.outputColorSpace = THREE.SRGBColorSpace;
  vehicleRenderer.toneMapping = THREE.ACESFilmicToneMapping;
  vehicleRenderer.toneMappingExposure = 1;
  vehicleRenderer.shadowMap.enabled = false;
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

  vehicleScene.add(new THREE.HemisphereLight('#fdfefe', '#aeb7c2', 2.4));

  const keyLight = new THREE.DirectionalLight('#ffffff', 2.4);
  keyLight.position.set(5, 8, 7);
  vehicleScene.add(keyLight);

  const rimLight = new THREE.DirectionalLight('#dbeafe', 1.1);
  rimLight.position.set(-6, 4, -5);
  vehicleScene.add(rimLight);

  const fillLight = new THREE.PointLight('#b6d9ff', 0.9, 24);
  fillLight.position.set(-3, 3, 5);
  vehicleScene.add(fillLight);

  vehicleModelPivot = new THREE.Group();
  vehicleModelPivot.position.y = 0.85;
  vehicleScene.add(vehicleModelPivot);

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  state.visualLoading = true;
  loader.load('/models/2021_tesla_model_y.glb', (gltf: { scene: THREE.Group }) => {
    const model = gltf.scene;
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxAxis = Math.max(size.x, size.y, size.z) || 1;
    const scale = 4.8 / maxAxis;

    model.position.sub(center);
    model.position.y += size.y * 0.08;
    model.scale.setScalar(scale);
    model.traverse((child: THREE.Object3D) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.castShadow = false;
        mesh.receiveShadow = false;
      }
    });

    vehicleModelRoot = model;
    vehicleModelPivot?.add(model);
    state.visualError = '';
    state.visualLoading = false;
    updateVehicleVisualState();
    resizeVehicleViewer();
  }, undefined, (error: unknown) => {
    console.error(error);
    state.visualError = '车辆模型加载失败';
    state.visualLoading = false;
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
  vehicleRenderer.setSize(width, height);
  vehicleCamera.aspect = width / height;
  vehicleCamera.updateProjectionMatrix();
  renderVehicleViewer();
}

function renderVehicleViewer() {
  if (!vehicleRenderer || !vehicleScene || !vehicleCamera) {
    return;
  }
  vehicleRenderer.render(vehicleScene, vehicleCamera);
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
    vehicleControls?.update();
    vehicleRenderer.render(vehicleScene, vehicleCamera);
  };
  vehicleRenderLoopFrame = window.requestAnimationFrame(frame);
}

function stopVehicleRenderLoop() {
  if (vehicleRenderLoopFrame !== null) {
    window.cancelAnimationFrame(vehicleRenderLoopFrame);
    vehicleRenderLoopFrame = null;
  }
}

function updateVehicleVisualState() {
  if (!vehicleModelPivot) {
    return;
  }
  vehicleModelPivot.rotation.y = getVehicleOrientationByShift(currentShiftState.value);
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
    vehicleControls.update();
    renderVehicleViewer();
    if (progress < 1) {
      vehicleAnimationFrame = window.requestAnimationFrame(step);
      return;
    }
    stopVehicleViewTween();
  };

  vehicleAnimationFrame = window.requestAnimationFrame(step);
}

function resetVehicleView() {
  animateVehicleView(DEFAULT_VEHICLE_CAMERA_POSITION, DEFAULT_VEHICLE_CAMERA_TARGET);
}

function disposeVehicleViewer() {
  if (vehicleResetViewTimer !== null) {
    window.clearTimeout(vehicleResetViewTimer);
    vehicleResetViewTimer = null;
  }
  stopVehicleViewTween();
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
    vehicleRenderer.dispose();
    vehicleRenderer.domElement.remove();
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
  getAMap().then((AMap) => {
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
    console.error(error);
    state.mapError = '高德地图初始化失败，请检查 Key 配置';
  });
}

function renderTrackOnMap() {
  if (!mapInstance || !gAMap) {
    return;
  }
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
  document.addEventListener('visibilitychange', handleDocumentVisibilityChange);
  Promise.all([loadSettings(), refreshActiveTabData({ immediate: true })]).finally(() => {
    restartAutoSyncTimer();
  });
  initMap();
  nextTick(() => {
    if (state.activeTab === 'status') {
      initVehicleViewer();
      startVehicleRenderLoop();
      resizeVehicleViewer();
      updateVehicleVisualState();
    }
    observePageExposure();
  });
});

onUnmounted(() => {
  document.removeEventListener('visibilitychange', handleDocumentVisibilityChange);
  stopAutoSyncTimer();
  if (pageObserver) {
    pageObserver.disconnect();
    pageObserver = null;
  }
  disposeVehicleViewer();
});

watch(() => state.activeTab, (tabName) => {
  restartAutoSyncTimer();
  refreshActiveTabData({ immediate: true });
  if (tabName === 'status') {
    nextTick(() => {
      initVehicleViewer();
      startVehicleRenderLoop();
      resizeVehicleViewer();
      updateVehicleVisualState();
    });
  } else {
    stopVehicleRenderLoop();
  }
  if (tabName === 'track') {
    nextTick(() => {
      if (mapInstance && typeof mapInstance.resize === 'function') {
        mapInstance.resize();
      }
      renderTrackOnMap();
    });
  }
});

watch(currentShiftState, () => {
  updateVehicleVisualState();
});
</script>

<template>
  <div ref="pageRef" class="tesla-page">
    <section class="tesla-tabs-card">
      <el-tabs v-model="state.activeTab" class="tesla-tabs">
        <el-tab-pane label="车辆状态" name="status">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card tesla-card--visual" v-loading="state.visualLoading">
              <div v-if="state.visualError" class="map-empty">{{ state.visualError }}</div>
              <div v-else class="vehicle-visual-shell">
                <div class="vehicle-visual-overlay">
                  <div class="vehicle-overlay-card">
                    <span>当前档位</span>
                    <strong :class="vehicleVisualStatus.accent">{{ vehicleVisualStatus.label }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>当前车况</span>
                    <strong>{{ state.latestSample?.vehicle_state || selectedVehicle?.state || '-' }}</strong>
                  </div>
                  <div class="vehicle-overlay-card">
                    <span>速度</span>
                    <strong>{{ state.latestSample?.speed != null ? `${state.latestSample.speed} ${state.latestSample.speed_unit || 'km/h'}` : '-' }}</strong>
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
                <div class="meta-line"><span>最近同步</span><strong>{{ formatTimestamp(state.status.lastSyncAt * 1000) }}</strong></div>
                <div class="meta-line"><span>账户</span><strong>{{ state.status.profile?.email || '-' }}</strong></div>
                <div class="meta-line"><span>名称</span><strong>{{ state.status.profile?.fullName || '-' }}</strong></div>
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
  gap: 18px;
  padding: 18px;
}

.tesla-hero,
.tesla-card,
.tesla-tabs-card {
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 14px 30px var(--color-shadow);
}

.tesla-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
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
    position: static;
    width: 100%;
    margin-bottom: 12px;
  }
}
</style>
