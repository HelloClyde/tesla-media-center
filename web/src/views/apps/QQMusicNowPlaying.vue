<script setup lang="ts">
import QQMusicControlIcon from './QQMusicControlIcon.vue';
import type { PlayMode } from './qqMusicQueue';
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { ArrowDown, ArrowLeft, ArrowRight, VideoPause, VideoPlay } from '@element-plus/icons-vue';
import { parseLrc, parseQrc, lyricIndex, type LyricLine } from './qqMusicLyrics';
const props = defineProps<{
  song: { mid: string; title: string; singer: string; cover: string; album: string };
  playing: boolean; elapsed: number; duration: number; loading: boolean;
  previousDisabled: boolean; nextDisabled: boolean; error: string;
  mode: PlayMode; modeLabel: string; radioActive: boolean; eqEnabled: boolean;
  liked: boolean; collectionBusy: boolean;
  loadWordLyrics: () => Promise<{ lyric: string }>;
  loadLyrics: () => Promise<{ lyric: string; translation: string }>;
}>();
const emit = defineEmits<{ close: []; toggle: []; previous: []; next: []; seek: [value: number]; queue: []; mode: []; equalizer: []; like: []; comments: []; add: [] }>();
const settingsOpen = ref(false);
const fontSize = ref(23), lyricOffset = ref(0), showTranslation = ref(true);
try { const value = JSON.parse(localStorage.getItem('qqmusic-lyrics-settings') || '{}'); fontSize.value = Math.min(36, Math.max(16, Number(value.fontSize) || 23)); lyricOffset.value = Math.min(5, Math.max(-5, Number(value.offset) || 0)); showTranslation.value = value.translation !== false; } catch {}
watch([fontSize, lyricOffset, showTranslation], () => { try { localStorage.setItem('qqmusic-lyrics-settings', JSON.stringify({ fontSize: fontSize.value, offset: lyricOffset.value, translation: showTranslation.value })); } catch {} });
const lyricTime = computed(() => props.elapsed + lyricOffset.value);
const lines = ref<LyricLine[]>([]);
const plain = ref('');
const busy = ref(false);
const failure = ref(false);
const scroller = ref<HTMLElement>();
const panel = ref<HTMLElement>();
const active = computed(() => lyricIndex(lines.value, lyricTime.value));
let generation = 0;
let disposed = false;
async function load() {
  const id = ++generation;
  lines.value = []; plain.value = ''; failure.value = false; busy.value = true;
  try {
    const result = await props.loadLyrics();
    if (disposed || id !== generation) return;
    const translations = new Map(parseLrc(result.translation || '').map(line => [line.time, line.text]));
    lines.value = parseLrc(result.lyric || '').map(line => ({ ...line, translation: translations.get(line.time) }));
    void props.loadWordLyrics().then(result => {
      if (disposed || id !== generation) return;
      const words = parseQrc(result.lyric);
      if (words.length) lines.value = words.map(line => ({ ...line, translation: translations.get(line.time) }));
    }).catch(() => { /* Keep synchronized LRC if QRC is unavailable. */ });
    if (!lines.value.length) plain.value = (result.lyric || '').replace(/\[[^\]]*\]/g, '').trim();
  } catch { if (!disposed && id === generation) failure.value = true; }
  finally { if (!disposed && id === generation) busy.value = false; }
}
watch(() => props.song.mid, load, { immediate: true });
watch([active, lines], async () => {
  await nextTick();
  const container = scroller.value;
  const line = container?.querySelector<HTMLElement>('[aria-current="true"]');
  if (container && line) container.scrollTo({ top: line.offsetTop - container.offsetTop - container.clientHeight / 2 + line.clientHeight / 2, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}, { flush: 'post' });
nextTick(() => panel.value?.focus());
onBeforeUnmount(() => { disposed = true; ++generation; });
function time(value: number) { return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`; }
</script>

<template>
  <section ref="panel" class="listening" :class="{ running: playing && !loading }" tabindex="-1" aria-label="正在播放" @keydown.esc.stop="emit('close')">
    <div class="ambient ambient-one"></div><div class="ambient ambient-two"></div>
    <header><button class="round" aria-label="返回歌曲列表" @click="emit('close')"><el-icon><ArrowDown /></el-icon></button><span>QQ MUSIC <i>/</i> 正在播放</span><button class="settings-trigger" @click="settingsOpen = !settingsOpen">歌词设置</button><span class="live-label">{{ loading ? '加载中' : playing ? '播放中' : '已暂停' }}</span></header>
    <div v-if="settingsOpen" class="lyric-settings"><label>字号 <input v-model.number="fontSize" type="range" min="16" max="36" aria-label="歌词字号" /></label><label>歌词提前 {{ lyricOffset }} 秒 <input v-model.number="lyricOffset" type="range" min="-5" max="5" step="0.1" aria-label="歌词时间调整" /></label><label><input v-model="showTranslation" type="checkbox" />译文</label></div>
    <div class="stage">
      <div class="artwork">
        <div class="record"><img v-if="song.cover" :src="song.cover" alt="专辑封面" /><div v-else class="cover-fallback">♪</div><span class="spindle"></span></div>
        <div class="track-info"><h1>{{ song.title }}</h1><p>{{ song.singer }}</p><small>{{ song.album }}</small></div>
        <div class="sound-bars" aria-hidden="true"><i v-for="n in 17" :key="n" :style="{ animationDelay: `${n * -.17}s`, animationDuration: `${.7 + n % 5 * .16}s` }"></i></div>
      </div>
      <div ref="scroller" class="lyrics" :style="{ '--lyric-size': fontSize + 'px' }" aria-label="歌词">
        <p v-if="busy" class="lyric-status" role="status">正在寻找这首歌的文字…</p>
        <div v-else-if="failure" class="lyric-status"><p>歌词暂时无法加载</p><button class="retry" @click="load">重新加载</button></div>
        <template v-else-if="lines.length"><div class="lyric-space"></div><button v-for="(line, index) in lines" :key="index" class="lyric-line" :class="{ active: index === active }" :aria-current="index === active ? 'true' : undefined" :disabled="!duration || loading" :aria-label="`${line.text || '间奏'}，跳转到 ${time(line.time)}`" @click="emit('seek', Math.max(0, line.time - lyricOffset))"><template v-if="line.words?.length"><span v-for="(word, wordIndex) in line.words" :key="wordIndex" :style="{ color: lyricTime >= word.time ? '#d6ffdf' : '#8daba1' }">{{ word.text }}</span></template><template v-else>{{ line.text || '· · ·' }}</template><small v-if="showTranslation && line.translation">{{ line.translation }}</small></button><div class="lyric-space"></div></template>
        <p v-else class="lyric-status plain">{{ plain || '暂无歌词，让旋律继续陪伴你' }}</p>
      </div>
    </div>
    <footer>
      <p v-if="error" class="play-error" role="status">{{ error }}</p>
      <div class="timeline"><span>{{ time(elapsed) }}</span><input type="range" min="0" :max="duration || 1" step="0.1" :value="elapsed" :disabled="!duration || loading" aria-label="正在播放进度" @input="emit('seek', Number(($event.target as HTMLInputElement).value))" /><span>{{ time(duration) }}</span></div>
      <div class="transport"><button class="round" :disabled="radioActive" :aria-label="radioActive ? '猜你喜欢连续推荐' : modeLabel + '，点击切换'" :title="radioActive ? '猜你喜欢保持连续推荐模式' : modeLabel + '，点击切换'" @click="emit('mode')"><QQMusicControlIcon :kind="mode" /></button><button class="round" :class="{ 'eq-active': eqEnabled }" aria-label="打开均衡器" title="均衡器" @click="emit('equalizer')"><QQMusicControlIcon kind="equalizer" /></button><button class="round" aria-label="播放队列" @click="emit('queue')">☷</button><button class="round" :disabled="collectionBusy" :aria-label="liked ? '取消红心收藏' : '红心收藏'" @click="emit('like')">{{ liked ? '♥' : '♡' }}</button><button class="round" :disabled="previousDisabled || loading" aria-label="上一首" @click="emit('previous')"><el-icon><ArrowLeft /></el-icon></button><button class="round main-control" :disabled="loading" :aria-label="playing ? '暂停' : '播放'" @click="emit('toggle')"><el-icon><VideoPause v-if="playing" /><VideoPlay v-else /></el-icon></button><button class="round" :disabled="nextDisabled" aria-label="下一首" @click="emit('next')"><el-icon><ArrowRight /></el-icon></button><button class="round" aria-label="添加到歌单" @click="emit('add')">＋</button><button class="round" aria-label="评论" @click="emit('comments')">评</button></div>
    </footer>
  </section>
</template>

<style scoped>
.transport{flex-wrap:wrap}.round.eq-active{color:#b9f6ce;border-color:#b9f6ce;background:#b9f6ce18}
.settings-trigger{color:inherit;border:1px solid #ffffff30;border-radius:16px;padding:6px 10px;background:none;cursor:pointer;margin-left:auto}.lyric-settings{display:flex;flex-wrap:wrap;align-items:center;gap:12px;font-size:12px;padding-top:10px}.lyric-settings label{display:flex;gap:6px;align-items:center}.lyric-settings input[type=range]{width:90px}.transport{gap:12px!important}@media(max-width:600px){.transport{gap:7px!important}.transport .round{width:36px;height:36px;font-size:18px}}
.listening{position:absolute;inset:0;z-index:10;isolation:isolate;display:flex;flex-direction:column;overflow:hidden;padding:20px 28px;background:#101e20;color:#f1f6ec;border-radius:inherit;outline:none;box-sizing:border-box}.ambient{position:absolute;width:65%;height:85%;border-radius:50%;filter:blur(70px);opacity:.23;z-index:-1;pointer-events:none;animation:drift 15s ease-in-out infinite alternate;animation-play-state:paused}.ambient-one{background:#4ca284;left:-20%;top:-30%}.ambient-two{background:#6370a2;right:-20%;bottom:-30%;animation-delay:-7s}.running .ambient,.running .record,.running .sound-bars i{animation-play-state:running}header{display:flex;align-items:center;gap:14px;flex-shrink:0}header>span{font-size:10px;letter-spacing:2px;color:#becbc7}header i{font-style:normal;color:#687f7d;margin:0 8px}.live-label{margin-left:auto;letter-spacing:1px!important}.round{border:1px solid #ffffff25;background:#ffffff08;color:inherit;width:42px;height:42px;border-radius:50%;display:grid;place-items:center;cursor:pointer;flex-shrink:0;font-size:20px}button:disabled{opacity:.4;cursor:default}button:focus-visible{outline:2px solid #b9f6ce;outline-offset:3px}.stage{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:28px;min-height:0;flex:1;padding:20px 0}.artwork{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:0;min-width:0}.record{width:clamp(100px,24vh,260px);aspect-ratio:1;border-radius:50%;padding:14px;background:repeating-radial-gradient(circle,#172324 0 3px,#30413d 4px 5px);box-shadow:0 12px 35px #0005,0 0 0 1px #ffffff18;position:relative;animation:spin 30s linear infinite;animation-play-state:paused;flex-shrink:0;box-sizing:border-box}.record img,.cover-fallback{width:100%;height:100%;object-fit:cover;border-radius:50%}.cover-fallback{display:grid;place-items:center;background:#386855;font-size:44px}.spindle{position:absolute;left:calc(50% - 7px);top:calc(50% - 7px);width:14px;height:14px;border-radius:50%;background:#152a26;border:3px solid #d6e7d4;box-sizing:border-box}.track-info{text-align:center;width:100%;margin-top:20px}.track-info h1{font-size:clamp(18px,2.6vw,28px);margin:0 0 7px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.track-info p{font-size:14px;color:#bacdc5;margin:0 0 4px}.track-info small{font-size:11px;color:#7e9b90;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sound-bars{height:22px;display:flex;align-items:center;gap:4px;margin-top:14px}.sound-bars i{width:3px;height:18px;background:#a4d5b5;border-radius:4px;animation:pulse 1s ease-in-out infinite alternate;animation-play-state:paused}.lyrics{position:relative;min-height:0;overflow:auto;scrollbar-width:none;mask-image:linear-gradient(transparent,#000 16%,#000 84%,transparent)}.lyrics::-webkit-scrollbar{display:none}.lyric-space{height:50%}.lyric-line{display:block;width:100%;border:0;background:none;text-align:left;font:inherit;font-size:var(--lyric-size,23px);font-weight:600;line-height:1.6;color:#8daba1;padding:12px 6px;cursor:pointer;transition:color .3s,text-shadow .3s}.lyric-line:disabled{opacity:1}.lyric-line.active{color:#d6ffdf;text-shadow:0 0 22px #b9f6ce30}.lyric-line small{display:block;font-size:13px;font-weight:400;margin-top:4px;color:#9fbdac}.lyric-status{height:100%;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;color:#a6beb3;font-size:14px;margin:0;line-height:1.8}.plain{white-space:pre-line;height:auto;min-height:100%}.retry{border:1px solid #ffffff30;border-radius:18px;background:none;color:#d6ffdf;padding:8px 16px;cursor:pointer}footer{flex-shrink:0}.timeline{display:flex;align-items:center;gap:12px;color:#a7bdb5;font-size:11px;font-variant-numeric:tabular-nums}.timeline input{flex:1;min-width:0;accent-color:#b9f6ce;height:26px;cursor:pointer}.transport{display:flex;align-items:center;justify-content:center;gap:26px;margin-top:6px}.main-control{width:50px;height:50px;background:#b9f6ce;color:#15372b;font-size:26px;border:0}.play-error{text-align:center;font-size:12px;color:#ffceb2;margin:0 0 4px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes drift{to{transform:translate(15%,15%) scale(1.2)}}@keyframes pulse{from{transform:scaleY(.25)}to{transform:scaleY(1)}}@media(max-height:550px){.listening{padding:12px 20px}.stage{padding:10px 0;gap:18px}.record{width:clamp(84px,24vh,150px)}.track-info{margin-top:12px}.sound-bars{display:none}.main-control{height:42px;width:42px}.transport{margin-top:0}}@media(max-width:480px){.listening{padding:14px}.stage{gap:14px;grid-template-columns:minmax(0,.8fr) minmax(0,1fr)}.record{width:100%;max-width:140px}.track-info h1{font-size:16px}.lyric-line{padding:10px 2px}header>span{letter-spacing:0;font-size:9px}.live-label{display:none}}@media(prefers-reduced-motion:reduce){.ambient,.record,.sound-bars i{animation:none}.lyric-line{transition:none}}
</style>
