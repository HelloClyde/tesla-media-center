<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue';
import { initialMotionState } from '@/functions/motionCapture';
import { createBrowserInertialStream } from '@/functions/browserInertialStream';
import type { InertialResult } from '@/functions/inertialSession';
import { useGeoLocationStore } from '@/stores/geoLocation';
const motion = reactive(initialMotionState());
const geo = useGeoLocationStore();
const running = ref(false), message = ref('尚未开始实时联调');
const result = ref<InertialResult | null>(null);
let stream: ReturnType<typeof createBrowserInertialStream> | undefined;
function stop() { stream?.stop(); stream = undefined; running.value = false; message.value = '实时联调已停止'; }
async function start() {
  stop(); running.value = true; result.value = null; message.value = '正在连接惯性引擎';
  const current = createBrowserInertialStream(motion, receive => {
    const id = `inertial-debug-${Math.random().toString(36).slice(2)}`;
    geo.addListener(id, receive); geo.init(); geo.refresh();
    return () => geo.removeListener(id);
  }, value => { result.value = value; message.value = value.output ? '已收到惯性引擎位置' : '引擎正在等待初始化'; },
  error => { message.value = error; running.value = false; });
  stream = current;
  const ready = await current.start();
  if (stream === current && ready) message.value = '已连接，等待传感器与 GPS 数据';
}
onUnmounted(stop);
</script>
<template>
  <section class="inertial-stream">
    <h3>惯性引擎实时联调</h3>
    <p>将加速度、角速度和有效 GPS 发送到当前 TMC 服务，展示引擎返回的位置。此测试不会替换导航位置。</p>
    <el-button type="primary" :disabled="running" @click="start">开始实时联调</el-button>
    <el-button :disabled="!running" @click="stop">停止联调</el-button>
    <p role="status">{{ message }}</p>
    <p v-if="running">{{ motion.message }} · {{ motion.hz.toFixed(1) }} Hz · {{ motion.count }} 个样本</p>
    <pre v-if="result">{{ JSON.stringify(result, null, 2) }}</pre>
  </section>
</template>
<style scoped>
.inertial-stream { margin-top: 24px; padding-top: 16px; border-top: 1px solid #849aaa40; }
p { color: #6a7e8c; } pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
