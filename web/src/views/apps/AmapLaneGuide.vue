<script setup lang="ts">
import { computed } from 'vue';
import { laneArrowAsset, type UpcomingLaneGuide } from './amapLaneGuidance';

const props = defineProps<{ guide: UpcomingLaneGuide }>();
const arrows = computed(() => props.guide.variant.back.map((back, index) => ({
  src: laneArrowAsset(back, props.guide.variant.front[index]),
  recommended: props.guide.variant.front[index] !== 255,
})));
const label = computed(() => {
  const guided = arrows.value.flatMap((lane, index) => lane.recommended ? [index + 1] : []);
  return `前方 ${Math.round(props.guide.distance)} 米车道引导，${guided.length ? `引导箭头位于第 ${guided.join('、')} 车道` : '请按道路标志选择车道'}`;
});
</script>

<template>
  <div class="lane-guide" role="status" :aria-label="label">
    <small>车道引导 · {{ Math.round(guide.distance) }} 米</small>
    <div class="lane-arrows" aria-hidden="true">
      <div v-for="(arrow, index) in arrows" :key="index" class="lane-arrow">
        <img v-if="arrow.src" :src="arrow.src" alt="" />
        <span v-else>—</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lane-guide{width:100%;padding:7px 12px 9px;background:#142338;color:#fff}
.lane-guide small{display:block;margin-bottom:2px;color:#bed4d8;font-size:11px}
.lane-arrows{display:flex;align-items:center;justify-content:center;max-width:100%;overflow:hidden}
.lane-arrow{flex:1 1 0;min-width:0;max-width:52px;height:62px;display:flex;align-items:center;justify-content:center}
.lane-arrow+.lane-arrow{border-left:1px solid #879eae66}
.lane-arrow img{display:block;width:100%;height:100%;object-fit:contain}
.lane-arrow span{color:#879eae}
</style>
