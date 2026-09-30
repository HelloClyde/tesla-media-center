<script setup lang="ts">
import { reactive, onUnmounted, computed, ref } from 'vue';
import { createMotionCapture, initialMotionState } from '@/functions/motionCapture';
import { useGeoLocationStore } from '@/stores/geoLocation';
const state = reactive(initialMotionState());
const capture = createMotionCapture(state);
const geoLocation = useGeoLocationStore();
const gpsCount = ref(0);
const listenerId = `motion-recording-${Math.random().toString(36).slice(2)}`;
geoLocation.addListener(listenerId, fix => {
  if (fix.source !== 'gps') return;
  const count = capture.recordGps(fix);
  if (count !== undefined) gpsCount.value = count;
});
function start() {
  gpsCount.value = 0;
  // Permission must be requested synchronously from the button gesture.
  const pending = capture.start();
  geoLocation.init();
  geoLocation.refresh();
  return pending;
}
const running = computed(() => ['permission', 'waiting', 'receiving'].includes(state.status));
const vector = (v?: number[]) => v ? v.map(n => n.toFixed(4)).join(' / ') : '暂无数据';
function download() {
  const url = URL.createObjectURL(new Blob([JSON.stringify(capture.recording())], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = 'tmc-motion.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
onUnmounted(() => { capture.stop(); geoLocation.removeListener(listenerId); });
</script>

<template>
  <section class="motion-test">
    <h2>惯性传感器</h2>
    <p>检测浏览器是否提供连续加速度与角速度，供高德惯性定位接入使用。</p>
    <div class="motion-actions">
      <el-button type="primary" :disabled="running" @click="start">开始采集</el-button>
      <el-button @click="capture.stop">停止</el-button>
      <el-button :disabled="!state.count" @click="download">导出数据</el-button>
    </div>
    <p role="status">{{ state.message }}</p>
    <dl>
      <div><dt>完整样本</dt><dd>{{ state.count }}</dd></div>
      <div><dt>同步 GPS 记录</dt><dd>{{ gpsCount }}</dd></div>
      <div><dt>不完整事件</dt><dd>{{ state.incomplete }}</dd></div>
      <div><dt>平均采样率</dt><dd>{{ state.hz.toFixed(1) }} Hz</dd></div>
      <div><dt>含重力加速度 x / y / z（m/s²）</dt><dd>{{ vector(state.latest?.acceleration) }}</dd></div>
      <div><dt>角速度 x / y / z（rad/s）</dt><dd>{{ vector(state.latest?.angularVelocity) }}</dd></div>
    </dl>
    <p class="motion-note">导出包含原始传感器和 GPS 位置，各保留最近 3000 条，仅在本机保存。两类数据使用同一到达时钟，GPS 原始时间和缺失字段也会保留。离开此栏目或隐藏页面会停止采集。收到数据不代表高德惯性导航已接通。</p>
  </section>
</template>

<style scoped>
.motion-test { padding: 24px; border: 1px solid #ccd6df; border-radius: 20px; }
.motion-test h2 { margin-top: 0; }
.motion-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.motion-actions :deep(.el-button) { margin-left: 0; }
dl { display: grid; gap: 12px; }
dl > div { padding: 14px; background: #849aaa12; border-radius: 12px; }
dt, .motion-note { color: #6a7e8c; }
dd { margin: 8px 0 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
</style>
