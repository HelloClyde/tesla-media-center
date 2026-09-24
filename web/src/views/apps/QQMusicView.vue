<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import { ElMessage } from 'element-plus';
import { Headset, VideoPlay, VideoPause, ArrowLeft, ArrowRight, Search } from '@element-plus/icons-vue';

interface Song { mid: string; title: string; singer: string; album: string; cover: string; duration: number }
const router = useRouter();
const query = ref('');
const searched = ref('');
const songs = ref<Song[]>([]);
const queue = ref<Song[]>([]);
const page = ref(1);
const more = ref(false);
const busy = ref(false);
const loadingTrack = ref(false);
const current = ref<Song>();
const audio = ref<HTMLAudioElement>();
const playing = ref(false);
const elapsed = ref(0);
const duration = ref(0);
const account = ref({ loggedIn: false, account: '' });
const accountOpen = ref(false);
const qr = ref('');
const qrBusy = ref(false);
const loginHint = ref('使用手机 QQ 扫码，确认登录 QQ 音乐');
const error = ref('');
const qualityOptions = [{ value: 'standard', label: '标准 128k' }, { value: 'high', label: '高品质 320k' }, { value: 'lossless', label: '无损 FLAC' }];
const quality = ref('standard');
try {
  const saved = localStorage.getItem('qqmusic-quality');
  if (qualityOptions.some(option => option.value === saved)) quality.value = saved!;
} catch { /* Storage may be unavailable in private browsing. */ }
function changeQuality() {
  try { localStorage.setItem('qqmusic-quality', quality.value); } catch { /* Keep the session preference. */ }
  if (current.value) ElMessage.info('音质已保存，下次播放歌曲时生效');
}
let loginGeneration = 0;
let playGeneration = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let sources: string[] = [];
let sourceIndex = 0;

async function api(path: string, data?: object) {
  const response = await axios.request({ url: '/api/qqmusic/' + path, method: data ? 'POST' : 'GET', data, timeout: 30000, validateStatus: () => true });
  if (response.data.status === 'need_login') {
    router.push('/login');
    throw new Error('请先登录媒体中心');
  }
  if (response.data.status !== 'ok') throw new Error(response.data.message || 'QQ 音乐请求失败，请稍后重试');
  return response.data.data;
}
function message(e: unknown) { return e instanceof Error ? e.message : '请求失败，请稍后重试'; }
async function refreshAccount() { account.value = await api('account'); }
async function search(loadMore = false) {
  if (busy.value || (!loadMore && !query.value.trim())) return;
  busy.value = true;
  error.value = '';
  const keyword = loadMore ? searched.value : query.value.trim();
  const next = loadMore ? page.value + 1 : 1;
  try {
    const result = await api(`search?q=${encodeURIComponent(keyword)}&page=${next}`);
    songs.value = loadMore ? [...songs.value, ...result.songs] : result.songs;
    searched.value = keyword;
    page.value = next;
    more.value = result.more;
  } catch (e) { error.value = message(e); }
  finally { busy.value = false; }
}
async function play(song: Song, fromList = false) {
  const generation = ++playGeneration;
  sources = [];
  sourceIndex = 0;
  if (fromList) queue.value = [...songs.value];
  audio.value?.pause();
  audio.value?.removeAttribute('src');
  audio.value?.load();
  current.value = song;
  elapsed.value = 0;
  duration.value = 0;
  loadingTrack.value = true;
  error.value = '';
  try {
    const result = await api(`play?mid=${encodeURIComponent(song.mid)}&quality=${quality.value}`);
    if (disposed || generation !== playGeneration || !audio.value) return;
    sources = result.urls || [result.url];
    audio.value.src = sources[0];
    await audio.value.play();
  } catch (e) {
    if (generation === playGeneration && !disposed && sourceIndex === 0) error.value = message(e);
  } finally { if (generation === playGeneration) loadingTrack.value = false; }
}
function mediaError() {
  if (disposed || !audio.value?.getAttribute('src')) return;
  if (sourceIndex + 1 < sources.length) {
    const generation = playGeneration;
    audio.value.src = sources[++sourceIndex];
    error.value = '';
    void audio.value.play().catch(() => {
      if (generation === playGeneration && sourceIndex === sources.length - 1) error.value = '音源加载失败，请重新播放或更换歌曲';
    });
  } else error.value = '音源加载失败，请重新播放或更换歌曲';
}
function step(delta: number) {
  const i = queue.value.findIndex(s => s.mid === current.value?.mid) + delta;
  if (i >= 0 && i < queue.value.length) void play(queue.value[i]);
}
async function toggle() {
  if (!current.value || loadingTrack.value) return;
  if (playing.value) audio.value?.pause();
  else if (!audio.value?.getAttribute('src') || audio.value.error) await play(current.value);
  else try { await audio.value.play(); } catch { error.value = '播放被浏览器暂停，请再次点击播放'; }
}
function time(value: number) { return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`; }
function updateTime() {
  elapsed.value = audio.value?.currentTime || 0;
  const value = audio.value?.duration || 0;
  duration.value = Number.isFinite(value) ? value : 0;
}
function seek(event: Event) { if (audio.value) audio.value.currentTime = Number((event.target as HTMLInputElement).value); }
function stopPoll() { ++loginGeneration; clearTimeout(timer); }
async function startLogin() {
  stopPoll();
  const generation = loginGeneration;
  qr.value = '';
  qrBusy.value = true;
  loginHint.value = '正在获取二维码…';
  try {
    const result = await api('login', {});
    if (disposed || generation !== loginGeneration) return;
    qr.value = result.image;
    loginHint.value = '使用手机 QQ 扫码，确认登录 QQ 音乐';
    const deadline = Date.now() + 180000;
    async function poll() {
      if (generation !== loginGeneration || disposed) return;
      try {
        const resultState = await api('login/status', { token: result.token });
        if (generation !== loginGeneration || disposed) return;
        const state = resultState.state;
        if (state === 'DONE') {
          await refreshAccount();
          qr.value = '';
          loginHint.value = '登录成功';
          ElMessage.success('QQ 音乐登录成功');
          return;
        }
        if (state === 'TIMEOUT' || state === 'REFUSE' || Date.now() >= deadline) {
          qr.value = '';
          loginHint.value = state === 'REFUSE' ? '已取消授权，可重新扫码' : '二维码已过期，请刷新';
          return;
        }
        loginHint.value = state === 'CONF' ? '已扫码，请在手机上确认' : '等待手机 QQ 扫码确认';
        timer = setTimeout(poll, 2000);
      } catch (e) { if (generation === loginGeneration) { qr.value = ''; loginHint.value = message(e); } }
    }
    timer = setTimeout(poll, 2000);
  } catch (e) { if (generation === loginGeneration) loginHint.value = message(e); }
  finally { if (generation === loginGeneration) qrBusy.value = false; }
}
async function logout() {
  try {
    await api('logout', {});
    stopPoll();
    ++playGeneration;
    audio.value?.pause();
    audio.value?.removeAttribute('src');
    audio.value?.load();
    current.value = undefined;
    loadingTrack.value = false;
    account.value = { loggedIn: false, account: '' };
    qr.value = '';
  } catch (e) { ElMessage.error(message(e)); }
}
onMounted(() => { refreshAccount().catch(e => { error.value = message(e); }); });
onBeforeUnmount(() => { disposed = true; stopPoll(); ++playGeneration; audio.value?.pause(); audio.value?.removeAttribute('src'); audio.value?.load(); });
</script>

<template>
  <section class="music-page">
    <header class="music-header">
      <div class="brand"><el-icon><Headset /></el-icon><strong>QQ 音乐</strong></div>
      <el-select v-model="quality" aria-label="播放音质" title="播放音质，下次播放生效" style="width: 132px; margin-left: auto" @change="changeQuality">
        <el-option v-for="option in qualityOptions" :key="option.value" :label="option.label" :value="option.value" :disabled="option.value === 'lossless' && !audio?.canPlayType('audio/flac')" />
      </el-select>
      <el-button round @click="accountOpen = true">{{ account.loggedIn ? '已登录 · 账号' : '登录 QQ 音乐' }}</el-button>
    </header>
    <form class="search" @submit.prevent="search()">
      <el-input v-model="query" :prefix-icon="Search" placeholder="搜索歌曲、歌手或专辑" maxlength="100" clearable aria-label="搜索歌曲" />
      <el-button type="primary" native-type="submit" :loading="busy">搜索</el-button>
    </form>
    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />
    <div class="results">
      <div v-if="!searched && !busy" class="empty"><el-icon :size="44"><Headset /></el-icon><h2>音乐，随行</h2><p>搜索你喜欢的歌曲，点击即可播放</p><p class="muted">部分歌曲需登录并具备相应账号权益</p></div>
      <p v-else-if="!songs.length && !busy" class="empty">没有找到相关歌曲，试试其他关键词</p>
      <button v-for="song in songs" :key="song.mid" class="song" :class="{ active: current?.mid === song.mid }" @click="play(song, true)">
        <img :src="song.cover" alt="" loading="lazy" />
        <span class="song-text"><strong>{{ song.title }}</strong><span>{{ song.singer }} · {{ song.album }}</span></span>
        <span class="muted">{{ time(song.duration) }}</span><el-icon><VideoPlay /></el-icon>
      </button>
      <el-button v-if="more" class="load-more" :loading="busy" @click="search(true)">加载更多</el-button>
    </div>
    <footer class="player">
      <div class="now-playing"><img v-if="current" :src="current.cover" alt="" /><div class="song-text"><strong>{{ current?.title || '还没有播放歌曲' }}</strong><span>{{ loadingTrack ? '正在加载…' : current?.singer || '从搜索结果中选择歌曲' }}</span></div></div>
      <div class="play-controls">
        <el-button circle :icon="ArrowLeft" aria-label="上一首" :disabled="!current || queue.findIndex(s => s.mid === current?.mid) <= 0" @click="step(-1)" />
        <el-button circle type="primary" :icon="playing ? VideoPause : VideoPlay" :aria-label="playing ? '暂停' : '播放'" :loading="loadingTrack" :disabled="!current" @click="toggle" />
        <el-button circle :icon="ArrowRight" aria-label="下一首" :disabled="!current || queue.findIndex(s => s.mid === current?.mid) >= queue.length - 1" @click="step(1)" />
      </div>
      <div class="seek"><span>{{ time(elapsed) }}</span><input type="range" min="0" :max="duration || 1" step="0.1" :value="elapsed" :disabled="!duration || loadingTrack" aria-label="播放进度" @input="seek" /><span>{{ time(duration) }}</span></div>
    </footer>
    <audio ref="audio" preload="metadata" @play="playing = true; error = ''" @pause="playing = false" @timeupdate="updateTime" @durationchange="updateTime" @ended="step(1)" @error="mediaError" />
    <el-dialog v-model="accountOpen" title="QQ 音乐账号" width="min(400px, 90vw)" align-center @closed="stopPoll(); qrBusy = false; qr = ''">
      <div class="account-panel" v-if="account.loggedIn"><p>已登录账号 {{ account.account }}</p><el-button @click="logout">退出 QQ 音乐登录</el-button></div>
      <div class="account-panel" v-else><img v-if="qr" class="qr" :src="qr" alt="QQ 音乐登录二维码" /><p>{{ loginHint }}</p><el-button type="primary" :loading="qrBusy" @click="startLogin">{{ qr ? '刷新二维码' : '获取登录二维码' }}</el-button></div>
      <p class="account-note">使用手机 QQ 扫码授权，无需在本页面输入 QQ 密码。登录仅用于当前浏览器；账号权限由 QQ 音乐决定。</p>
    </el-dialog>
  </section>
</template>

<style scoped>
.music-page{height:100%;min-height:0;display:flex;flex-direction:column;gap:12px;padding:16px;box-sizing:border-box;color:var(--color-text)}
.music-header,.brand,.search,.song,.now-playing,.play-controls,.seek{display:flex;align-items:center;gap:12px}
.music-header{justify-content:space-between}.brand{font-size:20px}.brand .el-icon{color:#19b978}.search .el-input{flex:1}.results{flex:1;min-height:0;overflow:auto}.empty{text-align:center;padding:36px 8px;color:var(--color-text-soft)}.empty h2{margin:14px 0 6px}.empty p{font-size:14px}.muted{color:var(--color-text-soft);font-size:12px}.song{width:100%;padding:10px 8px;text-align:left;border:0;border-bottom:1px solid var(--color-border);background:transparent;color:inherit;cursor:pointer;border-radius:10px}.song:hover,.song.active{background:rgba(25,185,120,.09)}.song img,.now-playing img{width:44px;height:44px;object-fit:cover;border-radius:8px}.song-text{display:flex;flex-direction:column;gap:4px;min-width:0;flex:1}.song-text strong,.song-text span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.song-text strong{font-size:15px;font-weight:500}.song-text span{font-size:12px;color:var(--color-text-soft)}.song>.el-icon{font-size:24px;color:#19b978}.load-more{display:block;margin:12px auto}.player{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 16px;border-top:1px solid var(--color-border);padding-top:12px}.now-playing{min-width:0}.play-controls{gap:8px}.play-controls .el-button{margin:0;width:42px;height:42px}.seek{grid-column:1/-1;gap:10px;font-size:12px;font-variant-numeric:tabular-nums}.seek input{flex:1;min-width:0;accent-color:#19b978;height:28px;cursor:pointer}.account-panel{text-align:center}.qr{width:190px;height:190px;image-rendering:pixelated;background:white;padding:10px}.account-note{font-size:12px;color:var(--color-text-soft);line-height:1.8;margin-top:20px}@media(max-width:600px){.music-page{padding:10px;gap:10px}.brand{font-size:18px}.song{gap:8px}.player{gap:8px}.play-controls{gap:4px}.play-controls .el-button{width:36px;height:36px}}
</style>
