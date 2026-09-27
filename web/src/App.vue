<script setup lang="ts">
import { watchEffect } from 'vue';
import { RouterView } from 'vue-router';
import { backgroundMusic } from './stores/backgroundMusic';


// Keep track information visible even while another application is open.
watchEffect(() => {
  const song = backgroundMusic.song;
  document.title = backgroundMusic.playing && song
    ? `${[song.title, song.singer].filter(Boolean).join(' - ')} · TMC`
    : 'TMC · 车载媒体中心';
});

</script>

<template>
  <RouterView />
</template>
