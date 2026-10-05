<script setup lang="ts">
import { onMounted, ref } from 'vue';
import axios from 'axios';
import { browserMapCacheStats, clearBrowserMapCache, updateBrowserMapCacheConfig } from '@/views/apps/amapBrowserTileCache';
const ttlHours = ref(168), maxMB = ref(512), usedBytes = ref(0), count = ref(0);
const busy = ref(false), ready = ref(false), message = ref('');
const device = ref<{available:boolean;count:number;usedBytes:number;ttlHours:number;maxMB:number}>();
const deviceTtlHours=ref(168), deviceMaxMB=ref(96);
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
    <p>当前车机保存已解码的 App 地图块和特色地标模型；3D 建筑瓦片也可供 2D 使用。浏览器不支持持久存储时继续使用服务器缓存。</p>
    <div class="cache-fields">
      <label>有效期（小时）<el-input-number v-model="deviceTtlHours" :min="1" :max="2160" :precision="0" :disabled="deviceBusy || !device?.available" /></label>
      <label>容量上限（MB）<el-input-number v-model="deviceMaxMB" :min="16" :max="512" :precision="0" :disabled="deviceBusy || !device?.available" /></label>
    </div>
    <p v-if="device">{{ device.available ? `本机已缓存 ${device.count} 个地图资源 · ${(device.usedBytes / 1048576).toFixed(2)} MB` : '本机浏览器不支持持久地图缓存' }}</p>
    <div class="cache-actions">
      <el-button type="primary" :disabled="deviceBusy || !device?.available" @click="saveDevice">保存本机设置</el-button>
      <el-button :disabled="deviceBusy" @click="refreshDevice">刷新本机用量</el-button>
      <el-button :disabled="deviceBusy || !device?.available" @click="clearDevice">清空本机缓存</el-button>
    </div>
    <p role="status">{{ deviceMessage }}</p>
  </section>
</template>
<style scoped>
.map-cache-settings{padding:20px;max-width:760px;color:var(--color-text)}h3{font-size:19px;margin-bottom:12px}p{font-size:13px;line-height:1.8;color:var(--color-text-soft);margin:12px 0}.cache-fields,.cache-actions{display:flex;flex-wrap:wrap;gap:16px}.cache-fields label{display:flex;flex-direction:column;gap:10px;font-size:14px}.cache-actions .el-button{margin:0}
</style>
