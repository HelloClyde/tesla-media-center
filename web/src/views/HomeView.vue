<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import axios from 'axios';

const state = reactive({
  iframeUrl: '',
})



function fetchConfig() {
    axios.get(`/api/config`)
        .then(response => {
          state.iframeUrl = response.data['home_page_iframe']
        })
        .catch(function (error) { // 请求失败处理
            console.log(error);
        });
}

onMounted(() => {
  fetchConfig();
})
</script>


<template>
  <iframe class="home-iframe" :src="state.iframeUrl"></iframe>
</template>


<style>
.home-iframe {
  width: 100%;
  height: 100%;
}
</style>