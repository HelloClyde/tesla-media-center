<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router';
import { monitorPublisher as publisher, stopMonitorPublisher } from '@/views/apps/monitor/publisher';
const route = useRoute(), router = useRouter();
</script>
<template>
  <aside v-if="publisher.phase !== 'idle' && route.path !== '/apps/monitor'" class="monitor-status" aria-label="车内监控运行状态">
    <button class="status-link" @click="router.push('/apps/monitor')"><span :class="{live:publisher.phase === 'connected'}"/><strong>{{ publisher.phase === 'connected' ? '监控已开启' : '监控连接中' }}</strong><small>{{ publisher.talking ? '车主正在对讲' : `${publisher.viewers} 人观看` }}</small></button>
    <button class="stop" @click="stopMonitorPublisher">停止</button>
  </aside>
</template>
<style scoped>
.monitor-status{position:absolute;z-index:1900;top:8px;right:70px;display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid #97ddc7;border-radius:14px;background:#f0fff8ee;box-shadow:0 3px 14px #16342e20;color:#126b50}.monitor-status button{border:0;background:none;color:inherit;cursor:pointer}.status-link{display:flex;align-items:center;gap:7px}.status-link span{width:8px;height:8px;border-radius:50%;background:#e5ad4d}.status-link span.live{background:#13ab78;box-shadow:0 0 0 3px #13ab7820}.status-link strong{font-size:12px}.status-link small{font-size:11px}.monitor-status .stop{font-size:12px;border-left:1px solid #bddbcc;padding-left:9px}@media(max-width:550px){.status-link small{display:none}.monitor-status{right:62px}}
</style>
