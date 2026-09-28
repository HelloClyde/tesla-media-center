<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
const props = defineProps<{ text: string }>();
const viewport = ref<HTMLElement>(), content = ref<HTMLElement>();
const distance = ref(0);
const style = computed(() => ({ '--title-distance': '-' + distance.value + 'px', '--title-duration': Math.max(6, distance.value / 28 + 3) + 's' }));
let observer: ResizeObserver | undefined;
let disposed = false;
function measure() { distance.value = Math.max(0, (content.value?.scrollWidth || 0) - (viewport.value?.clientWidth || 0)); }
watch(() => props.text, async () => { distance.value = 0; await nextTick(); if (!disposed) measure(); });
onMounted(() => {
  measure();
  if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(measure); if (viewport.value) observer.observe(viewport.value); if (content.value) observer.observe(content.value); }
  void document.fonts?.ready.then(() => { if (!disposed) measure(); });
});
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); });
</script>
<template>
  <span ref="viewport" class="scrolling-title" :title="text" :style="style">
    <span :key="text" ref="content" class="title-content" :class="{ scrolling: distance > 1 }">{{ text }}</span>
  </span>
</template>
<style scoped>
.scrolling-title{display:block;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:clip!important}
.title-content{display:inline-block;width:max-content;max-width:none;vertical-align:middle}
.scrolling{animation:title-pan var(--title-duration) linear infinite alternate}
@keyframes title-pan{0%,15%{transform:translateX(0)}85%,100%{transform:translateX(var(--title-distance))}}
@media(prefers-reduced-motion:reduce){.scrolling{animation:none}.scrolling-title{overflow-x:auto;scrollbar-width:none}.scrolling-title::-webkit-scrollbar{display:none}}
</style>
