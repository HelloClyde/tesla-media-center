<script setup lang="ts">
import { House, VideoPlay, Monitor } from '@element-plus/icons-vue';
import { reactive } from 'vue';
import { RouterView,useRouter } from 'vue-router';
import BackgroundMusic from '@/components/BackgroundMusic.vue';

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
  menuTopItems: [{icon: House, label: '首页', route:'/apps/home'}],
  menuItems: [
    {icon: '/icon/AMAP_LOGO.ico', label: '高德导航（实验）', route: '/apps/amap'},
    {icon: '/icon/TESLA_LOGO.svg', label: '特斯拉', route: '/apps/tesla'},
    {icon: '/icon/QQMUSIC_LOGO.ico', label: 'QQ 音乐', route: '/apps/qqmusic'},
    {icon: '/icon/BILIBILI_LOGO.svg', label: '哔哩哔哩', route: '/apps/bilibili'},
    {icon: '/icon/GBA_LOGO.svg', label: '游戏', route: '/apps/gba'},
    {icon: VideoPlay, label: '本地播放器', route: '/apps/video'},
    // {icon: SwitchFilled, route: 'game'},
    {icon: Monitor, label: '设置与调试', route: '/apps/debug'},
    // {icon: Setting, route: 'setting'},
    // {icon: Compass, route: 'brower'},
  ]
})


function routeTo(name: string){
  router.push(name);
}

</script>

<template>
  <template v-if="state.isTesla">
    <div class="app-shell">
      <div class="menu">
        <div class="menu-top">
          <button type="button" class="menu-item" v-for="item of state.menuTopItems" :key="item.route" :class="{ 'menu-item-active': item.route === router.currentRoute.value.path }" :aria-label="item.label" :title="item.label" :aria-current="item.route === router.currentRoute.value.path ? 'page' : undefined" @click="routeTo(item.route)">
            <el-icon>
              <component :is="item.icon"></component>
            </el-icon>
          </button>
        </div>
        <div class="menu-bottom">
          <button type="button" class="menu-item" v-for="item of state.menuItems" :key="item.route" :class="{ 'menu-item-active': item.route === router.currentRoute.value.path, 'menu-item-qqmusic': item.route === '/apps/qqmusic' }" :aria-label="item.label" :title="item.label" :aria-current="item.route === router.currentRoute.value.path ? 'page' : undefined" @click="routeTo(item.route)">
            <el-icon v-if="typeof(item.icon) === 'string'" :class="{ 'menu-icon-bilibili': item.route === '/apps/bilibili', 'menu-icon-qqmusic': item.route === '/apps/qqmusic', 'menu-icon-brand': item.route === '/apps/amap' }">
              <img :src="item.icon" class="icon-svg" alt="" />
            </el-icon>
            <el-icon v-else>
              <component :is="item.icon"></component>
            </el-icon>
          </button>
        </div>
        <BackgroundMusic />
      </div>
      <div class="main-view">
        <RouterView v-slot="{ Component }"><KeepAlive include="QQMusicView"><component :is="Component" /></KeepAlive></RouterView>
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
  --menu-blend-width: clamp(16px, 2.5vw, 24px);
  isolation: isolate;
  display: flex;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

/* A shared glass layer extends across the seam, outside the scrolling menu.
   Keep icons above it and let pointer events reach the application below. */
.app-shell::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: calc(var(--menu-width) + var(--menu-blend-width));
  z-index: 20;
  pointer-events: none;
  background: linear-gradient(90deg,
    var(--color-surface) 0%,
    var(--color-surface) calc(var(--menu-width) - 12px),
    transparent 100%);
  -webkit-backdrop-filter: blur(16px) saturate(135%);
  backdrop-filter: blur(16px) saturate(135%);
  -webkit-mask-image: linear-gradient(90deg, #000 var(--menu-width), transparent 100%);
  mask-image: linear-gradient(90deg, #000 var(--menu-width), transparent 100%);
}

.icon-svg {
  width: 100%;
  object-fit: contain;
}

.el-icon:not(.menu-icon-qqmusic):not(.menu-icon-brand) .icon-svg {
  filter: drop-shadow(1000px 0 0 var(--color-text-soft));
  transform: translate(-1000px);
}

.menu-item-active .el-icon:not(.menu-icon-qqmusic):not(.menu-icon-brand) .icon-svg
{
  filter: drop-shadow(1000px 0 0 var(--color-accent));
  transform: translate(-1000px);
}




.menu {
  position: relative;
  z-index: 21;
  width: var(--menu-width);
  flex: 0 0 var(--menu-width);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border-right: 0;
  background: transparent;
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
  --menu-active-color: var(--color-accent);
  --menu-active-bg: var(--color-accent-soft);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-size: clamp(26px, 3.8vw, 42px);
  width: 100%;
  height: var(--menu-item-height);
  line-height: var(--menu-item-height);
  text-align: center;
  color: var(--color-text-soft);
}

.menu-item::before {
  content: '';
  position: absolute;
  left: 5px;
  right: 5px;
  top: 50%;
  height: min(calc(var(--menu-width) - 10px), calc(var(--menu-item-height) - 6px));
  border-radius: 12px;
  transform: translateY(-50%);
  background: var(--menu-active-bg);
  opacity: 0;
  transition: opacity .15s ease;
}

.menu-item::after {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  transform: translateY(-50%);
  background: var(--menu-active-color);
  opacity: 0;
}

.menu-item > .el-icon { position: relative; }
.menu-item-qqmusic { --menu-active-color: #19b978; --menu-active-bg: rgba(25,185,120,.14); }
.menu-item-active::before, .menu-item-active::after { opacity: 1; }
.menu-item:focus-visible { outline: 2px solid var(--menu-active-color); outline-offset: -3px; border-radius: 12px; }
@media (hover: hover) { .menu-item:hover::before { opacity: .6; } .menu-item-active:hover::before { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .menu-item::before { transition: none; } }

.menu-item-active {
  color: var(--menu-active-color);
}

.main-view {
  position: relative;
  z-index: 0;
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
