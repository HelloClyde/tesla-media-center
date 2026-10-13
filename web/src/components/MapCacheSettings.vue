<script setup lang="ts">
import { onMounted, ref } from 'vue';
import axios from 'axios';
import { browserMapCacheStats, clearBrowserMapCache, updateBrowserMapCacheConfig, requestBrowserMapPersistence,
  DEFAULT_BROWSER_MAP_CACHE_MB, MAX_BROWSER_MAP_CACHE_MB } from '@/views/apps/amapBrowserTileCache';
const ttlHours = ref(168), maxMB = ref(512), usedBytes = ref(0), count = ref(0);
const busy = ref(false), ready = ref(false), message = ref('');
const device = ref<Awaited<ReturnType<typeof browserMapCacheStats>>>();
const deviceTtlHours=ref(168), deviceMaxMB=ref(DEFAULT_BROWSER_MAP_CACHE_MB);
const deviceBusy=ref(false), deviceMessage=ref('');
async function request(method: 'GET' | 'PUT' | 'DELETE') {
  busy.value = true; message.value = '';
  try {
    const response = await axios.request({ url: '/api/amap-app/cache', method, data: method === 'PUT' ? { ttlHours: ttlHours.value, maxMB: maxMB.value } : undefined, timeout: 15000 });
    if (response.data.status !== 'ok') throw new Error(response.data.message || '请登录后重试');
    const data = response.data.data;
    ttlHours.value = data.ttlHours; maxMB.value = data.maxMB; usedBytes.value = data.usedBytes; count.value = data.count; ready.value = true;
    message.value = method === 'DELETE' ? '地图缓存已清空' : method === 'PUT' ? '设置已保存' : '';
  } catch (error) { message.value = axios.isAxiosError(error) ? error.response?.data?.message || '缓存服务连接失败' : (error as Error).message; }
  finally { busy.value = false; }
}
async function refreshDevice() {
  device.value=await browserMapCacheStats();
  deviceTtlHours.value=device.value.ttlHours;deviceMaxMB.value=device.value.maxMB;
}
async function saveDevice() {
  deviceBusy.value=true;deviceMessage.value='';
  const success=await updateBrowserMapCacheConfig(deviceTtlHours.value,deviceMaxMB.value);
  await refreshDevice();
  deviceMessage.value=success?'本机缓存设置已保存':'无法保存本机缓存设置';
  deviceBusy.value=false;
}
async function clearDevice() {
  deviceBusy.value=true;deviceMessage.value='';
  const success=await clearBrowserMapCache();
  await refreshDevice();
  deviceMessage.value=success?'本机地图缓存已清空':'本机浏览器未提供持久缓存';
  deviceBusy.value=false;
}
async function persistDevice() {
  deviceBusy.value = true; deviceMessage.value = '';
  const granted = await requestBrowserMapPersistence();
  await refreshDevice();
  deviceMessage.value = granted ? '浏览器已允许长期保留地图缓存' : '浏览器未批准长期保留，现有缓存仍可使用';
  deviceBusy.value = false;
}
onMounted(() => {void request('GET');void refreshDevice();});
</script>
<template>
  <section class="map-cache-settings">
    <h3>地图磁盘缓存</h3>
    <p>缓存保存在服务器，所有车机共享。过期自动清理，容量不足时优先淘汰最近最少使用的地图块。</p>
    <div class="cache-fields">
      <label>有效期（小时）<el-input-number v-model="ttlHours" :min="1" :max="2160" :precision="0" :disabled="busy || !ready" /></label>
      <label>容量上限（MB）<el-input-number v-model="maxMB" :min="16" :max="4096" :precision="0" :disabled="busy || !ready" /></label>
    </div>
    <p v-if="ready">已缓存 {{ count }} 个地图块 · {{ (usedBytes / 1048576).toFixed(2) }} MB（压缩数据，不含数据库管理开销）</p>
    <div class="cache-actions">
      <el-button type="primary" :disabled="busy || !ready" @click="request('PUT')">保存设置</el-button>
      <el-button :disabled="busy" @click="request('GET')">刷新用量</el-button>
      <el-button :disabled="busy || !ready" @click="request('DELETE')">清空地图缓存</el-button>
    </div>
    <p role="status">{{ message }}</p>
    <h3>本机浏览器缓存</h3>
    <p>地图块和特色地标模型保存在当前车机，重访先读取本机；2D 与 3D 共用缓存。默认 1 GB，最高可设为 8 GB，实际容量受浏览器配额和剩余空间限制。</p>
    <div class="cache-fields">
      <label>有效期（小时）<el-input-number v-model="deviceTtlHours" :min="1" :max="2160" :precision="0" :disabled="deviceBusy || !device?.available" /></label>
      <label>容量上限（MB）<el-input-number v-model="deviceMaxMB" :min="16" :max="MAX_BROWSER_MAP_CACHE_MB" :precision="0" :disabled="deviceBusy || !device?.available" /></label>
    </div>
    <p v-if="device">{{ device.available ? `本机已缓存 ${device.count} 个地图资源 · ${(device.usedBytes / 1048576).toFixed(2)} MB` : '本机浏览器不支持持久地图缓存' }}</p>
    <p v-if="device?.available && device.quotaBytes !== null">浏览器配额 {{ (device.quotaBytes / 1073741824).toFixed(2) }} GB · 站点已用 {{ ((device.usageBytes || 0) / 1048576).toFixed(1) }} MB · 地图有效上限 {{ device.effectiveMaxMB.toFixed(0) }} MB</p>
    <p v-if="device?.available && device.persistent !== null">{{ device.persistent ? '长期保留已启用' : '尚未获得长期保留权限，浏览器可能在空间不足时清理缓存' }}</p>
    <div class="cache-actions">
      <el-button type="primary" :disabled="deviceBusy || !device?.available" @click="saveDevice">保存本机设置</el-button>
      <el-button :disabled="deviceBusy" @click="refreshDevice">刷新本机用量</el-button>
      <el-button :disabled="deviceBusy || !device?.available" @click="clearDevice">清空本机缓存</el-button>
      <el-button v-if="device?.persistent === false" :disabled="deviceBusy || !device?.available" @click="persistDevice">申请长期保留</el-button>
    </div>
    <p role="status">{{ deviceMessage }}</p>
  </section>
</template>
<style scoped>
.map-cache-settings{padding:20px;max-width:760px;color:var(--color-text)}h3{font-size:19px;margin-bottom:12px}p{font-size:13px;line-height:1.8;color:var(--color-text-soft);margin:12px 0}.cache-fields,.cache-actions{display:flex;flex-wrap:wrap;gap:16px}.cache-fields label{display:flex;flex-direction:column;gap:10px;font-size:14px}.cache-actions .el-button{margin:0}
</style>
