<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router';
import { backgroundNavigation as nav, navigationCommands } from '@/stores/backgroundNavigation';
import NavigationTurnIcon from './NavigationTurnIcon.vue';
const route = useRoute(), router = useRouter();
</script>
<template>
  <aside v-if="nav.active && route.path !== '/apps/amap'" class="navigation-float" aria-label="后台导航">
    <button class="guidance" aria-label="返回高德导航" @click="router.push('/apps/amap')">
      <NavigationTurnIcon :arrow="nav.arrow" />
      <span><small>{{ nav.simulated ? '模拟导航' : '正在导航' }} · 剩余 {{ nav.remaining }}</small><strong>{{ nav.instruction }}</strong><span>{{ nav.road }}</span></span>
    </button>
    <p v-if="nav.status">{{ nav.status }}</p>
    <div class="actions"><button @click="navigationCommands.toggleVoice?.()">{{ nav.muted ? '开启语音' : '静音' }}</button><button @click="navigationCommands.stop?.()">结束导航</button></div>
  </aside>
</template>
<style scoped>
.navigation-float{position:absolute;right:16px;top:16px;z-index:21;width:min(340px,calc(100% - var(--menu-width) - 32px));box-sizing:border-box;padding:14px;border:1px solid #ffffff40;border-radius:20px;background:#123f38f2;color:white;box-shadow:0 8px 28px #0003;backdrop-filter:blur(16px)}
.guidance{display:flex;align-items:center;gap:12px;width:100%;text-align:left}.guidance svg{width:40px;height:48px;flex-shrink:0}.guidance>span{min-width:0;display:grid;gap:5px}.guidance strong{font-size:20px}.guidance small{color:#a8e1d2}.guidance span span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.navigation-float button{border:0;color:inherit;background:transparent;cursor:pointer;padding:0;min-height:40px}.navigation-float p{font-size:12px;opacity:.75;margin:8px 0}.actions{display:flex;justify-content:flex-end;gap:10px}.actions button{padding:4px 12px;border-radius:10px;background:#ffffff18}
</style>
