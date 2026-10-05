<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{ arrow: string }>();
const paths: Record<string, string> = {
  '↰': 'M34 51V29Q34 20 25 20H10 M21 9 10 20 21 31',
  '↱': 'M22 51V29Q22 20 31 20H46 M35 9 46 20 35 31',
  '↶': 'M42 51V23a14 14 0 0 0-28 0v15 M5 29 14 38 23 29',
  '↑': 'M28 51V10 M15 23 28 10 41 23',
  '⚑': 'M14 52V10 M14 12h28l-7 10 7 10H14',
  '⟳': 'M28 54V45a16 16 0 1 1 16-16V9 M34 19 44 9 54 19',
};
const path = computed(() => paths[props.arrow] || paths['↑']);
</script>
<template>
  <svg viewBox="0 0 56 64" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path :d="path" /></svg>
</template>
