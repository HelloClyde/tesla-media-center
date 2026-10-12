<script setup lang="ts">
import { computed } from 'vue';
import type { AppRoute } from './amapNavigation';
import { formatRouteDuration, formatRouteTolls } from './amapRouteSummary';
import { ROUTE_BUBBLE_WIDTH, ROUTE_BUBBLE_HEIGHT, routePreviewColor, type RouteBubblePlacement } from './amapRoutePreview';

const props = defineProps<{ routes: AppRoute[]; placements: RouteBubblePlacement[]; selected: number; navigating?: boolean }>();
const visiblePlacements = computed(() => props.placements.filter(bubble => props.routes[bubble.index]));
defineEmits<{ select: [index: number] }>();
</script>

<template>
  <div class="route-preview-bubbles" :class="{ navigating }" aria-label="地图路线方案">
    <svg class="route-bubble-leaders" aria-hidden="true">
      <g v-for="bubble in visiblePlacements" :key="bubble.index" :stroke="routePreviewColor(bubble.index, selected, navigating)">
        <line :x1="bubble.anchor.x" :y1="bubble.anchor.y" :x2="bubble.x" :y2="bubble.y" stroke-width="1.5" />
        <circle :cx="bubble.anchor.x" :cy="bubble.anchor.y" r="3" fill="white" stroke-width="2" />
      </g>
    </svg>
    <button v-for="bubble in visiblePlacements" :key="bubble.index" type="button" class="route-preview-bubble"
      :class="{ selected: selected === bubble.index }" :aria-pressed="selected === bubble.index"
      :aria-label="`选择方案 ${bubble.index + 1}，${formatRouteDuration(routes[bubble.index].duration)}，${formatRouteTolls(routes[bubble.index])}`"
      :style="{ left: `${bubble.x}px`, top: `${bubble.y}px`, width: `${ROUTE_BUBBLE_WIDTH}px`, height: `${ROUTE_BUBBLE_HEIGHT}px`, '--route-color': routePreviewColor(bubble.index, selected, navigating) }"
      @click.stop="$emit('select', bubble.index)">
      <span class="route-bubble-heading"><i>{{ bubble.index + 1 }}</i><strong :title="formatRouteDuration(routes[bubble.index].duration)">{{ formatRouteDuration(routes[bubble.index].duration) }}</strong></span>
      <small :title="formatRouteTolls(routes[bubble.index])">{{ formatRouteTolls(routes[bubble.index]) }}</small>
    </button>
  </div>
</template>

<style scoped>
.route-preview-bubbles{position:absolute;inset:0;z-index:450;pointer-events:none}.route-bubble-leaders{position:absolute;inset:0;width:100%;height:100%;overflow:hidden}
.route-preview-bubbles .route-preview-bubble{position:absolute;transform:translate(-50%,-50%);box-sizing:border-box;pointer-events:auto;min-height:0;padding:7px 9px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:3px;border:2px solid var(--route-color);border-radius:13px;background:#fffffff5;box-shadow:0 3px 12px #183c3428;text-align:left;cursor:pointer;color:#344f48}
.route-preview-bubble.selected{background:#edfff6;color:#078161;box-shadow:0 3px 14px #087e5538}
.navigating .route-preview-bubble.selected{background:#eef6ff;color:#126cbd;box-shadow:0 3px 14px #1688ef38}
.route-bubble-heading{display:flex;align-items:center;gap:6px;width:100%;min-width:0}.route-bubble-heading i{display:grid;place-items:center;flex:none;width:18px;height:18px;background:var(--route-color);color:white;border-radius:50%;font-size:11px;font-style:normal;font-weight:700}.route-bubble-heading strong{font-size:14px;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.route-preview-bubble small{font-size:11px;line-height:1.2;white-space:nowrap;margin-left:24px;max-width:calc(100% - 24px);overflow:hidden;text-overflow:ellipsis}
.route-preview-bubble:focus-visible{outline:3px solid #0d9f75;outline-offset:3px}
</style>
