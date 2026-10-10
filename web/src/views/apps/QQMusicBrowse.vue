<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useAudioChannel } from '@/functions/useAudioChannel';
interface Item { id: string; title: string; cover: string; kind: string; group?: string; subtitle?: string; count?: number }
const props = defineProps<{ initial: Item; active?: boolean; api: (path: string, data?: object) => Promise<any> }>();
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
const canvas = ref<HTMLCanvasElement>(), loading = ref<HTMLElement>();
const track = ref<HTMLInputElement>(), timeLabel = ref<HTMLElement>();
const { channelAudio, startAudioChannel, restoreAudioChannel } = useAudioChannel();
const mediaUrl = ref(''), directUrl = ref(''), videoPlaying = ref(false), audioBlocked = ref(false);
let player: any = null, playbackGeneration = 0;
let watchdog: ReturnType<typeof setTimeout> | undefined;
const isActive = () => props.active !== false;
function stopPlayback() {
  ++playbackGeneration;
  clearTimeout(watchdog);
  player?.destroy(); player = null;
  channelAudio.value?.pause();
  videoPlaying.value = false; audioBlocked.value = false;
}
async function startPlayback() {
  if (!mediaUrl.value || !isActive()) return;
  stopPlayback(); error.value = '';
  const ticket = playbackGeneration;
  emit('video'); startAudioChannel();
  await nextTick();
  if (ticket !== playbackGeneration || !canvas.value || !isActive()) return;
  try {
    player = new Player();
    player.setLoadingDiv(loading.value);
    player.setTrack(track.value, timeLabel.value);
    player.setFinishCallback(() => { if (ticket === playbackGeneration) videoPlaying.value = false; });
    player.setTimeCallback((time: number) => { if (time > 0) clearTimeout(watchdog); });
    player.setAudioBlockedCallback?.((blocked: boolean) => {
      if (ticket === playbackGeneration) { audioBlocked.value = blocked; if (blocked) videoPlaying.value = false; }
    });
    watchdog = setTimeout(() => {
      if (ticket === playbackGeneration) { error.value = 'MV 加载超时，请重试'; stopPlayback(); }
    }, 70000);
    const status = player.play(mediaUrl.value, canvas.value, (event: any) => {
      if (ticket !== playbackGeneration || !event.error || event.error === 1) return;
      error.value = event.message || 'MV 播放失败，请重试'; stopPlayback();
    }, 512 * 1024, false, undefined, [directUrl.value, mediaUrl.value].filter(Boolean));
    if (status?.e) throw new Error(status.m || '软解播放器启动失败');
    videoPlaying.value = true;
  } catch (cause) {
    if (ticket === playbackGeneration) {
      error.value = cause instanceof Error ? cause.message : 'MV 播放失败';
      stopPlayback();
    }
  }
}
function togglePlayback() {
  if (!player) { void startPlayback(); return; }
  if (player.getState() === 1) { player.pause(); videoPlaying.value = false; }
  else if (player.getState() === 2) { player.resume(); videoPlaying.value = true; }
}
watch(() => props.active, active => {
  if (active === false) stopPlayback();
  else if (mediaUrl.value && selected.value.kind === 'mv') void startPlayback();
});
const trail = ref<Item[]>([]);
const selected = ref(props.initial);
const items = ref<Item[]>([]), songs = ref<any[]>([]);
const busy = ref(false), error = ref(''), page = ref(1), more = ref(false);
let generation = 0;
async function load(append = false) {
  const id = ++generation; busy.value = true; error.value = '';
  if (!append) { stopPlayback(); items.value = []; songs.value = []; mediaUrl.value = ''; directUrl.value = ''; more.value = false; }
  const next = append ? page.value + 1 : 1;
  try {
    if (selected.value.kind === 'mv') {
      const result = await props.api('mv?id=' + encodeURIComponent(selected.value.id));
      if (id !== generation) return;
      if (typeof result.url !== 'string' || !result.url.startsWith('/api/qqmusic/mv/media/')) throw new Error('MV 播放地址无效');
      mediaUrl.value = result.url;
      directUrl.value = '';
      if (typeof result.directUrl === 'string') {
        try {
          const candidate = new URL(result.directUrl);
          if (candidate.protocol === 'https:' && (candidate.hostname.endsWith('.qq.com') || candidate.hostname.endsWith('.qqmusic.com')))
            directUrl.value = candidate.href;
        } catch { /* The authenticated relay remains available. */ }
      }
      if (props.active !== false) void startPlayback();
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
function open(item: Item) { if (item.kind === 'mv') { emit('video'); startAudioChannel(); } trail.value.push(selected.value); selected.value = item; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }
function back() { selected.value = trail.value.pop()!; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }
watch(() => props.initial, item => { selected.value = item; trail.value = []; artistTab.value = 'songs'; group.value = '全部'; void loadProfile(); void load(); }, { immediate: true });
onBeforeUnmount(() => { ++generation; ++profileGeneration; stopPlayback(); });
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
    <div v-if="mediaUrl && active !== false" class="mv-player">
      <div class="mv-picture"><canvas ref="canvas" aria-label="QQ 音乐 MV 播放画面" width="960" height="540"></canvas><div ref="loading" class="mv-loading" style="display:none">正在缓冲…</div></div>
      <div class="mv-controls"><button type="button" @click="togglePlayback">{{ videoPlaying ? '暂停' : '播放' }}</button><input ref="track" type="range" min="0" value="0" aria-label="MV 播放进度"/><span ref="timeLabel">00:00:00/00:00:00</span><button type="button" @click="restoreAudioChannel">{{ audioBlocked ? '启动声音' : '恢复声音' }}</button><button type="button" @click="player?.fullscreen()">全屏</button></div>
    </div>
    <audio ref="channelAudio" class="mv-channel-audio" aria-hidden="true"></audio>
    <div class="cards"><button v-for="item in displayedItems" :key="item.kind + item.id" @click="open(item)"><img v-if="item.cover" :src="item.cover" alt="" loading="lazy" /><strong>{{ item.title }}</strong><small v-if="item.subtitle">{{ item.subtitle }}</small></button></div>
    <button v-for="(song, index) in songs" :key="song.mid" class="track" @click="emit('play', song, songs)"><b v-if="selected.kind === 'top'" class="rank" :class="{ podium: index < 3 }">{{ String(index + 1).padStart(2, '0') }}</b><img :src="song.cover" alt="" /><span>{{ song.title }}<small>{{ song.singer }}</small></span><span>播放</span></button>
    <p v-if="!busy && !error && !items.length && !songs.length && !mediaUrl">暂无内容</p>
    <el-button v-if="more" :loading="busy" @click="load(true)">加载更多</el-button>
  </section>
</template>
<style scoped>
.profile-hero{display:flex;align-items:flex-start;gap:18px;padding:18px;border-radius:16px;background:linear-gradient(130deg,#1c6251,#263e50);color:white;margin-bottom:16px}.profile-hero img{width:100px;height:100px;object-fit:cover;border-radius:12px}.profile-hero img.portrait{border-radius:50%}.profile-hero h2{margin:0 0 10px;font-size:24px}.profile-hero p{font-size:13px;line-height:1.7}.description{white-space:pre-line}.profile-hero summary{cursor:pointer;font-size:13px;margin-top:10px}.browse-tabs{display:flex;flex-wrap:wrap;margin-bottom:14px}.play-all{margin-bottom:14px}.rank{width:30px;font-size:20px;font-variant-numeric:tabular-nums;color:var(--color-text-soft)}.rank.podium{color:#19b978}.cards small{display:block;margin-top:6px;color:var(--color-text-soft);font-size:11px}.profile-error{font-size:13px;color:var(--color-text-soft)}
.browse{min-height:0;overscroll-behavior:contain}
header{display:flex;align-items:center;gap:12px}h3{margin:4px 0 18px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}.cards button,.track{border:1px solid var(--color-border);background:var(--color-surface);color:var(--color-text);border-radius:12px;text-align:left;padding:10px;cursor:pointer}.cards img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}.cards strong{display:block;margin-top:8px}.track{display:flex;align-items:center;gap:12px;width:100%;margin-bottom:6px}.track img{width:42px;height:42px;border-radius:6px}.track>span:first-of-type{flex:1}.track small{display:block;color:var(--color-text-soft);margin-top:5px}.mv-player{width:100%;margin-bottom:18px}.mv-picture{position:relative;background:#000;aspect-ratio:16/9;max-height:65vh}.mv-picture canvas{display:block;width:100%;height:100%}.mv-loading{position:absolute;inset:0;display:grid;place-items:center;color:#fff;background:#0006;pointer-events:none}.mv-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px}.mv-controls button{min-height:40px;padding:8px 12px;border:1px solid var(--color-border);border-radius:8px;background:var(--color-surface);color:var(--color-text)}.mv-controls input{flex:1;min-width:120px}.mv-controls span{font-size:12px;font-variant-numeric:tabular-nums}.mv-channel-audio{display:none}
</style>
