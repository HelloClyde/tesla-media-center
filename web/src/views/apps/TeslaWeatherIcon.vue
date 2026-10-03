<script setup lang="ts">
import type { SceneWeather } from './teslaWeatherData';

defineProps<{ weather?: SceneWeather }>();
</script>

<template>
  <svg class="vehicle-weather-icon" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <g v-if="weather === 'clear'" stroke="#ffd36b" stroke-linecap="round" stroke-width="2.5">
      <circle cx="24" cy="24" r="8" fill="#ffd36b" stroke="none" />
      <path d="M24 4v5m0 30v5M4 24h5m30 0h5M9.9 9.9l3.6 3.6m21 21 3.6 3.6m0-28.2-3.6 3.6m-21 21-3.6 3.6" />
    </g>
    <template v-else>
      <circle v-if="weather === 'cloudy'" cx="17" cy="16" r="7" fill="#ffd36b" />
      <path d="M12 31.5h24a7 7 0 0 0 .6-14 12 12 0 0 0-22.8 1.1A6.5 6.5 0 0 0 12 31.5Z"
        fill="#a9bdcf" stroke="#e7f2fa" stroke-linejoin="round" stroke-width="1.5" />
      <g v-if="weather === 'rain'" stroke="#65c9ff" stroke-linecap="round" stroke-width="2.5">
        <path d="m17 36-2 5m10-5-2 5m10-5-2 5" />
      </g>
      <g v-else-if="weather === 'fog'" stroke="#c5d5e2" stroke-linecap="round" stroke-width="2.2">
        <path d="M9 36h27M14 41h21" />
      </g>
      <g v-else-if="weather === 'snow'" stroke="#b7e8ff" stroke-linecap="round" stroke-width="1.8">
        <path d="M17 36v7m-3.5-3.5h7M30 36v7m-3.5-3.5h7" />
      </g>
    </template>
  </svg>
</template>

<style scoped>
.vehicle-weather-icon { display: block; width: 40px; height: 40px; flex: none; filter: drop-shadow(0 2px 5px #0005); }
</style>
