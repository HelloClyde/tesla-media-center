<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import DouyinAccount from '@/components/DouyinAccount.vue';
import { useAudioChannel } from '@/functions/useAudioChannel';

interface Clip { vid: string; title: string; pageUrl: string; cover?: string }
interface Source extends Clip { url: string; urls: string[] }
const items = ref<Clip[]>([]), recent = ref<Clip[]>([]), recentQueue = ref<Clip[]>([]);
const query = ref(''), link = ref(''), mode = ref<'home' | 'search' | 'recent'>('home');
const catalogBusy = ref(false), catalogError = ref(''), busy = ref(false), error = ref('');
const current = ref<Source | null>(null), playing = ref(false), audioBlocked = ref(false);
const panel = ref<'comments' | 'queue'>('comments');
const comments = ref<{id:string; author:string; text:string; likes:number | null}[]>([]);
const commentsBusy = ref(false), commentsError = ref('');
let commentsController: AbortController | undefined;
let commentGeneration = 0, wheelAt = 0;
const canvas = ref<HTMLCanvasElement>(), loading = ref<HTMLElement>();
const track = ref<HTMLInputElement>(), label = ref<HTMLElement>();
const { channelAudio, startAudioChannel, restoreAudioChannel } = useAudioChannel();
const historyKey = 'tmc.douyin.recent.v1';
const autoNextKey = 'tmc.douyin.auto-next.v1';
const autoNext = ref(false);
try {
  autoNext.value = localStorage.getItem(autoNextKey) === 'true';
  const stored = JSON.parse(localStorage.getItem(historyKey) || '[]');
  if (Array.isArray(stored)) recent.value = stored.filter(v => /^\d{15,22}$/.test(v?.vid) && typeof v.title === 'string')
    .slice(0, 24).map(v => ({ vid: v.vid, title: v.title, pageUrl: `https://www.douyin.com/video/${v.vid}` }));
} catch { /* Storage is optional. */ }
watch(autoNext, value => { try { localStorage.setItem(autoNextKey, String(value)); } catch { /* Storage is optional. */ } });
const visible = computed(() => mode.value === 'recent' ? recentQueue.value : items.value);
const index = computed(() => visible.value.findIndex(v => v.vid === current.value?.vid));
let player: any = null, disposed = false, generation = 0, catalogGeneration = 0;
let sourceController: AbortController | undefined, catalogController: AbortController | undefined;
let watchdog: ReturnType<typeof setTimeout> | undefined;
let touchStartPoint: { x: number; y: number } | undefined;
let resizeObserver: ResizeObserver | undefined;

function stop() {
  ++generation; clearTimeout(watchdog); sourceController?.abort(); sourceController = undefined;
  resizeObserver?.disconnect(); resizeObserver = undefined;
  player?.destroy(); player = null; playing.value = false; audioBlocked.value = false; busy.value = false;
  channelAudio.value?.pause();
}
function close() { ++commentGeneration; commentsController?.abort(); commentsBusy.value = false; stop(); current.value = null; error.value = ''; }
async function loadCatalog(nextMode: 'home' | 'search' | 'recent' = mode.value) {
  if (nextMode === 'search' && !query.value.trim()) return;
  catalogController?.abort(); const ticket = ++catalogGeneration;
  catalogError.value = ''; catalogBusy.value = false;
  if (nextMode === 'recent') { mode.value = nextMode; recentQueue.value = [...recent.value]; panel.value = 'queue'; return; }
  if (nextMode === 'search') panel.value = 'queue';
  catalogBusy.value = true; catalogController = new AbortController();
  const controller = catalogController;
  const timer = setTimeout(() => controller.abort(), 100000);
  try {
    const response = await fetch(`/api/douyin/${nextMode}${nextMode === 'search' ? '?q=' + encodeURIComponent(query.value.trim()) : ''}`,
      { credentials: 'same-origin', signal: catalogController.signal });
    const result = await response.json();
    if (disposed || ticket !== catalogGeneration) return;
    if (!response.ok || result.status !== 'ok') throw new Error(result.status === 'need_login'
      ? '请先登录媒体中心' : result.message || '抖音列表加载失败');
    mode.value = nextMode; items.value = result.data.items;
    if (nextMode === 'home' && items.value.length) void open(items.value[0].pageUrl);
    if (nextMode === 'search') panel.value = 'queue';
  } catch (cause: any) {
    if (!disposed && ticket === catalogGeneration) catalogError.value = cause.name === 'AbortError'
      ? '抖音页面加载超时，请重试或通过分享链接打开视频' : cause.message || '网络请求失败';
  } finally { clearTimeout(timer); if (!disposed && ticket === catalogGeneration) catalogBusy.value = false; }
}
async function open(value = link.value) {
  if (disposed || !value.trim()) return;
  ++commentGeneration; commentsController?.abort(); commentsBusy.value = false;
  stop(); error.value = ''; busy.value = true; comments.value = []; commentsError.value = ''; link.value = value;
  const ticket = generation, active = () => !disposed && ticket === generation;
  sourceController = new AbortController(); const controller = sourceController;
  const timer = setTimeout(() => controller.abort(), 100000);
  startAudioChannel();
  try {
    const response = await fetch('/api/douyin/source', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: value }), signal: controller.signal });
    const result = await response.json();
    if (!active()) return;
    if (!response.ok || result.status !== 'ok') throw new Error(result.status === 'need_login'
      ? '请先登录媒体中心' : result.message || '获取视频失败');
    current.value = result.data; link.value = current.value!.pageUrl; void loadComments();
    await nextTick(); if (!active()) return;
    const resize = () => {
      if (!canvas.value?.parentElement) return;
      const box = canvas.value.parentElement.getBoundingClientRect();
      const width = Math.max(1, Math.round(box.width)), height = Math.max(1, Math.round(box.height));
      if (canvas.value.width !== width) canvas.value.width = width;
      if (canvas.value.height !== height) canvas.value.height = height;
    };
    resize();
    if (typeof ResizeObserver !== 'undefined' && canvas.value?.parentElement) {
      resizeObserver = new ResizeObserver(resize); resizeObserver.observe(canvas.value.parentElement);
    }
    player = new Player(); player.chunkSize = 1024 * 1024; player.maxAheadSeconds = 24;
    player.setLoadingDiv(loading.value); player.setTrack(track.value, label.value);
    player.setAudioBlockedCallback?.((blocked: boolean) => {
      if (active()) { audioBlocked.value = blocked; playing.value = !blocked; }
    });
    player.setFinishCallback(() => {
      if (!active()) return;
      playing.value = false; clearTimeout(watchdog);
      if (loading.value) loading.value.style.display = 'none';
      const next = visible.value[index.value + 1];
      if (autoNext.value && index.value >= 0 && next) {
        queueMicrotask(() => { if (active() && autoNext.value) void open(next.pageUrl); });
      }
    });
    player.setTimeCallback((time: number) => { if (active() && time > 0) clearTimeout(watchdog); });
    watchdog = setTimeout(() => { if (active()) { error.value = '视频加载超时，请重试'; stop(); } }, 70000);
    const state = player.play(current.value!.url, canvas.value, (event: any) => {
      if (!active() || !event.error || event.error === 1) return;
      error.value = event.message || '视频播放失败，请重试'; stop();
    }, 512 * 1024, false, undefined, [current.value!.url]);
    if (state?.e) throw new Error(state.m || '播放器启动失败');
    if (!active()) return;
    playing.value = true;
    const { vid, title, pageUrl } = current.value!;
    recent.value = [{ vid, title, pageUrl }, ...recent.value.filter(v => v.vid !== vid)].slice(0, 24);
    try { localStorage.setItem(historyKey, JSON.stringify(recent.value)); } catch { /* Best effort. */ }
  } catch (cause: any) {
    if (active()) { error.value = cause.name === 'AbortError' ? '视频页面加载超时，请重试' : cause.message || '获取视频失败'; stop(); }
  } finally { clearTimeout(timer); if (active()) busy.value = false; }
}
async function loadComments() {
  if (!current.value) return;
  commentsController?.abort(); const controller = new AbortController(); commentsController = controller;
  const ticket = ++commentGeneration; commentsBusy.value = true; commentsError.value = '';
  const timer = setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch(`/api/douyin/comments?vid=${current.value.vid}`, {signal:controller.signal, credentials:'same-origin'});
    const result = await response.json();
    if (disposed || ticket !== commentGeneration) return;
    if (!response.ok || result.status !== 'ok') throw new Error(result.message || '评论暂时无法加载');
    comments.value = result.data.items;
  } catch (cause:any) {
    if (!disposed && ticket === commentGeneration) commentsError.value = cause.name === 'AbortError' ? '评论加载超时，请重试' : cause.message;
  } finally { clearTimeout(timer); if (!disposed && ticket === commentGeneration) commentsBusy.value = false; }
}
function wheel(event: WheelEvent) {
  if (Math.abs(event.deltaY) < 25 || busy.value || Date.now() - wheelAt < 900) return;
  wheelAt = Date.now(); move(event.deltaY > 0 ? 1 : -1);
}
function toggle() {
  if (!player || busy.value) return;
  if (audioBlocked.value) {
    startAudioChannel();
    const currentPlayer = player;
    void currentPlayer.resumeBlockedAudio().then((resumed: boolean) => {
      if (player === currentPlayer && !resumed) error.value = '浏览器尚未允许播放声音，请再点一次播放';
    }).catch(() => { if (player === currentPlayer) error.value = '声音启动失败，请再次点击播放'; });
    return;
  }
  if (player.getState() === 1) { player.pause(); playing.value = false; channelAudio.value?.pause(); }
  else if (player.getState() === 2) { startAudioChannel(); player.resume(); playing.value = true; }
  else if (current.value) void open(current.value.pageUrl);
}
function move(delta: number) {
  const next = index.value + delta;
  if (!busy.value && index.value >= 0 && next >= 0 && next < visible.value.length) void open(visible.value[next].pageUrl);
}
function beginSwipe(event: TouchEvent) {
  if (event.touches.length !== 1) { touchStartPoint = undefined; return; }
  touchStartPoint = { x: event.touches[0].clientX, y: event.touches[0].clientY };
}
function swipe(event: TouchEvent) {
  if (touchStartPoint && event.changedTouches.length === 1) {
    const deltaY = touchStartPoint.y - event.changedTouches[0].clientY;
    const deltaX = touchStartPoint.x - event.changedTouches[0].clientX;
    if (Math.abs(deltaY) > 70 && Math.abs(deltaY) > Math.abs(deltaX) * 1.2) move(deltaY > 0 ? 1 : -1);
  }
  touchStartPoint = undefined;
}
onMounted(() => { void loadCatalog('home'); });
onBeforeUnmount(() => { disposed = true; ++catalogGeneration; catalogController?.abort(); commentsController?.abort(); ++commentGeneration; stop(); });
</script>

<template>
  <main class="douyin-app">
    <section class="stage" aria-label="抖音播放器" @wheel.prevent="wheel">
      <div class="screen" @touchstart="beginSwipe" @touchend="swipe" @touchcancel="touchStartPoint = undefined">
        <canvas ref="canvas" width="576" height="1024" aria-label="抖音播放画面"/>
        <div ref="loading" class="buffering" style="display:none">正在缓冲…</div>
        <div v-if="busy || catalogBusy && !current" class="stage-message" role="status">正在加载视频…</div>
        <div v-else-if="audioBlocked" class="stage-message" role="status">浏览器需要点击后才能播放声音<button @click="toggle">点击播放</button></div>
        <div v-else-if="!current" class="stage-message">{{ catalogError || '暂时没有可播放的视频' }}<button @click="loadCatalog('home')">重新加载</button></div>
      </div>
    </section>
    <aside class="side">
      <header><div class="brand"><img src="/icon/DOUYIN_LOGO.svg" alt=""/><h1>抖音</h1></div><DouyinAccount @changed="close(); loadCatalog('home')"/></header>
      <form class="search" @submit.prevent="loadCatalog('search')"><input v-model="query" aria-label="搜索抖音视频" maxlength="80" placeholder="搜索视频" type="search"/><button :disabled="!query.trim()">搜索</button></form>
      <p v-if="catalogError" class="notice catalog-error" role="alert">{{ catalogError }}</p>
      <div class="details">
        <span class="eyebrow">{{ index >= 0 ? `${index + 1} / ${visible.length}` : '正在观看' }}</span>
        <h2>{{ current?.title || '抖音短视频' }}</h2>
        <p class="hint">在左侧上下滑动或滚动，切换视频</p>
        <div v-if="error" class="notice" role="alert">{{ error }}<button @click="open()">重试</button></div>
        <div class="transport"><button :disabled="busy || index <= 0" @click="move(-1)">上一条</button><button class="primary" :disabled="busy || !current || !!error" @click="toggle">{{ audioBlocked ? '点击播放' : playing ? '暂停' : '播放' }}</button><button :disabled="busy || index < 0 || index >= visible.length - 1" @click="move(1)">下一条</button></div>
        <div class="timeline"><input ref="track" type="range" min="0" max="100" value="0" aria-label="播放进度"/><span ref="label">00:00:00/00:00:00</span></div>
        <label class="auto-next"><input v-model="autoNext" type="checkbox"/><span class="auto-next-track" aria-hidden="true"></span><span>播完自动播放下一条</span></label>
        <div class="actions"><button @click="restoreAudioChannel">开启 / 恢复声音</button><a v-if="current" :href="current.pageUrl" target="_blank" rel="noopener noreferrer">在抖音打开</a></div>
      </div>
      <nav aria-label="视频信息"><button :class="{active:panel==='comments'}" @click="panel='comments'">评论</button><button :class="{active:panel==='queue'}" @click="panel='queue'">视频列表</button></nav>
      <section v-if="panel==='comments'" class="comments" aria-label="评论区">
        <p v-if="commentsBusy" role="status">正在加载评论…</p>
        <div v-else-if="commentsError" class="notice" role="alert">{{ commentsError }}<button @click="loadComments">重试</button></div>
        <p v-else-if="!comments.length" class="hint">{{ current ? '暂未显示评论' : '视频加载后显示评论' }}</p>
        <article v-for="comment in comments" :key="comment.id"><strong>{{ comment.author }}</strong><p>{{ comment.text }}</p><small v-if="comment.likes !== null">{{ comment.likes }} 赞</small></article>
        <p class="hint">评论互动可在抖音官方页面完成。</p>
      </section>
      <section v-else class="catalog" aria-label="抖音视频列表">
        <div class="actions"><button @click="loadCatalog('home')">换一批</button><button @click="loadCatalog('recent')">最近观看</button></div>
        <p v-if="catalogBusy" role="status">正在加载视频…</p>
        <button v-for="clip in visible" :key="clip.vid" class="card" :class="{selected:clip.vid===current?.vid}" @click="open(clip.pageUrl)"><img v-if="clip.cover" :src="clip.cover" alt="" loading="lazy" referrerpolicy="no-referrer"/><span>{{ clip.title }}</span></button>
      </section>
      <details class="share"><summary>打开分享链接</summary><form @submit.prevent="open()"><input v-model="link" aria-label="抖音分享链接" placeholder="粘贴分享链接" maxlength="4096"/><button :disabled="!link.trim() || busy">播放</button></form></details>
    </aside>
    <audio ref="channelAudio" hidden aria-hidden="true"/>
  </main>
</template>
<style scoped>
.douyin-app{height:100%;min-height:0;box-sizing:border-box;overflow:hidden;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,1fr);gap:24px;padding:20px;background:#111116;color:#f3f3f5;border-radius:16px;font-size:14px}.stage{min-height:0;min-width:0;display:flex;align-items:center;justify-content:center;overflow:hidden;background:#08080b;border-radius:16px}.screen{position:relative;height:100%;max-width:100%;aspect-ratio:9/16;background:#000;overflow:hidden;touch-action:none}canvas{position:absolute;inset:0;width:100%;height:100%;display:block}.stage-message{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;padding:24px;text-align:center;background:#09090de6}.buffering{position:absolute;bottom:24px;left:50%;transform:translateX(-50%);white-space:nowrap;background:#000a;padding:12px;border-radius:10px}.side{min-height:0;min-width:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;padding-right:8px}header,.brand,.actions,nav{display:flex;align-items:center;gap:12px}header{justify-content:space-between;margin-bottom:18px}.brand img{width:38px;height:38px}.brand h1{font-size:22px;margin:0}button,input,a{font:inherit}button,a{box-sizing:border-box;min-height:44px;padding:10px 14px;border:1px solid #ffffff18;border-radius:10px;background:#25252d;color:inherit;text-decoration:none;cursor:pointer}button:disabled{opacity:.4;cursor:default}button:focus-visible,input:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #25f4ee;outline-offset:2px}form{display:flex;gap:8px}input{box-sizing:border-box;min-width:0;background:#1e1e26;border:1px solid #ffffff18;border-radius:10px;padding:12px;color:inherit}form input{flex:1}.search{margin-bottom:24px}.primary,.search button{background:#fe2c55}.eyebrow{color:#25f4ee;font-size:12px}h2{font-size:18px;line-height:1.6;overflow-wrap:anywhere;margin:10px 0}.hint{font-size:12px;color:#9999a8;line-height:1.7}.transport{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:18px}.timeline{display:flex;flex-direction:column;gap:8px;margin:18px 0}.timeline input{width:100%;padding:0;accent-color:#fe2c55}.timeline span{font-size:12px;color:#aaa}.auto-next{display:flex;align-items:center;gap:10px;min-height:44px;width:fit-content;cursor:pointer}.auto-next input{width:20px;height:20px;min-width:20px;padding:0;accent-color:#fe2c55;cursor:pointer}.actions{flex-wrap:wrap}.actions button,.actions a{font-size:12px;background:none}nav{position:sticky;top:0;background:#111116;border-bottom:1px solid #ffffff18;padding:14px 0 8px;margin-top:16px;z-index:1}nav button{border:0;background:none;color:#999}nav button.active{color:#fff;box-shadow:inset 0 -2px #fe2c55;border-radius:0}.comments{min-height:180px}.comments article{padding:18px 0;border-bottom:1px solid #ffffff10}.comments strong{font-size:13px;color:#b9b9c6}.comments article p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;margin:6px 0}.comments small{color:#888}.notice{color:#ff9cb0;line-height:1.7;padding:12px 0}.notice button{margin:8px 8px 0 0}.catalog{padding:16px 0}.card{width:100%;display:flex;gap:12px;align-items:center;text-align:left;background:none;margin:8px 0}.card img{width:45px;height:60px;object-fit:cover;border-radius:6px}.card span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;line-height:1.6}.card.selected{border-color:#fe2c55}.share{padding:20px 0;color:#999;border-top:1px solid #ffffff18}.share summary{cursor:pointer}.share form{margin-top:14px}@media(max-width:700px){.douyin-app{grid-template-columns:minmax(0,1fr) minmax(0,1fr);padding:10px;gap:12px}.side{padding-right:4px}header{flex-wrap:wrap}.brand h1{font-size:18px}h2{font-size:15px}.transport{gap:4px}.transport button{padding:8px 4px;font-size:12px}.search button{padding:8px}.actions{gap:6px}}
.auto-next{position:relative;gap:12px;min-height:48px;user-select:none}
.auto-next input{position:absolute;opacity:0;width:1px;height:1px;min-width:0;padding:0;margin:0}
.auto-next-track{position:relative;display:inline-block;flex:none;width:46px;height:26px;border-radius:999px;background:#43434e;box-shadow:inset 0 0 0 1px #ffffff26;transition:background .18s ease}
.auto-next-track::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 4px #0005;transition:transform .18s ease}
.auto-next input:checked + .auto-next-track{background:#fe2c55}
.auto-next input:checked + .auto-next-track::after{transform:translateX(20px)}
.auto-next input:focus-visible + .auto-next-track{outline:2px solid #25f4ee;outline-offset:3px}
@media(prefers-reduced-motion:reduce){.auto-next-track,.auto-next-track::after{transition:none}}
</style>
