<script setup lang="ts">
import { Grid } from '@element-plus/icons-vue';
import { applications } from '@/apps';
import { computed, reactive, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import AppLauncher from './apps/HomeView.vue';
import { RouterView,useRouter } from 'vue-router';
import BackgroundAppDock from '@/components/BackgroundAppDock.vue';
import BackgroundNavigation from '@/components/BackgroundNavigation.vue';
import { startLayoutDiagnostics } from '@/functions/viewportDiagnostics';
const stopLayoutDiagnostics = startLayoutDiagnostics();
onBeforeUnmount(stopLayoutDiagnostics);

console.info('origin ua:', navigator.userAgent);
Object.defineProperty(navigator, 'userAgent', {
  value: navigator.userAgent + ';Android 6.0;Linux x86_64',
  writable: true
})
console.info('amap ua:', navigator.userAgent);

const router = useRouter();
const launcherOpen = ref(false);
const PIN_KEY='tmc:sidebar-pins:v1';
const pinnedRoutes=ref<string[]>((()=>{try{const value=JSON.parse(localStorage.getItem(PIN_KEY)||'null');if(Array.isArray(value))return [...new Set(value.filter(r=>applications.some(a=>a.route===r)))];}catch{}return applications.map(a=>a.route);})());
const pinnedApps=computed(()=>pinnedRoutes.value.flatMap(r=>applications.find(a=>a.route===r)||[]));
const sidebar=ref<HTMLElement>();
const dragging=ref<{route:string;x:number;y:number;active:boolean;fromSidebar?:boolean;over:boolean;before:string|null}>();
const dragApp=computed(()=>applications.find(a=>a.route===dragging.value?.route));
const pinMessage=ref('');
let dragOrigin=[0,0], dragPointer=-1, suppressClickUntil=0;
function persistPins(){try{localStorage.setItem(PIN_KEY,JSON.stringify(pinnedRoutes.value));pinMessage.value='侧栏已保存';}catch{pinMessage.value='已更新侧栏，但浏览器无法保存设置';}}
function togglePin(route:string){if(pinnedRoutes.value.includes(route))pinnedRoutes.value=pinnedRoutes.value.filter(r=>r!==route);else pinnedRoutes.value.push(route);persistPins();}
let sidebarHold:ReturnType<typeof setTimeout>|undefined;
let holdOrigin=[0,0];
function clearSidebarHold(){if(sidebarHold)clearTimeout(sidebarHold);sidebarHold=undefined;}
function pressSidebar(route:string,event:PointerEvent){
  if(event.button!==0)return;clearSidebarHold();holdOrigin=[event.clientX,event.clientY];
  const element=event.currentTarget as HTMLElement;
  sidebarHold=setTimeout(()=>{sidebarHold=undefined;element.setPointerCapture?.(event.pointerId);startAppDrag(route,event);if(dragging.value){dragging.value.fromSidebar=true;moveAppDrag(event);}},450);
}
function holdMove(event:PointerEvent){if(sidebarHold&&Math.hypot(event.clientX-holdOrigin[0],event.clientY-holdOrigin[1])>10)clearSidebarHold();}
function dragTouchMove(event:TouchEvent){if(dragging.value?.fromSidebar&&event.cancelable)event.preventDefault();}
function startAppDrag(route:string,event:PointerEvent){
  if(event.button!==0||!applications.some(a=>a.route===route))return;
  dragOrigin=[event.clientX,event.clientY];dragPointer=event.pointerId;
  dragging.value={route,x:event.clientX,y:event.clientY,active:true,over:false,before:null};
  (event.currentTarget as HTMLElement)?.setPointerCapture?.(event.pointerId);
}
function moveAppDrag(event:PointerEvent){
  const d=dragging.value;if(!d||event.pointerId!==dragPointer)return;
  if(!d.active&&Math.hypot(event.clientX-dragOrigin[0],event.clientY-dragOrigin[1])<6)return;
  d.active=true;d.x=event.clientX;d.y=event.clientY;
  const rect=sidebar.value?.getBoundingClientRect();d.over=!!rect&&d.x>=rect.left&&d.x<=rect.right&&d.y>=rect.top&&d.y<=rect.bottom;
  d.before=null;
  if(d.over){
    for(const element of sidebar.value!.querySelectorAll<HTMLElement>('[data-pin-route]')){
      if(element.dataset.pinRoute===d.route)continue;
      const box=element.getBoundingClientRect();if(d.y<box.top+box.height/2){d.before=element.dataset.pinRoute!;break;}
    }
    if(rect&&d.y>rect.bottom-45)(sidebar.value!.querySelector('.menu-bottom') as HTMLElement).scrollTop+=12;
    if(rect&&d.y<rect.top+45)(sidebar.value!.querySelector('.menu-bottom') as HTMLElement).scrollTop-=12;
  }
  event.preventDefault();
}
function endAppDrag(event:PointerEvent){
  clearSidebarHold();
  const d=dragging.value;if(!d||event.pointerId!==dragPointer)return;
  if(d.active){suppressClickUntil=performance.now()+400;if(event.type==='pointerup'&&d.over){
    const routes=pinnedRoutes.value.filter(r=>r!==d.route),index=d.before?routes.indexOf(d.before):-1;
    routes.splice(index<0?routes.length:index,0,d.route);pinnedRoutes.value=routes;persistPins();
  }else if(event.type==='pointerup'&&d.fromSidebar){pinnedRoutes.value=pinnedRoutes.value.filter(r=>r!==d.route);persistPins();}}
  dragging.value=undefined;dragPointer=-1;
}
function suppressDragClick(event:MouseEvent){if(performance.now()<suppressClickUntil){event.preventDefault();event.stopImmediatePropagation();}}
function cancelDrag(){clearSidebarHold();dragging.value=undefined;dragPointer=-1;}

const launcherPanel = ref<HTMLElement>();
const launcherTrigger = ref<HTMLButtonElement>();
function dismissLauncher(event: PointerEvent) {
  const target = event.target as Node;
  if (launcherOpen.value && !launcherPanel.value?.contains(target) && !launcherTrigger.value?.contains(target)) launcherOpen.value = false;
}
function launcherKey(event: KeyboardEvent) {
  if(event.key==='Escape')cancelDrag();
  if (event.key === 'Escape' && launcherOpen.value) {
    launcherOpen.value = false;
    launcherTrigger.value?.focus();
  }
}
onMounted(() => { document.addEventListener('pointermove',holdMove);document.addEventListener('touchmove',dragTouchMove,{passive:false}); document.addEventListener('pointermove',moveAppDrag,{passive:false});document.addEventListener('pointerup',endAppDrag);document.addEventListener('pointercancel',endAppDrag);document.addEventListener('click',suppressDragClick,true);window.addEventListener('blur',cancelDrag); document.addEventListener('pointerdown', dismissLauncher); document.addEventListener('keydown', launcherKey); });
onBeforeUnmount(() => { clearSidebarHold();document.removeEventListener('pointermove',holdMove);document.removeEventListener('touchmove',dragTouchMove); document.removeEventListener('pointermove',moveAppDrag);document.removeEventListener('pointerup',endAppDrag);document.removeEventListener('pointercancel',endAppDrag);document.removeEventListener('click',suppressDragClick,true);window.removeEventListener('blur',cancelDrag); document.removeEventListener('pointerdown', dismissLauncher); document.removeEventListener('keydown', launcherKey); });
watch(() => router.currentRoute.value.path, path => {
  launcherOpen.value = path === '/apps/home';
}, { immediate: true });

const state = reactive({
  // isTesla: navigator.userAgent.toLowerCase().indexOf('tesla') >= 0,
  isTesla: true,
  menuItems: applications
})


function routeTo(name: string){
  launcherOpen.value = false;
  router.push(name);
}

</script>

<template>
  <template v-if="state.isTesla">
    <div class="app-shell">
      <div ref="sidebar" class="menu" :class="{ 'pin-drop-ready':dragging?.active, 'pin-drop-over':dragging?.over }">
        <div class="menu-top">
          <button type="button" class="menu-item" :class="{ 'menu-item-active': launcherOpen }" aria-label="应用列表" title="应用列表" ref="launcherTrigger" aria-controls="app-launcher-panel" :aria-expanded="launcherOpen" @click="launcherOpen = !launcherOpen">
            <el-icon><Grid /></el-icon>
          </button>
        </div>
        <div class="menu-bottom">
          <button type="button" class="menu-item" v-for="item of pinnedApps" :data-pin-route="item.route" @pointerdown="pressSidebar(item.route,$event)" @contextmenu.prevent :key="item.route" :class="{ 'pin-insert-before': dragging?.over && dragging.before === item.route, 'menu-item-active': item.route === router.currentRoute.value.path, 'menu-item-qqmusic': item.route === '/apps/qqmusic' }" :aria-label="item.label" :title="item.label" :aria-current="item.route === router.currentRoute.value.path ? 'page' : undefined" @click="routeTo(item.route)">
            <el-icon v-if="typeof(item.icon) === 'string'" :class="{ 'menu-icon-bilibili': item.route === '/apps/bilibili', 'menu-icon-qqmusic': item.route === '/apps/qqmusic', 'menu-icon-brand': ['/apps/amap', '/apps/gam4980', '/apps/tencent-video', '/apps/bilibili', '/apps/tesla'].includes(item.route) }">
              <img :src="item.icon" class="icon-svg" alt="" />
            </el-icon>
            <el-icon v-else>
              <component :is="item.icon"></component>
            </el-icon>
          </button>
        </div>
        <div v-if="dragging?.active" class="pin-drop-label">{{ dragging.over ? '松开固定' : '拖到这里' }}</div>
        <BackgroundAppDock />
      </div>
      <div class="main-view">
        <div v-if="router.currentRoute.value.path === '/apps/home'" class="launcher-idle"><img src="/tmc-mark.svg" alt="TMC" /><button @click="launcherOpen = true">打开应用列表</button></div>
        <RouterView v-slot="{ Component, route }"><KeepAlive include="QQMusicView,AmapAppView"><component :is="Component" :key="route.name ?? route.path" v-if="router.currentRoute.value.path !== '/apps/home'" /></KeepAlive></RouterView>
      </div>
      <BackgroundNavigation />
      <div v-if="dragging?.active && dragApp" class="app-drag-ghost" :style="{left:dragging.x+16+'px',top:dragging.y+12+'px'}"><img v-if="typeof dragApp.icon==='string'" :src="dragApp.icon" alt=""/><component v-else :is="dragApp.icon"/><span>{{ dragApp.label }}<small v-if="dragging.fromSidebar && !dragging.over" class="unpin-hint">松开移出侧栏</small></span></div>
      <span class="pin-announcement" role="status" aria-live="polite">{{ pinMessage }}</span>
      <Transition name="launcher-slide">
        <aside v-if="launcherOpen" id="app-launcher-panel" ref="launcherPanel" class="app-launcher-panel" aria-label="应用列表面板">
          <AppLauncher :pinned="pinnedRoutes" @toggle-pin="togglePin" @drag-app="startAppDrag" @selected="launcherOpen = false" />
        </aside>
      </Transition>
    </div>
  </template>
  <template v-else>
    <HomeViewPC />
  </template>
</template>

<style scoped>
.menu.pin-drop-ready{background:var(--color-accent-soft);outline:2px dashed var(--color-accent);outline-offset:-3px}
.menu.pin-drop-over{background:var(--color-accent-soft);box-shadow:inset 0 0 0 3px var(--color-accent)}
.menu-item.pin-insert-before{border-top:3px solid var(--color-accent)}
.pin-drop-label{font-size:11px;text-align:center;color:var(--color-accent);padding:8px 2px;pointer-events:none}
.app-drag-ghost{position:fixed;z-index:9999;display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:16px;background:var(--color-surface);color:var(--color-text);box-shadow:0 8px 30px #0003;pointer-events:none}.app-drag-ghost img,.app-drag-ghost svg{width:32px;height:32px;object-fit:contain}
.unpin-hint{display:block;font-size:12px;color:#c65b51;margin-top:4px}
.pin-announcement{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}

.app-shell {
  position: relative;
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

.icon-svg[src*="TENCENT_VIDEO_LOGO"] { border-radius: 25%; }

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
  overflow-x: hidden;
  overflow-y: hidden;
  scrollbar-width: none;
  border-right: 0;
  background: transparent;
  height: 100%;
}

.menu::-webkit-scrollbar {
  display: none;
}

.menu-bottom {
  margin-top: auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  flex: 0 1 auto;
  width: 100%;
}

.menu-top {
  flex-shrink: 0;
  width: 100%;
}

.menu-item {
  -webkit-touch-callout: none;
  user-select: none;
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

<style>
.app-launcher-panel{position:absolute;z-index:22;left:var(--menu-width);top:0;bottom:0;width:min(620px,calc(100% - var(--menu-width)));border-radius:0 24px 24px 0;border:1px solid var(--color-border);border-left:0;background:var(--color-surface);background:color-mix(in srgb,var(--color-surface) 88%,transparent);backdrop-filter:blur(28px) saturate(130%);-webkit-backdrop-filter:blur(28px) saturate(130%);box-shadow:18px 0 44px -20px rgba(0,0,0,.25);overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:var(--color-border-hover) transparent}
.app-launcher-panel .app-launcher{height:auto;min-height:100%;padding:24px;background:none;overflow:visible}
.app-launcher-panel .app-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.app-launcher-panel .app-card{padding:14px;box-shadow:none;background:var(--color-surface);border-radius:18px}
.app-launcher-panel .app-search{width:200px}
.launcher-slide-enter-active,.launcher-slide-leave-active{transition:transform .2s ease,opacity .2s ease}
.launcher-slide-enter-from,.launcher-slide-leave-to{transform:translateX(-18px);opacity:0}
.launcher-idle{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}
.launcher-idle img{width:72px;opacity:.45}
.launcher-idle button{padding:12px 20px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);color:var(--color-text);cursor:pointer}
@media(max-width:620px){.app-launcher-panel .app-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.app-launcher-panel .app-launcher{padding:20px 16px}.app-launcher-panel .launcher-header{margin-bottom:18px}.app-launcher-panel .app-search{width:100%}}
@media(prefers-reduced-motion:reduce){.launcher-slide-enter-active,.launcher-slide-leave-active{transition:none}}
</style>
