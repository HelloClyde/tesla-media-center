<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
interface Item { id: string; title: string; cover: string; kind: string; group?: string; subtitle?: string; count?: number }
const props = defineProps<{ initial: Item; api: (path: string, data?: object) => Promise<any> }>();
const emit = defineEmits<{ play: [song: any, songs: any[]]; video: [] }>();
const artistTab = ref('songs'), group = ref('全部');
const profile = ref<{ title: string; cover: string; description: string; area?: string; genre?: string; updated?: string; period?: string; count?: number }>();
const profileError = ref('');
let profileGeneration = 0;
const groups = computed(() => ['全部', ...new Set(items.value.map(item => item.group).filter((value): value is string => !!value))]);
const displayedItems = computed(() => selected.value.kind === 'tops' && group.value !== '全部' ? items.value.filter(item => item.group === group.value) : items.value);
async function loadProfile() {
  const generation = ++profileGeneration; profile.value = undefined; profileError.value = '';
  if (selected.value.kind !== 'singer') return;
  try { const result = await props.api('singer-profile?id=' + encodeURIComponent(selected.value.id)); if (generation === profileGeneration) profile.value = result; }
  catch { if (generation === profileGeneration) profileError.value = '歌手资料暂时无法加载'; }
}
const trail = ref<Item[]>([]);
const selected = ref(props.initial);
const items = ref<Item[]>([]), songs = ref<any[]>([]);
const busy = ref(false), error = ref(''), page = ref(1), more = ref(false);
const urls = ref<string[]>([]), urlIndex = ref(0);
let generation = 0;
async function load(append = false) {
  const id = ++generation; busy.value = true; error.value = '';
  if (!append) { items.value = []; songs.value = []; urls.value = []; urlIndex.value = 0; more.value = false; }
  const next = append ? page.value + 1 : 1;
  try {
    if (selected.value.kind === 'mv') {
      const result = await props.api('mv?id=' + encodeURIComponent(selected.value.id));
      if (id !== generation) return;
      urls.value = result.urls;
      emit('video');
    } else {
      const kind = selected.value.kind === 'singer' && artistTab.value !== 'songs' ? 'singer-' + artistTab.value : selected.value.kind;
      const result = await props.api(`browse?kind=${kind}&id=${encodeURIComponent(selected.value.id)}&q=${encodeURIComponent(selected.value.id)}&page=${next}`);
      if (id !== generation) return;
      items.value = append ? [...new Map([...items.value, ...result.items].map(item => [item.kind + ':' + item.id, item])).values()] : result.items;
      songs.value = append ? [...songs.value, ...result.songs] : result.songs;
      more.value = result.more; page.value = next; if (result.info) profile.value = result.info;
    }
  } catch (e) { if (id === generation) error.value = e instanceof Error ? e.message : '加载失败'; }
  finally { if (id === generation) busy.value = false; }
}
function open(item: Item) { trail.value.push(selected.value); selected.value = item; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }
function back() { selected.value = trail.value.pop()!; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }
watch(() => props.initial, item => { selected.value = item; trail.value = []; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }, { immediate: true });
onBeforeUnmount(() => { ++generation; ++profileGeneration; });
function videoError() { if (urlIndex.value + 1 < urls.value.length) ++urlIndex.value; else error.value = '视频加载失败或当前浏览器不支持此编码'; }
</script>
<template>
  <section class="browse">
    <header><el-button v-if="trail.length" @click="back">返回</el-button><h3>{{ selected.title }}</h3></header>
    <div v-if="profile" class="profile-hero"><img v-if="profile.cover" :src="profile.cover" alt="" :class="{ portrait: selected.kind === 'singer' }" /><div><h2>{{ profile.title }}</h2><p>{{ [profile.area, profile.genre, profile.updated && ('更新于 ' + profile.updated), profile.period && ('第 ' + profile.period + ' 期')].filter(Boolean).join(' · ') }}</p><small v-if="profile.count">{{ profile.count }} 首歌曲</small><details v-if="profile.description"><summary>查看简介</summary><p class="description">{{ profile.description }}</p></details></div></div>
    <p v-if="profileError" class="profile-error">{{ profileError }} <el-button text @click="loadProfile">重试</el-button></p>
    <el-radio-group v-if="selected.kind === 'singer'" v-model="artistTab" class="browse-tabs" @change="load()"><el-radio-button value="songs">歌曲</el-radio-button><el-radio-button value="albums">专辑</el-radio-button><el-radio-button value="mvs">MV</el-radio-button></el-radio-group>
    <el-radio-group v-if="selected.kind === 'tops'" v-model="group" class="browse-tabs"><el-radio-button v-for="name in groups" :key="name" :value="name">{{ name }}</el-radio-button></el-radio-group>
    <el-button v-if="songs.length" class="play-all" @click="emit('play', songs[0], songs)">播放当前列表 · {{ songs.length }} 首</el-button>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" /><el-button v-if="error" @click="load()">重试</el-button>
    <p v-if="busy" role="status">正在加载…</p>
    <video v-if="urls.length" :src="urls[urlIndex]" controls autoplay playsinline @play="emit('video')" @error="videoError" />
    <div class="cards"><button v-for="item in displayedItems" :key="item.kind + item.id" @click="open(item)"><img v-if="item.cover" :src="item.cover" alt="" loading="lazy" /><strong>{{ item.title }}</strong><small v-if="item.subtitle">{{ item.subtitle }}</small></button></div>
    <button v-for="(song, index) in songs" :key="song.mid" class="track" @click="emit('play', song, songs)"><b v-if="selected.kind === 'top'" class="rank" :class="{ podium: index < 3 }">{{ String(index + 1).padStart(2, '0') }}</b><img :src="song.cover" alt="" /><span>{{ song.title }}<small>{{ song.singer }}</small></span><span>播放</span></button>
    <p v-if="!busy && !error && !items.length && !songs.length && !urls.length">暂无内容</p>
    <el-button v-if="more" :loading="busy" @click="load(true)">加载更多</el-button>
  </section>
</template>
<style scoped>
.profile-hero{display:flex;align-items:flex-start;gap:18px;padding:18px;border-radius:16px;background:linear-gradient(130deg,#1c6251,#263e50);color:white;margin-bottom:16px}.profile-hero img{width:100px;height:100px;object-fit:cover;border-radius:12px}.profile-hero img.portrait{border-radius:50%}.profile-hero h2{margin:0 0 10px;font-size:24px}.profile-hero p{font-size:13px;line-height:1.7}.description{white-space:pre-line}.profile-hero summary{cursor:pointer;font-size:13px;margin-top:10px}.browse-tabs{display:flex;flex-wrap:wrap;margin-bottom:14px}.play-all{margin-bottom:14px}.rank{width:30px;font-size:20px;font-variant-numeric:tabular-nums;color:var(--color-text-soft)}.rank.podium{color:#19b978}.cards small{display:block;margin-top:6px;color:var(--color-text-soft);font-size:11px}.profile-error{font-size:13px;color:var(--color-text-soft)}
.browse{max-height:65vh;overflow:auto;overscroll-behavior:contain}
header{display:flex;align-items:center;gap:12px}h3{margin:4px 0 18px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}.cards button,.track{border:1px solid var(--color-border);background:var(--color-surface);color:var(--color-text);border-radius:12px;text-align:left;padding:10px;cursor:pointer}.cards img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}.cards strong{display:block;margin-top:8px}.track{display:flex;align-items:center;gap:12px;width:100%;margin-bottom:6px}.track img{width:42px;height:42px;border-radius:6px}.track>span:first-of-type{flex:1}.track small{display:block;color:var(--color-text-soft);margin-top:5px}video{width:100%;max-height:65vh;background:#000}
</style>
