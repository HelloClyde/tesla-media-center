<script setup lang="ts">
defineProps<{ roadJpeg: string; arrowPng: string; width: number; height: number }>();
</script>

<template>
  <div class="junction-preview" aria-label="高德原版路口放大图">
    <div class="junction-picture" :style="{ aspectRatio: `${width} / ${height}` }">
      <img :src="`data:image/jpeg;base64,${roadJpeg}`" alt="路口道路示意" />
      <img class="junction-arrow" :src="`data:image/png;base64,${arrowPng}`" alt="应走路线" />
    </div>
  </div>
</template>

<style scoped>
.junction-preview{width:100%;overflow:hidden;background:#15242b}
.junction-picture{position:relative;width:100%;overflow:hidden}
.junction-picture img{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}
.junction-picture .junction-arrow{pointer-events:none}
</style>
