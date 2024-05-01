<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'

const state = reactive({
  iframeUrl: '',
})



function fetchConfig() {
  get(`/api/config`, '读取配置失败')
    .then(data => {
      state.iframeUrl = data['home_page_iframe']
    });
}

onMounted(() => {
  fetchConfig();
})
</script>


<template>
  <iframe class="home-iframe" :src="state.iframeUrl" scrolling="no"></iframe>
</template>


<style>
.home-iframe {
  width: 100%;
  height: 100%;
}
</style>