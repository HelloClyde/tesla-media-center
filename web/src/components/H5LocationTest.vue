<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { createGpsSpeedTracker } from '@/views/apps/teslaGpsSpeed';

type Fix = {
  receivedAt: string;
  timestamp: number;
  ageMs: number;
  latitude: number;
  longitude: number;
  accuracy: number;
  speedMps: number | null;
  heading: number | null;
  estimatedKmh: number | null;
};

const tracker = createGpsSpeedTracker();
const samples = ref<Fix[]>([]);
const events = ref<string[]>([]);
const permission = ref('未查询');
const watching = ref(false);
let watchId: number | undefined;
let permissionStatus: PermissionStatus | undefined;

const available = computed(() => typeof navigator !== 'undefined' && !!navigator.geolocation);
const secureContext = window.isSecureContext;
const environment = computed(() => ({
  secureContext,
  origin: window.location.origin,
  geolocation: available.value,
  permission: permission.value,
}));

function log(message: string) {
  events.value.unshift(`${new Date().toLocaleTimeString()} ${message}`);
  events.value = events.value.slice(0, 12);
}

function receive(position: GeolocationPosition) {
  const { coords, timestamp } = position;
  const estimatedKmh = tracker.accept({
    latitude: coords.latitude, longitude: coords.longitude,
    accuracy: coords.accuracy, speed: coords.speed, timestamp,
  });
  samples.value.unshift({
    receivedAt: new Date().toLocaleTimeString(), timestamp, ageMs: Date.now() - timestamp,
    latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy,
    speedMps: coords.speed, heading: coords.heading, estimatedKmh,
  });
  samples.value = samples.value.slice(0, 12);
  log(`定位成功：原生速度 ${coords.speed === null ? 'null' : `${coords.speed} m/s`}，估算 ${estimatedKmh === null ? '等待有效坐标' : `${estimatedKmh.toFixed(1)} km/h`}`);
}

function fail(error: GeolocationPositionError) {
  log(`定位失败：code=${error.code} ${error.message || '无错误详情'}`);
}

async function checkPermission() {
  if (!navigator.permissions?.query) { permission.value = '浏览器未提供 Permissions API'; return; }
  try {
    permissionStatus = await navigator.permissions.query({ name: 'geolocation' });
    permission.value = permissionStatus.state;
    permissionStatus.onchange = () => { permission.value = permissionStatus?.state || '未知'; };
  } catch (error) {
    permission.value = error instanceof Error ? error.message : String(error);
  }
}

function getCurrent() {
  if (!navigator.geolocation) { log('浏览器未提供 Geolocation API'); return; }
  log('调用 getCurrentPosition（高精度，禁用缓存，15 秒超时）');
  try {
    navigator.geolocation.getCurrentPosition(receive, fail, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
  } catch (error) { log(`调用异常：${String(error)}`); }
}

function startWatch() {
  if (!navigator.geolocation || watchId !== undefined) return;
  tracker.reset();
  log('调用 watchPosition（高精度，禁用缓存）');
  try {
    watchId = navigator.geolocation.watchPosition(receive, fail, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    watching.value = true;
  } catch (error) { log(`调用异常：${String(error)}`); }
}

function stopWatch() {
  if (watchId !== undefined) navigator.geolocation?.clearWatch(watchId);
  watchId = undefined;
  watching.value = false;
  log('已停止 watchPosition');
}

void checkPermission();
onUnmounted(() => {
  if (watchId !== undefined) navigator.geolocation?.clearWatch(watchId);
  if (permissionStatus) permissionStatus.onchange = null;
});
</script>

<template>
  <article class="location-test">
    <span class="diagnostic-title">H5 定位 API 实测</span>
    <p>直接调用车机浏览器接口。行驶中观察原生速度、坐标变化和定位时间；原生速度为 null 时，页面会用连续坐标估算。</p>
    <pre>{{ JSON.stringify(environment, null, 2) }}</pre>
    <div class="location-test__actions">
      <el-button :disabled="!available" @click="getCurrent">单次读取</el-button>
      <el-button :disabled="!available || watching" type="primary" @click="startWatch">开始连续定位</el-button>
      <el-button :disabled="!watching" @click="stopWatch">停止</el-button>
      <el-button @click="checkPermission">检查权限</el-button>
    </div>
    <p v-if="!secureContext">当前页面不是安全上下文，浏览器可能拒绝定位。请通过 HTTPS 访问。</p>
    <pre>最近结果：{{ JSON.stringify(samples, null, 2) }}</pre>
    <pre>调用日志：{{ events.join('\n') || '尚未调用定位接口' }}</pre>
  </article>
</template>

<style scoped>
.location-test{min-width:0}
.location-test p{color:var(--color-text-soft);font-size:13px;line-height:1.5}
.location-test pre{max-height:240px;overflow:auto;padding:12px;border-radius:8px;background:rgba(120,140,160,.1);font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
.location-test__actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.location-test__actions :deep(.el-button){margin:0}
</style>
