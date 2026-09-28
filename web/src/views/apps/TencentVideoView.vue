<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useAudioChannel } from '@/functions/useAudioChannel';
import TencentAccount from '@/components/TencentAccount.vue';

interface Video { vid: string; title: string; duration: number; pageUrl: string; url: string; urls?: string[] }
interface Recent { vid: string; title: string; pageUrl: string }
interface CatalogItem { id: string; vid: string; title: string; cover: string; subtitle: string; kind: string; episodes: CatalogItem[] }
const query = ref(''), activeQuery = ref('');
const catalogMode = ref<'home' | 'search'>('home');
const items = ref<CatalogItem[]>([]), selectedSeries = ref<CatalogItem | null>(null);
const featured = computed(() => catalogMode.value === 'home' && items.value.length >= 3 ? items.value.slice(0, 3) : []);
const gridItems = computed(() => featured.value.length ? items.value.slice(3) : items.value);
const catalogBusy = ref(false), catalogError = ref('');
const nextCursor = ref<string | null>(null), nextPage = ref<number | null>(null);
let catalogController: AbortController | null = null;
let catalogGeneration = 0;
let failedAppend = false;
const input = ref('');
const busy = ref(false), error = ref(''), playing = ref(false);
const current = ref<Video | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const loading = ref<HTMLElement | null>(null);
const track = ref<HTMLInputElement | null>(null);
const label = ref<HTMLElement | null>(null);
const { channelAudio, startAudioChannel, restoreAudioChannel } = useAudioChannel();
const historyKey = 'tmc.tencent-video.recent.v1';
const recent = ref<Recent[]>([]);
try {
  const saved = JSON.parse(localStorage.getItem(historyKey) || '[]');
  if (Array.isArray(saved)) recent.value = saved.filter(v => /^[a-zA-Z0-9]{11}$/.test(v?.vid)
    && typeof v.title === 'string').slice(0, 12).map(v => ({ vid: v.vid, title: v.title,
      pageUrl: `https://v.qq.com/x/page/${v.vid}.html` }));
} catch { /* Unavailable storage should not block playback. */ }
let player: any = null;
let controller: AbortController | null = null;
let generation = 0, disposed = false;
let watchdog: ReturnType<typeof setTimeout> | undefined;

function stop() {
  ++generation;
  clearTimeout(watchdog);
  controller?.abort(); controller = null;
  player?.destroy(); player = null;
  playing.value = false; busy.value = false;
  channelAudio.value?.pause();
}
function close() { stop(); current.value = null; error.value = ''; }

async function loadCatalog(append = false) {
  catalogController?.abort();
  const ticket = ++catalogGeneration;
  catalogController = new AbortController();
  catalogBusy.value = true; catalogError.value = ''; failedAppend = append;
  if (!append) { items.value = []; nextCursor.value = null; nextPage.value = null; selectedSeries.value = null; }
  const params = new URLSearchParams();
  if (catalogMode.value === 'search') {
    params.set('q', activeQuery.value); params.set('page', String(append ? nextPage.value ?? 0 : 0));
  } else if (append && nextCursor.value) params.set('cursor', nextCursor.value);
  try {
    const response = await fetch(`/api/tencent-video/${catalogMode.value}?${params}`, {
      credentials: 'same-origin', signal: catalogController.signal,
    });
    const result = await response.json();
    if (disposed || ticket !== catalogGeneration) return;
    if (!response.ok || result.status !== 'ok') throw new Error(result.status === 'need_login'
      ? '登录已过期，请重新登录媒体中心' : result.message || '视频列表加载失败');
    const merged = append ? [...items.value, ...result.data.items] : result.data.items;
    items.value = [...new Map<string, CatalogItem>(merged.map((item: CatalogItem) => [item.id, item])).values()];
    nextCursor.value = result.data.nextCursor ?? null;
    nextPage.value = result.data.nextPage ?? null;
  } catch (cause: any) {
    if (!disposed && ticket === catalogGeneration) catalogError.value = cause.message || '视频列表加载失败';
  } finally {
    if (!disposed && ticket === catalogGeneration) catalogBusy.value = false;
  }
}
function search() {
  if (!query.value.trim()) return;
  catalogMode.value = 'search'; activeQuery.value = query.value.trim(); void loadCatalog();
}
function home() { catalogMode.value = 'home'; activeQuery.value = ''; void loadCatalog(); }
function choose(item: CatalogItem) {
  if (item.episodes.length) { selectedSeries.value = item; return; }
  if (item.vid) { void open(item.vid); }
}

async function open(value = input.value, relayOnly = false) {
  if (disposed || !value.trim()) return;
  stop(); error.value = ''; busy.value = true;
  const request = generation;
  const active = () => !disposed && request === generation;
  controller = new AbortController();
  // Start the car audio channel while still inside the user's click gesture.
  startAudioChannel();
  try {
    const response = await fetch('/api/tencent-video/source', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin', body: JSON.stringify({ url: value }), signal: controller.signal,
    });
    const result = await response.json();
    if (!active()) return;
    if (!response.ok || result.status !== 'ok') throw new Error(result.status === 'need_login'
      ? '登录已过期，请重新登录媒体中心' : result.message || '获取视频失败');
    current.value = result.data;
    input.value = current.value!.pageUrl;
    await nextTick();
    if (!active()) return;
    canvas.value?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
    player = new Player();
    player.setLoadingDiv(loading.value);
    player.setTrack(track.value, label.value);
    player.setFinishCallback(() => { if (active()) playing.value = false; });
    player.setTimeCallback((time: number) => { if (time > 0) clearTimeout(watchdog); });
    watchdog = setTimeout(() => {
      if (active()) { error.value = '视频加载超时，请重试或换一个公开视频'; stop(); }
    }, Math.max(60000, (current.value!.urls?.length || 0) * 8000 + 45000));
    const status = player.play(current.value!.url, canvas.value, (event: any) => {
      if (!active() || !event.error || event.error === 1) return;
      error.value = `${event.message || `播放失败（错误码 ${event.error}，HTTP ${event.status || 0}）`} · VID: ${current.value!.vid}`;
      stop();
    }, 512 * 1024, false, undefined, [...(relayOnly ? [] : current.value!.urls || []), current.value!.url]);
    if (status?.e) throw new Error(status.m || '播放器启动失败');
    playing.value = true;
    const { vid, title, pageUrl } = current.value!;
    recent.value = [{ vid, title, pageUrl }, ...recent.value.filter(v => v.vid !== vid)].slice(0, 12);
    try { localStorage.setItem(historyKey, JSON.stringify(recent.value)); } catch { /* Best effort. */ }
  } catch (cause: any) {
    if (active()) { error.value = cause.message || '获取视频失败'; stop(); }
  } finally { if (active()) busy.value = false; }
}
function toggle() {
  if (!player) return;
  if (player.getState() === 1) { player.pause(); playing.value = false; }
  else if (player.getState() === 2) { player.resume(); playing.value = true; }
  else if (current.value) { void open(current.value.pageUrl); }
}
onMounted(() => { void loadCatalog(); });
onBeforeUnmount(() => { disposed = true; ++catalogGeneration; catalogController?.abort(); stop(); });
</script>

<template>
  <main class="tencent-view">
    <header class="topbar">
      <div class="brand"><img class="brand-icon" src="/icon/TENCENT_VIDEO_LOGO.png" alt=""/><div><h1>腾讯视频</h1><p>好内容，随心看</p></div></div>
      <form class="search-form" @submit.prevent="search">
        <label for="tencent-search" class="sr-only">搜索腾讯视频</label>
        <div class="link-row"><input id="tencent-search" v-model="query" maxlength="100" placeholder="搜索视频、节目或创作者" type="search"/><button :disabled="!query.trim()" type="submit">搜索</button></div>
      </form>
      <TencentAccount />
    </header>
    <details class="link-entry"><summary>通过链接或 VID 打开</summary><form class="link-form" @submit.prevent="open()">
      <label for="tencent-link">视频链接或 VID</label>
      <div class="link-row"><input id="tencent-link" v-model="input" placeholder="https://v.qq.com/x/page/…" autocomplete="off" /><button :disabled="busy || !input.trim()" type="submit">{{ busy ? '正在打开…' : '打开视频' }}</button></div>
    </form></details>
    <div v-if="busy" class="source-progress" role="status">正在打开视频…<button @click="stop">取消</button></div>
    <div v-if="error" class="play-error" role="alert"><span>{{ error }}</span><div v-if="current" class="retry-actions"><button @click="open(current.pageUrl)">重试</button><button @click="open(current.pageUrl, true)">仅用转接重试</button></div></div>
    <section v-if="current" class="video-panel">
      <div class="video-heading"><h2>{{ current.title }}</h2><button @click="close">关闭播放器</button></div>
      <div class="picture"><canvas ref="canvas" aria-label="腾讯视频播放画面" width="1100" height="623"></canvas><div ref="loading" class="loading" style="display: none">正在缓冲…</div></div>
      <div class="controls"><button @click="toggle" :disabled="!player">{{ playing ? '暂停' : '播放' }}</button><input ref="track" type="range" min="0" value="0" aria-label="播放进度"/><span ref="label">00:00:00/00:00:00</span><button @click="restoreAudioChannel">恢复声音</button><button @click="player?.fullscreen()">全屏</button></div>
    </section>
    <nav class="catalog-tabs" aria-label="视频浏览"><button :aria-pressed="catalogMode === 'home'" @click="home">首页推荐</button><span v-if="catalogMode === 'search'">“{{ activeQuery }}”的搜索结果</span><span v-else class="catalog-caption">发现值得一看的故事</span><button v-if="catalogMode === 'home'" class="refresh" :disabled="catalogBusy" @click="home">刷新推荐</button></nav>
    <section v-if="selectedSeries" class="episode-panel">
      <div class="video-heading"><h2>{{ selectedSeries.title }} · 选集</h2><button @click="selectedSeries = null">收起选集</button></div>
      <div class="episode-list"><button v-for="episode in selectedSeries.episodes" :key="episode.id" @click="choose(episode)">{{ episode.title }}<small v-if="episode.subtitle">{{ episode.subtitle }}</small></button></div>
    </section>
    <div v-if="catalogError" class="play-error" role="alert"><span>{{ catalogError }}</span><button @click="loadCatalog(failedAppend)">重试加载</button></div>
    <div v-if="catalogBusy && !items.length" class="catalog-loading" role="status">正在加载视频…</div>
    <section v-if="featured.length" class="featured-grid" aria-label="焦点推荐">
      <button v-for="(item, index) in featured" :key="item.id" class="catalog-card feature-card" @click="choose(item)">
        <img v-if="item.cover" :src="item.cover" alt="" :loading="index === 0 ? 'eager' : 'lazy'" referrerpolicy="no-referrer"/>
        <span class="feature-shade"></span><span class="feature-kind">{{ item.kind }}</span>
        <span class="feature-copy"><span v-if="index === 0" class="feature-eyebrow">首页精选</span><strong>{{ item.title }}</strong><small v-if="item.subtitle">{{ item.subtitle }}</small><span v-if="index === 0" class="feature-action">{{ item.episodes.length ? '查看选集' : '▶ 点击观看' }}</span></span>
      </button>
    </section>
    <h2 v-if="featured.length && gridItems.length" class="section-title">更多推荐<span>总有新的精彩</span></h2>
    <section class="catalog-grid" :aria-label="catalogMode === 'home' ? '首页推荐视频' : '搜索结果'" :aria-busy="catalogBusy">
      <button v-for="item in gridItems" :key="item.id" class="catalog-card" @click="choose(item)">
        <div class="cover"><img v-if="item.cover" :src="item.cover" alt="" loading="lazy" referrerpolicy="no-referrer"/><span v-else class="cover-placeholder">▶</span><span class="card-kind">{{ item.kind }}</span></div>
        <strong>{{ item.title }}</strong><small v-if="item.subtitle">{{ item.subtitle }}</small>
      </button>
    </section>
    <p v-if="!catalogBusy && !catalogError && !items.length" class="empty">{{ catalogMode === 'search' ? '没有找到可展示的视频，试试其他关键词。' : '暂时没有推荐内容，请刷新重试。' }}</p>
    <div v-if="nextCursor !== null || nextPage !== null" class="load-more"><button :disabled="catalogBusy" @click="loadCatalog(true)">{{ catalogBusy ? '正在加载…' : '加载更多' }}</button></div>
    <section v-if="recent.length" class="recent"><h2>最近打开</h2><div class="recent-grid"><button v-for="item in recent" :key="item.vid" @click="input = item.pageUrl; open(item.pageUrl)"><span class="recent-play" aria-hidden="true">▶</span><span>{{ item.title }}</span></button></div></section>
    <p class="support-note">推荐和搜索来自腾讯视频。播放支持公开、未加密的 MP4 源；会员或加密内容可能无法播放。</p>
    <audio ref="channelAudio" hidden></audio>
  </main>
</template>

<style scoped>
.link-entry{margin:-6px 0 20px;color:var(--color-text-secondary,#85919e)}.link-entry summary{cursor:pointer;padding:10px 0}.link-entry .link-form{margin-top:8px}.catalog-tabs{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:24px 0 16px}.catalog-tabs button[aria-pressed=true]{color:#168bc4;background:#168bc414;border-color:#168bc455}.catalog-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:20px;margin-bottom:24px}.catalog-card{padding:0!important;overflow:hidden;text-align:left;align-self:start;border:0!important;background:transparent!important}.cover{aspect-ratio:16/9;background:var(--color-border);position:relative;border-radius:12px;overflow:hidden}.cover img{width:100%;height:100%;object-fit:cover}.cover-placeholder{display:grid;height:100%;place-items:center;color:#169dd5;font-size:28px}.card-kind{position:absolute;bottom:8px;right:8px;color:#fff;background:#000a;border-radius:5px;padding:3px 7px;font-size:12px}.catalog-card strong{font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:15px;line-height:1.5;margin-top:10px}.catalog-card small{display:block;color:var(--color-text-secondary,#85919e);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:5px}.catalog-loading,.load-more{text-align:center;padding:24px}.episode-panel{border:1px solid var(--color-border);background:var(--color-surface);padding:20px;border-radius:18px;margin-bottom:20px}.episode-list{display:flex;flex-wrap:wrap;gap:10px;max-height:280px;overflow:auto}.episode-list small{display:block}.source-progress{display:flex;align-items:center;gap:16px;margin:16px 0}@media(max-width:650px){.catalog-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.catalog-card strong{font-size:14px}}
.tencent-view{max-width:1200px;margin:auto;padding:28px;color:var(--color-text)}
header{display:flex;align-items:center;gap:16px;margin-bottom:28px}.app-emblem{display:grid;place-items:center;width:58px;height:58px;border-radius:18px;background:linear-gradient(135deg,#2cbfac,#3da9e8 55%,#f5b13e);color:white;font-size:28px}
h1{font-size:26px;margin:0 0 6px}header p,.support-note,.empty p{color:var(--color-text-secondary,#85919e);margin:0;line-height:1.6}
.link-form,.video-panel,.recent,.empty{background:var(--color-surface);border:1px solid var(--color-border);border-radius:18px;padding:20px;margin-bottom:20px}.link-form label{display:block;margin-bottom:10px;font-size:14px}.link-row{display:flex;gap:12px}.link-row input{flex:1;min-width:0;border:1px solid var(--color-border);border-radius:10px;padding:14px;background:var(--color-bg);color:inherit;font:inherit}
button{border:1px solid var(--color-border);border-radius:10px;background:var(--color-surface);color:inherit;padding:12px 18px;font:inherit;cursor:pointer;min-height:44px}button:disabled{opacity:.45;cursor:default}.link-row button{background:#167cb4;color:white;border:0}button:focus-visible,input:focus-visible{outline:2px solid #169dd5;outline-offset:2px}.video-heading{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px}h2{font-size:18px;margin:0 0 14px}.video-heading h2{margin:0}.picture{position:relative;background:#000;aspect-ratio:1100/623;overflow:hidden;border-radius:10px}canvas{width:100%;height:100%;display:block}.loading{position:absolute;inset:0;align-content:center;text-align:center;color:white;background:#0005;pointer-events:none}.controls{display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap}.controls input{flex:1;min-width:100px}.controls span{font-size:13px;font-variant-numeric:tabular-nums}.play-error{background:#b52c2510;border:1px solid #b52c2540;color:#ba3d35;padding:16px;border-radius:12px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;gap:12px}.recent-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.recent-grid button{display:flex;text-align:left;align-items:center;gap:14px;line-height:1.5}.recent-play{color:#169dd5}.empty{text-align:center;padding:48px 24px}.empty>span{font-size:54px;color:#169dd5}.empty h2{margin:16px 0 8px}.support-note{font-size:13px}@media(max-width:650px){.tencent-view{padding:16px}.link-row{flex-direction:column}.controls{gap:8px}.controls button{padding:10px}.video-heading{align-items:flex-start}.video-heading button{white-space:nowrap}}
</style>

<style scoped>
.tencent-view{padding:22px 28px 32px}
.retry-actions{display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0}.play-error{flex-wrap:wrap}.play-error>span{overflow-wrap:anywhere;flex:1;min-width:180px}
.topbar{justify-content:space-between;gap:32px;margin-bottom:8px}
.brand{display:flex;align-items:center;gap:12px;flex-shrink:0}.brand-icon{width:48px;height:48px;border-radius:12px}.brand h1{font-size:23px;letter-spacing:.5px;margin-bottom:3px}.brand p{font-size:12px}
.search-form{width:min(560px,56%)}.search-form .link-row{gap:6px;padding:5px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:30px}.search-form input{border:0;background:transparent;padding:8px 14px;min-height:44px}.search-form button{border-radius:24px;padding:10px 24px;background:#087d51;min-width:84px}.search-form button:disabled{opacity:.65}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.link-entry{margin:0;color:var(--color-text-secondary,#85919e);font-size:12px}.link-entry summary{width:fit-content;min-height:44px;box-sizing:border-box;padding:13px 0}.link-entry .link-form{font-size:14px}
.catalog-tabs{margin:6px 0 14px;gap:18px}.catalog-tabs button[aria-pressed=true]{background:transparent;border-color:transparent;border-radius:0;border-bottom:3px solid #0ca968;color:var(--color-text);font-size:19px;font-weight:650;padding:8px 0}.catalog-caption{font-size:13px;color:var(--color-text-secondary,#85919e)}.catalog-tabs .refresh{margin-left:auto;background:transparent;border-color:transparent;padding:8px 12px;font-size:13px}
.featured-grid{display:grid;grid-template-columns:1.55fr 1fr;grid-template-rows:148px 148px;gap:14px;margin-bottom:26px}
.feature-card{position:relative;height:100%;border-radius:16px;background:#163f40!important;color:#fff;isolation:isolate}.feature-card:first-child{grid-row:span 2}.feature-card>img{width:100%;height:100%;object-fit:cover;display:block}.feature-shade{position:absolute;inset:0;background:linear-gradient(180deg,#0000 15%,#061b26b3 75%,#061b26ed)}.feature-kind{position:absolute;top:12px;right:12px;padding:4px 8px;border-radius:6px;background:#0009;font-size:12px}.feature-copy{position:absolute;bottom:18px;left:22px;right:22px}.feature-copy strong{font-size:20px;line-height:1.3;margin:5px 0;color:#fff}.feature-card:first-child strong{font-size:30px}.feature-copy small{color:#ffffffe0;margin-top:6px}.feature-eyebrow{font-size:11px;letter-spacing:3px;color:#b4f8d0}.feature-action{display:inline-flex;align-items:center;margin-top:14px;background:#fff;color:#154333;padding:11px 18px;border-radius:24px;font-size:13px;font-weight:600}.feature-card:not(:first-child) .feature-copy{bottom:14px;left:18px}.feature-card:not(:first-child) strong{-webkit-line-clamp:1}
.section-title{display:flex;align-items:center;gap:14px;font-size:20px;margin-bottom:16px}.section-title span{font-size:12px;font-weight:400;color:var(--color-text-secondary,#85919e)}
.catalog-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:24px 18px}.catalog-card{min-width:0}.catalog-card:focus-visible{outline:3px solid #13ad72;outline-offset:4px}.catalog-card strong{font-size:15px}.catalog-card:hover strong{color:#087d51}.feature-card:hover strong{color:#b4f8d0}.recent{padding:20px 0;border:0;background:transparent;border-top:1px solid var(--color-border);border-radius:0}.support-note{font-size:12px}
@media(min-width:1450px){.featured-grid{grid-template-rows:170px 170px}.catalog-grid{grid-template-columns:repeat(5,minmax(0,1fr))}}
@media(max-width:850px){.tencent-view{padding:18px}.topbar{gap:18px}.search-form{width:58%}.featured-grid{grid-template-rows:130px 130px}.feature-card:first-child strong{font-size:25px}.catalog-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:650px){.topbar{flex-wrap:wrap;gap:12px}.brand-icon{width:40px;height:40px}.brand h1{font-size:21px}.brand p{display:none}.search-form{width:100%}.search-form .link-row{flex-direction:row}.search-form button{min-width:70px;padding:10px 14px}.catalog-caption{display:none}.featured-grid{grid-template-columns:1fr 1fr;grid-template-rows:220px 135px;gap:10px}.feature-card:first-child{grid-column:span 2;grid-row:auto}.feature-copy{left:18px;bottom:18px}.feature-card:not(:first-child) .feature-copy{left:12px;right:12px;bottom:12px}.feature-card:not(:first-child) strong{font-size:16px}.feature-card:not(:first-child) small{display:none}.feature-kind{top:8px;right:8px;font-size:10px}.catalog-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 12px}.section-title span{display:none}}
</style>
