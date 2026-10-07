<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { backgroundNavigation as nav, navigationCommands } from '@/stores/backgroundNavigation';
import NavigationTurnIcon from './NavigationTurnIcon.vue';
const route = useRoute(), router = useRouter();
const card = ref<HTMLElement | null>(null), collapsed = ref(false), dragging = ref(false);
const position = ref<{ x: number; y: number } | null>(null);
const storageKey = 'tmc.navigation-float.v1';
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
  collapsed.value = saved?.collapsed === true;
  if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) position.value = { x: saved.x, y: saved.y };
} catch { /* Storage is optional on the car browser. */ }
const visible = computed(() => nav.active && route.path !== '/apps/amap');
const placement = computed(() => position.value ? { left: `${position.value.x}px`, top: `${position.value.y}px`, right: 'auto' } : {});
function save() {
  try { localStorage.setItem(storageKey, JSON.stringify({ ...position.value, collapsed: collapsed.value })); } catch { /* Optional persistence. */ }
}
function clamp(x: number, y: number) {
  const element = card.value, parent = element?.parentElement;
  if (!element || !parent || !parent.clientWidth || !parent.clientHeight) return { x, y };
  const menuWidth = parent.querySelector('.menu')?.getBoundingClientRect().width || 0;
  const minX = menuWidth + 8, maxX = Math.max(minX, parent.clientWidth - element.offsetWidth - 8);
  return { x: Math.min(maxX, Math.max(minX, x)), y: Math.min(Math.max(8, parent.clientHeight - element.offsetHeight - 8), Math.max(8, y)) };
}
function fit() {
  if (!position.value) return;
  const next = clamp(position.value.x, position.value.y);
  if (next.x !== position.value.x || next.y !== position.value.y) position.value = next;
}
async function toggleCollapsed() { collapsed.value = !collapsed.value; await nextTick(); fit(); save(); }
let press: { id: number; x: number; y: number; left: number; top: number } | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
let suppressClickUntil = 0;
function finish(event?: PointerEvent) {
  if (event && press && event.pointerId !== press.id) return;
  clearTimeout(timer);
  if (dragging.value) { save(); suppressClickUntil = Date.now() + 500; }
  if (press && card.value?.hasPointerCapture?.(press.id)) card.value.releasePointerCapture(press.id);
  press = null; dragging.value = false;
  window.removeEventListener('pointermove', move);
  window.removeEventListener('pointerup', finish);
  window.removeEventListener('pointercancel', finish);
  window.removeEventListener('blur', blur);
}
function blur() { finish(); }
function start(event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0 || (event.target as Element).closest('[data-no-drag]')) return;
  finish(); suppressClickUntil = 0;
  const element = card.value!, bounds = element.getBoundingClientRect(), parent = element.parentElement!.getBoundingClientRect();
  press = { id: event.pointerId, x: event.clientX, y: event.clientY, left: bounds.left - parent.left, top: bounds.top - parent.top };
  timer = setTimeout(() => {
    if (!press) return;
    dragging.value = true; position.value = clamp(press.left, press.top);
    element.setPointerCapture?.(press.id);
  }, 450);
  window.addEventListener('pointermove', move, { passive: false });
  window.addEventListener('pointerup', finish);
  window.addEventListener('pointercancel', finish);
  window.addEventListener('blur', blur);
}
function move(event: PointerEvent) {
  if (!press || event.pointerId !== press.id) return;
  const dx = event.clientX - press.x, dy = event.clientY - press.y;
  if (!dragging.value) {
    if (Math.hypot(dx, dy) > 10) { suppressClickUntil = Date.now() + 500; finish(); }
    return;
  }
  event.preventDefault();
  position.value = clamp(press.left + dx, press.top + dy);
}
function guardClick(event: MouseEvent) {
  if (Date.now() < suppressClickUntil) { event.preventDefault(); event.stopPropagation(); }
}
let observer: ResizeObserver | undefined;
watch(card, element => {
  observer?.disconnect(); finish();
  if (!element) return;
  fit();
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(fit); observer.observe(element); if (element.parentElement) observer.observe(element.parentElement);
  }
});
onBeforeUnmount(() => { finish(); observer?.disconnect(); });
</script>
<template>
  <aside v-if="visible" ref="card" class="navigation-float" :class="{ collapsed, dragging }" :style="placement" aria-label="后台导航"
    @pointerdown="start" @click.capture="guardClick" @contextmenu.prevent>
    <button class="collapse-toggle" data-no-drag :aria-label="collapsed ? '展开导航卡片' : '折叠导航卡片'" :aria-expanded="!collapsed" @click="toggleCollapsed">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path :d="collapsed ? 'M6 9l6 6 6-6' : 'M6 15l6-6 6 6'" /></svg>
    </button>
    <button class="guidance" aria-label="返回高德导航" title="点击返回导航，长按移动卡片" @click="router.push('/apps/amap')">
      <NavigationTurnIcon :arrow="nav.arrow" />
      <span><small v-if="!collapsed">{{ nav.simulated ? '模拟导航' : '正在导航' }} · 剩余 {{ nav.remaining }} · {{ nav.remainingDuration }}</small><strong>{{ nav.instruction }}</strong><span v-if="!collapsed">{{ nav.road }}</span></span>
    </button>
    <template v-if="!collapsed">
      <p v-if="nav.status">{{ nav.status }}</p>
      <div class="actions" data-no-drag><button @click="navigationCommands.toggleVoice?.()">{{ nav.muted ? '开启语音' : '静音' }}</button><button @click="navigationCommands.stop?.()">结束导航</button></div>
    </template>
  </aside>
</template>
<style scoped>
.navigation-float{position:absolute;right:16px;top:16px;z-index:21;width:min(340px,calc(100% - var(--menu-width) - 32px));box-sizing:border-box;padding:14px;border:1px solid #ffffff40;border-radius:20px;background:#123f38f2;color:white;box-shadow:0 8px 28px #0003;backdrop-filter:blur(16px);user-select:none;-webkit-user-select:none;touch-action:none}
.navigation-float.dragging{cursor:grabbing;box-shadow:0 12px 36px #0006;outline:2px solid #7ee8cc}
.guidance{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding-right:36px!important;box-sizing:border-box}.guidance svg{width:40px;height:48px;flex-shrink:0}.guidance>span{min-width:0;display:grid;gap:5px}.guidance strong{font-size:20px;overflow-wrap:anywhere}.guidance small{color:#a8e1d2}.guidance span span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.navigation-float button{border:0;color:inherit;background:transparent;cursor:pointer;padding:0;min-height:40px}.navigation-float p{font-size:12px;opacity:.75;margin:8px 0}.actions{display:flex;justify-content:flex-end;gap:10px}.actions button{padding:4px 12px;border-radius:10px;background:#ffffff18}
.collapse-toggle{position:absolute;z-index:2;right:7px;top:7px;width:40px;height:40px;display:grid;place-items:center;border-radius:12px}.collapse-toggle svg{width:22px;height:22px}.collapse-toggle:hover{background:#ffffff18}
.navigation-float.collapsed{width:min(250px,calc(100% - var(--menu-width) - 32px));padding:8px 12px;border-radius:16px}.collapsed .guidance{gap:8px;min-height:40px}.collapsed .guidance svg{width:28px;height:32px}.collapsed .guidance strong{font-size:16px}.collapsed .collapse-toggle{top:8px}
</style>
