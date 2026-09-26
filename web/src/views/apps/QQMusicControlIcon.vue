<script setup lang="ts">
defineProps<{ kind: 'order' | 'loop' | 'single' | 'shuffle' | 'equalizer' }>();
</script>
<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="control-icon">
    <template v-if="kind === 'equalizer'"><path d="M5 3v7m0 4v7M12 3v12m0 4v2M19 3v3m0 4v11" /><path d="M2 10h6v4H2zM9 15h6v4H9zM16 6h6v4h-6z" /></template>
    <template v-else-if="kind === 'shuffle'"><path d="M3 6h2c5 0 9 12 14 12h2m-4-4 4 4-4 4M3 18h2c2 0 4-2 5-4m4-4c2-3 3-4 5-4h2m-4-4 4 4-4 4" /></template>
    <template v-else-if="kind === 'order'"><path d="M4 5h12M4 10h12M4 15h7M18 11v10m-3-3 3 3 3-3" /></template>
    <template v-else><path d="m16 2 4 4-4 4M20 6H7a4 4 0 0 0-4 4m5 12-4-4 4-4M4 18h13a4 4 0 0 0 4-4" /><path v-if="kind === 'single'" d="m10 10 2-1v6m-2 0h4" /></template>
  </svg>
</template>
<style scoped>.control-icon{width:20px;height:20px;display:block;flex-shrink:0}</style>
