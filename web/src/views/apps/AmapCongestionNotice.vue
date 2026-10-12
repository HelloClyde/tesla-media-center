<script setup lang="ts">
import { computed } from 'vue';
import { formatDistance } from './amapNavigation';
import { formatRemainingDuration } from './amapRouteSummary';
import type { CongestionNotice } from './amapRouteTraffic';

const props = defineProps<{ notice: CongestionNotice }>();
const label = computed(() => props.notice.status === 4 ? '严重拥堵' : props.notice.status === 3 ? '拥堵' : '缓行');
const duration = computed(() => formatRemainingDuration(props.notice.duration).replace(/^约\s*/, ''));
</script>

<template>
  <aside class="congestion-notice" :class="`congestion-${notice.status}`" aria-label="拥堵路段耗时">
    <div class="congestion-heading"><span class="congestion-dot" aria-hidden="true"></span><span>{{ notice.active ? '正在' : '前方' }}{{ label }}</span><small v-if="!notice.active">{{ formatDistance(notice.distance) }}后</small></div>
    <strong v-if="notice.duration !== null">{{ notice.active ? '预计还需' : '预计通过' }} {{ duration }}</strong>
    <strong v-else class="time-pending">通过时间待更新</strong>
    <small>{{ notice.active ? '剩余' : '路段长' }} {{ formatDistance(notice.length) }}</small>
  </aside>
</template>

<style scoped>
.congestion-notice{--traffic-color:#f5a623;padding:9px 12px;box-sizing:border-box;border-radius:14px;border:1px solid #ffffffc9;border-left:3px solid var(--traffic-color);background:#fffffff2;box-shadow:0 4px 18px #183c3420;color:#213c36;min-width:0;font-variant-numeric:tabular-nums}
.congestion-3{--traffic-color:#e44650}.congestion-4{--traffic-color:#923d6d}
.congestion-heading{display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600;flex-wrap:wrap}.congestion-heading small{margin-left:auto;font-weight:400}
.congestion-dot{width:7px;height:7px;border-radius:50%;background:var(--traffic-color);flex:none}
.congestion-notice strong{display:block;font-size:17px;line-height:1.4;margin:3px 0}.congestion-notice small{font-size:11px;color:#6f837b}.congestion-notice .time-pending{font-size:14px;font-weight:500}
@media(max-width:520px){.congestion-notice{padding:7px 8px;border-radius:12px}.congestion-notice strong{font-size:14px}.congestion-heading{font-size:11px}.congestion-heading small{margin-left:0}.congestion-notice small{font-size:10px}}
</style>
