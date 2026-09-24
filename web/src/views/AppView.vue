<script setup lang="ts">
import { House, VideoPlay, Monitor, MapLocation } from '@element-plus/icons-vue';
import { reactive } from 'vue';
import { RouterView,useRouter } from 'vue-router';

console.info('origin ua:', navigator.userAgent);
Object.defineProperty(navigator, 'userAgent', {
  value: navigator.userAgent + ';Android 6.0;Linux x86_64',
  writable: true
})
console.info('amap ua:', navigator.userAgent);

const router = useRouter();

const state = reactive({
  // isTesla: navigator.userAgent.toLowerCase().indexOf('tesla') >= 0,
  isTesla: true,
  menuTopItems: [{icon: House, route:'/apps/home'}],
  menuItems: [
    {icon: MapLocation, route: '/apps/nav'},
    {icon: '/icon/TESLA_LOGO.svg', route: '/apps/tesla'},
    // {icon: Headset, route: 'music'},
    {icon: '/icon/BILIBILI_LOGO.svg', route: '/apps/bilibili'},
    {icon: '/icon/GBA_LOGO.svg', route: '/apps/gba'},
    {icon: VideoPlay, route: '/apps/video'},
    // {icon: SwitchFilled, route: 'game'},
    {icon: Monitor, route: '/apps/debug'},
    // {icon: Setting, route: 'setting'},
    // {icon: Compass, route: 'brower'},
  ],
  curMenu: router.currentRoute.value.path
})


function routeTo(name: string){
  router.push(name);
  state.curMenu = name;
}

</script>

<template>
  <template v-if="state.isTesla">
    <div class="app-shell">
      <div class="menu">
        <div class="menu-top">
          <div class="menu-item" v-for="item of state.menuTopItems">
            <el-icon @click="routeTo(item.route)">
              <component :is="item.icon"></component>
            </el-icon>
          </div>
        </div>
        <div class="menu-bottom">
          <div class="menu-item" :class="{ 'menu-item-active': item.route == state.curMenu }" v-for="item of state.menuItems">
            <el-icon @click="routeTo(item.route)" v-if="typeof(item.icon) === 'string'" :class="{ 'menu-icon-bilibili': item.route === '/apps/bilibili' }">
              <img :src="item.icon" class="icon-svg" />
            </el-icon>
            <el-icon @click="routeTo(item.route)" v-else>
              <component :is="item.icon"></component>
            </el-icon>
          </div>
        </div>
      </div>
      <div class="main-view">
        <RouterView />
      </div>
    </div>
  </template>
  <template v-else>
    <HomeViewPC />
  </template>
</template>

<style scoped>
.app-shell {
  --menu-width: clamp(48px, 6.4vw, 80px);
  --menu-item-height: clamp(44px, 11vh, 80px);
  display: flex;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.icon-svg {
  width: 100%;
  filter: drop-shadow(1000px 0 0 var(--color-text-soft));
  transform: translate(-1000px);
}

.menu-item-active .icon-svg
{
  filter: drop-shadow(1000px 0 0 var(--color-accent));
  transform: translate(-1000px);
}

.menu-icon-bilibili {
  transform: translateY(-10px);
}


.menu {
  width: var(--menu-width);
  flex: 0 0 var(--menu-width);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface);
  backdrop-filter: blur(18px);
  height: 100%;
}

.menu-bottom {
  margin-top: auto;
  width: 100%;
}

.menu-top {
  width: 100%;
}

.menu-item {
  font-size: clamp(26px, 3.8vw, 50px);
  width: 100%;
  height: var(--menu-item-height);
  line-height: var(--menu-item-height);
  text-align: center;
  color: var(--color-text-soft);
}

.menu-item-active {
  color: var(--color-accent);
}

.main-view {
  flex: 1 1 auto;
  min-width: 0;
  width: 0;
  height: 100%;
  overflow: auto;
  color: var(--color-text);
}

nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}

</style>
