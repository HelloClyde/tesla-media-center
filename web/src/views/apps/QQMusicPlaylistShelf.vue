<script lang="ts">
interface ShelfItem { id: string; title: string; cover: string; kind: string }
const shelfCache = new Map<string, { items: ShelfItem[]; page: number; more: boolean }>();
// Serialize shelf requests so scrolling into multiple sections does not burst the upstream API.
let pending: Promise<unknown> = Promise.resolve();
</script>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue';
const props = defineProps<{ theme: string; api: (path: string) => Promise<any> }>();
const emit = defineEmits<{ open: [item: ShelfItem] }>();
const section = ref<HTMLElement>(), track = ref<HTMLElement>();
const cached = shelfCache.get(props.theme);
const items = ref<ShelfItem[]>(cached?.items || []);
const page = ref(cached?.page || 0), more = ref(cached?.more ?? true);
const busy = ref(false), error = ref('');
let disposed = false;
let observer: IntersectionObserver | undefined;
async function load() {
  if (busy.value || !more.value || disposed) return;
  busy.value = true; error.value = '';
  const task = pending.catch(() => {}).then(async () => {
    if (disposed) return;
    try {
      const result = await props.api(`browse?kind=playlist-search&q=${encodeURIComponent(props.theme)}&page=${page.value + 1}`);
      if (disposed) return;
      items.value = [...new Map([...items.value, ...result.items].map(item => [item.id, item])).values()];
      ++page.value; more.value = result.more;
      shelfCache.set(props.theme, { items: items.value, page: page.value, more: more.value });
    } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : '歌单加载失败'; }
    finally { if (!disposed) busy.value = false; }
  });
  pending = task;
  await task;
}
function slide(direction: number) {
  const el = track.value;
  if (el) el.scrollBy({ left: direction * el.clientWidth * .8, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}
onMounted(() => {
  if (items.value.length) return;
  if (!('IntersectionObserver' in window)) { void load(); return; }
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); void load(); }
  }, { root: section.value?.closest('.results'), rootMargin: '80px' });
  if (section.value) observer.observe(section.value);
});
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); });
</script>
<template>
  <section ref="section" class="playlist-shelf" :aria-label="theme + '歌单'">
    <header><h3>{{ theme }}</h3><span>精选歌单</span><div class="shelf-arrows"><el-button circle :icon="ArrowLeft" :aria-label="theme + '歌单向左滑动'" @click="slide(-1)" /><el-button circle :icon="ArrowRight" :aria-label="theme + '歌单向右滑动'" @click="slide(1)" /></div></header>
    <div ref="track" class="shelf-track" tabindex="0" :aria-label="theme + '歌单，左右滑动浏览'" @keydown.left.prevent="slide(-1)" @keydown.right.prevent="slide(1)">
      <button v-for="item in items" :key="item.id" class="playlist-tile" @click="emit('open', item)"><img :src="item.cover" alt="" loading="lazy" /><strong>{{ item.title }}</strong></button>
      <div v-if="busy && !items.length" v-for="n in 4" :key="'placeholder-' + n" class="shelf-placeholder" aria-hidden="true"></div>
      <div v-if="error" class="shelf-message" role="status"><p>{{ error }}</p><el-button @click="load">重试</el-button></div>
      <button v-else-if="items.length && more" class="shelf-more" :disabled="busy" @click="load">{{ busy ? '加载中…' : '更多歌单 →' }}</button>
      <p v-else-if="!busy && !items.length && page" class="shelf-message">暂无歌单</p>
    </div>
    <span v-if="busy" class="sr-only" role="status">正在加载{{ theme }}歌单</span>
  </section>
</template>
<style scoped>
.playlist-shelf{margin-top:24px;min-width:0}header{display:flex;align-items:center;gap:10px;margin-bottom:12px}h3{font-size:20px;margin:0}header>span{font-size:12px;color:var(--color-text-soft)}.shelf-arrows{display:flex;gap:6px;margin-left:auto}.shelf-arrows .el-button{margin:0;width:32px;height:32px}.shelf-track{display:flex;gap:14px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;scrollbar-width:thin;padding:2px 2px 12px;min-height:150px}.playlist-tile{flex:0 0 clamp(125px,19vw,175px);min-width:0;border:0;background:transparent;color:inherit;text-align:left;padding:0;cursor:pointer;scroll-snap-align:start}.playlist-tile img{display:block;width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px;background:var(--color-border)}.playlist-tile strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;line-height:1.6;font-weight:500;margin-top:9px;height:42px}.playlist-tile:focus-visible,.shelf-track:focus-visible{outline:2px solid #19b978;outline-offset:1px;border-radius:12px}.shelf-more{flex:0 0 110px;align-self:center;border:1px solid var(--color-border);border-radius:14px;padding:16px 8px;cursor:pointer;background:var(--color-surface);color:var(--color-text-soft)}.shelf-placeholder{flex:0 0 clamp(125px,19vw,175px);height:160px;border-radius:14px;background:var(--color-border);opacity:.4}.shelf-message{font-size:13px;color:var(--color-text-soft);max-width:340px;flex-shrink:0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
</style>
