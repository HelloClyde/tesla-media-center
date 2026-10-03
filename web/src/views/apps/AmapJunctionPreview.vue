<script setup lang="ts">
defineProps<{ roadJpeg: string; arrowPng: string; distance: number; instruction: string; width: number; height: number }>();
</script>

<template>
  <aside class="junction-preview" aria-label="高德原版路口放大图">
    <header><strong>{{ instruction }}</strong><span>{{ Math.round(Math.max(0, distance)) }} 米</span></header>
    <div class="junction-picture" :style="{ aspectRatio: `${width} / ${height}` }">
      <img :src="`data:image/jpeg;base64,${roadJpeg}`" alt="路口道路示意" />
      <img class="junction-arrow" :src="`data:image/png;base64,${arrowPng}`" alt="应走路线" />
    </div>
  </aside>
</template>

<style scoped>
.junction-preview{position:absolute;right:66px;top:126px;width:min(360px,calc(100% - 90px));z-index:490;overflow:hidden;border:1px solid #ffffffa8;border-radius:16px;box-shadow:0 10px 28px #102b3555;background:#15242b;color:#fff}
header{height:42px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 14px;background:#123f38}
header strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
header span{flex-shrink:0;color:#8af0ca;font-variant-numeric:tabular-nums;font-size:13px}
.junction-picture{position:relative;width:100%;overflow:hidden}
.junction-picture img{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}
.junction-picture .junction-arrow{pointer-events:none}
@media(max-width:850px){.junction-preview{top:126px;right:64px;width:min(270px,calc(100% - 86px))}}
@media(max-height:550px){.junction-preview{top:116px;width:225px}}
</style>
