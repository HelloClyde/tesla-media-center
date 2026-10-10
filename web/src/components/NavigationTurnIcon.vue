<script setup lang="ts">
import {computed, useId} from 'vue';
import {navigationArrowAsset} from './navigationArrow';
const props = defineProps<{ arrow: string }>();
const source = computed(() => navigationArrowAsset(props.arrow));
const maskId = `navigation-arrow-${useId()}`;
</script>
<template>
  <svg viewBox="0 0 240 240" aria-hidden="true" focusable="false">
    <defs><mask :id="maskId" x="0" y="0" width="240" height="240" maskUnits="userSpaceOnUse" style="mask-type:alpha">
      <image :href="source" width="240" height="240" preserveAspectRatio="xMidYMid meet" />
    </mask></defs>
    <!-- Preserve the APK silhouette while inheriting the card's foreground
         colour, including the light-background task dock. -->
    <rect width="240" height="240" fill="currentColor" :mask="`url(#${maskId})`" />
  </svg>
</template>
