<script setup lang="ts">
import { onBeforeUnmount } from 'vue';
import { RouterView } from 'vue-router';
import { installMusicTitle } from './functions/musicPresentation';


// Keep track information visible even while another application is open.
onBeforeUnmount(installMusicTitle());

</script>

<template>
  <RouterView />
</template>
