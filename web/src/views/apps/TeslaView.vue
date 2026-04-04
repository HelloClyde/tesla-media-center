<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { del, get, post } from '@/functions/requests';
import getAMap from '@/functions/amapConfig';

const mapContainer = ref<HTMLElement | null>(null);

let mapInstance: any = null;
let polyline: any = null;
let vehicleMarker: any = null;
let autoSyncTimer: number | null = null;
let gAMap: any = null;

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
  settingsLoading: false,
  statusLoading: false,
  syncLoading: false,
  tripsLoading: false,
  rawLoading: false,
  storageLoading: false,
  mapReady: false,
  mapError: '',
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
  },
});

const selectedVehicle = computed(() => {
  return state.vehicles.find((item: any) => item.vin === state.selectedVin) || null;
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
    if (!state.selectedVin && state.vehicles.length > 0) {
      state.selectedVin = state.vehicles[0].vin;
    }
  });
}

function loadTrack() {
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

function loadTrips() {
  if (!state.selectedVin) {
    state.trips = [];
    return Promise.resolve();
  }
  state.tripsLoading = true;
  return get(`/api/tesla/history/trips?vin=${encodeURIComponent(state.selectedVin)}&limit=2000`, '读取行程失败').then((data) => {
    state.trips = data.items || [];
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
  return Promise.all([loadTrack(), loadTrips(), loadRawRows()]);
}

function openTripTrack(trip: any) {
  state.selectedTrip = trip;
  state.activeTab = 'track';
  const tripPoints = (trip.samples || []).filter((item: any) => item.longitude != null && item.latitude != null);
  state.trackPoints = tripPoints;
  state.latestSample = (trip.samples || [])[trip.samples.length - 1] || null;
  nextTick(() => {
    renderTrackOnMap();
  });
}

function showAllTrack() {
  state.selectedTrip = null;
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
    Promise.all([loadTrips(), loadTrack(), loadStorage()]).then(() => {
      ElMessage.success('行程已删除');
    });
  });
}

function handleRawPageChange(page: number) {
  state.rawPage = page;
  loadRawRows();
}

function syncVehicles(showMessage = false) {
  state.syncLoading = true;
  return post('/api/tesla/sync', {
    vin: state.selectedVin || undefined,
  }, '同步 Tesla 数据失败').then(() => {
    return Promise.all([loadStatus(), loadVehicles(), loadTrack(), loadTrips(), loadStorage()]).then(() => {
      if (showMessage) {
        ElMessage.success('Tesla 数据已同步');
      }
    });
  }).finally(() => {
    state.syncLoading = false;
  });
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
  if (polyline) {
    mapInstance.remove(polyline);
    polyline = null;
  }
  if (vehicleMarker) {
    mapInstance.remove(vehicleMarker);
    vehicleMarker = null;
  }

  const points = state.trackPoints
    .filter((item: any) => item.longitude != null && item.latitude != null)
    .map((item: any) => [item.longitude, item.latitude]);

  if (points.length > 1) {
    polyline = new gAMap.Polyline({
      path: points,
      strokeColor: '#409EFF',
      strokeWeight: 6,
      lineJoin: 'round',
      lineCap: 'round',
    });
    mapInstance.add(polyline);
  }

  const latestPoint = points[points.length - 1];
  if (latestPoint) {
    vehicleMarker = new gAMap.Marker({
      position: latestPoint,
      title: selectedVehicle.value?.displayName || state.selectedVin,
    });
    mapInstance.add(vehicleMarker);
    mapInstance.setFitView(vehicleMarker ? [vehicleMarker, polyline].filter(Boolean) : [polyline], false, [80, 80, 80, 80]);
  }
}

onMounted(() => {
  Promise.all([loadSettings(), loadStatus()]).then(() => {
    loadStorage();
    if (state.status.authorized) {
      return loadVehicles().then(() => Promise.all([loadTrack(), loadTrips(), loadRawRows()]));
    }
  });
  initMap();
  autoSyncTimer = window.setInterval(() => {
    if (state.status.authorized && !state.syncLoading) {
      Promise.all([loadStatus(), loadVehicles(), loadTrack(), loadTrips(), loadRawRows(), loadStorage()]);
    }
  }, 15000);
});

onUnmounted(() => {
  if (autoSyncTimer !== null) {
    window.clearInterval(autoSyncTimer);
    autoSyncTimer = null;
  }
});
</script>

<template>
  <div class="tesla-page">
    <section class="tesla-tabs-card">
      <el-tabs v-model="state.activeTab" class="tesla-tabs">
        <el-tab-pane label="车辆状态" name="status">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card">
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">Vehicles</p>
                  <h2>车辆与状态</h2>
                </div>
              </div>
              <div class="vehicle-overview">
                <div class="vehicle-main">
                  <span class="vehicle-label">当前车辆</span>
                  <el-select v-model="state.selectedVin" placeholder="选择车辆" class="vehicle-select" @change="handleVehicleChange">
                    <el-option v-for="vehicle of state.vehicles" :key="vehicle.vin" :label="`${vehicle.displayName} (${vehicle.vin})`" :value="vehicle.vin" />
                  </el-select>
                </div>
                <div class="overview-pill">
                  <span>状态</span>
                  <strong>{{ state.latestSample?.vehicle_state || selectedVehicle?.state || '-' }}</strong>
                </div>
                <div class="overview-pill">
                  <span>电量</span>
                  <strong>{{ state.latestSample?.battery_level != null ? `${state.latestSample.battery_level}%` : '-' }}</strong>
                </div>
                <div class="overview-pill">
                  <span>最近同步</span>
                  <strong>{{ formatTimestamp(state.latestSample?.timestamp_ms || state.status.lastSyncAt * 1000) }}</strong>
                </div>
              </div>
              <div class="state-grid">
                <div v-for="item of sampleCards" :key="item.label" class="state-box">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
            </article>
          </section>
        </el-tab-pane>

        <el-tab-pane label="轨迹" name="track">
          <section class="tesla-grid tesla-grid--content">
            <article class="tesla-card tesla-card--map">
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
              <div class="card-head">
                <div>
                  <p class="tesla-kicker">SQLite</p>
                  <h2>原始记录</h2>
                </div>
                <div class="status-pill">{{ state.rawTotal }} 条</div>
              </div>
              <div v-if="state.rawRows.length === 0" class="trip-empty">
                当前车辆还没有原始样本记录
              </div>
              <template v-else>
                <el-table :data="state.rawRows" size="small" class="raw-table">
                  <el-table-column prop="timestamp_ms" label="时间" min-width="180">
                    <template #default="{ row }">{{ formatTimestamp(row.timestamp_ms) }}</template>
                  </el-table-column>
                  <el-table-column prop="vehicle_state" label="状态" min-width="100" />
                  <el-table-column prop="shift_state" label="档位" min-width="80" />
                  <el-table-column prop="speed" label="速度" min-width="100">
                    <template #default="{ row }">{{ row.speed != null ? `${row.speed} ${row.speed_unit || 'km/h'}` : '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="odometer" label="里程" min-width="120">
                    <template #default="{ row }">{{ row.odometer != null ? `${row.odometer} ${row.distance_unit || 'km'}` : '-' }}</template>
                  </el-table-column>
                  <el-table-column label="坐标" min-width="220">
                    <template #default="{ row }">{{ row.latitude != null && row.longitude != null ? `${row.latitude}, ${row.longitude}` : '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="battery_level" label="电量" min-width="90">
                    <template #default="{ row }">{{ row.battery_level != null ? `${row.battery_level}%` : '-' }}</template>
                  </el-table-column>
                </el-table>
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

.raw-table {
  margin-bottom: 16px;
}

.raw-pagination {
  display: flex;
  justify-content: flex-end;
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
}
</style>
