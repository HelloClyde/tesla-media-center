<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { VideoPlay, VideoPause, ArrowLeft, ArrowRight, Search } from '@element-plus/icons-vue';
import { roomImpulse, routeSpatialOutput, type Room } from './qqMusicSpatial';
import { nextIndex, type PlayMode } from './qqMusicQueue';
import QQMusicControlIcon from './QQMusicControlIcon.vue';
import QQMusicPlaylistShelf from './QQMusicPlaylistShelf.vue';
import QQMusicBrowse from './QQMusicBrowse.vue';
import QQMusicNowPlaying from './QQMusicNowPlaying.vue';
import { freshRadioBatch } from './qqMusicRadio';

interface Song { mid: string; title: string; singer: string; album: string; cover: string; duration: number; access?: string; maxQuality?: string; singers?: {mid: string; name: string}[]; albumMid?: string }
interface Playlist { id: string; title: string; cover: string; count: number }
const router = useRouter();
const query = ref('');
const searchInput = ref<{ focus: () => void }>();
const membership = ref<{ label: string; level: number | null; isVip: boolean | null }>({ label: '会员状态待查询', level: null, isVip: null });
let membershipGeneration = 0;
const accessLabels: Record<string, string> = { vip: 'VIP', purchase: '单独付费', paid: '付费播放', standard: '普通可听', unknown: '权益待确认' };
const maxQualityLabels: Record<string, string> = { master: '臻品母带', premium: '臻品音质', lossless: 'SQ 无损', high: 'HQ 高品质', standard: '标准', smooth: '流畅', unknown: '音质待确认' };
function maxQualityLabel(song: Song) { const label = maxQualityLabels[song.maxQuality || 'unknown'] || maxQualityLabels.unknown; return label === maxQualityLabels.unknown ? label : '最高 ' + label; }
function accessLabel(song: Song) { return accessLabels[song.access || 'unknown'] || accessLabels.unknown; }
async function openSearch() { tab.value = 'search'; await nextTick(); searchInput.value?.focus(); }
const searched = ref('');
const songs = ref<Song[]>([]);
const tab = ref('home');
const homeMode = ref<'cards' | 'daily'>('cards');
const radioActive = ref(false);
const radioBusy = ref(false);
const radioError = ref('');
const advancing = ref(false);
let radioGeneration = 0;
let radioRequest: Promise<void> | undefined;
const mode = ref<PlayMode>('order');
const modeLabels = { order: '顺序播放', loop: '列表循环', single: '单曲循环', shuffle: '随机播放' };
const queueOpen = ref(false);
const eqOpen = ref(false);
function cycleMode() {
  if (radioActive.value) return;
  const modes: PlayMode[] = ['order', 'loop', 'single', 'shuffle'];
  mode.value = modes[(modes.indexOf(mode.value) + 1) % modes.length];
  ElMessage.success(modeLabels[mode.value]);
}
const audioKey = ref(0), eqEnabled = ref(false), eqBusy = ref(false), eqPreset = ref('flat');
const eqPresets: Record<string, { name: string; gains: number[] }> = {
  flat: { name: '原声', gains: [0, 0, 0, 0, 0] }, bass: { name: '低音', gains: [6, 3, 0, -1, 0] },
  vocal: { name: '人声', gains: [-2, 0, 3, 4, 1] }, soft: { name: '柔和', gains: [1, 0, -1, -2, -3] }
};
const spatialChannels = ref(2), forceStereo = ref(false);
let spatialRouting: ReturnType<typeof routeSpatialOutput> | undefined;
let routingMode: boolean | undefined;
const spatialEnabled = ref(false), spatialRoom = ref<Room>('room'), spatialAmount = ref(25);
let spatialConvolver: ConvolverNode | undefined, spatialWet: GainNode | undefined, spatialDry: GainNode | undefined;
function updateRoom() {
  if (!eqContext || !spatialConvolver) return;
  const channels = roomImpulse(eqContext.sampleRate, spatialRoom.value);
  const buffer = eqContext.createBuffer(2, channels[0].length, eqContext.sampleRate);
  channels.forEach((channel, index) => buffer.getChannelData(index).set(channel));
  spatialConvolver.buffer = buffer;
}
function applySpatial() {
  if (!eqContext || !spatialWet || !spatialDry) return;
  const surround = spatialEnabled.value && !forceStereo.value;
  if (routingMode !== surround) {
    spatialRouting?.dispose(); spatialRouting = undefined;
    try {
      spatialRouting = routeSpatialOutput(eqContext, spatialDry, spatialWet, surround);
      spatialChannels.value = spatialRouting.channels; routingMode = surround;
    } catch {
      routingMode = undefined;
      ElMessage.info('音频输出配置失败，已切回原声');
      if (eqBusy.value) throw new Error('Audio output unavailable');
      void setEq(false, playing.value);
      return;
    }
  }
  const mix = spatialEnabled.value ? Math.min(.5, Math.max(0, spatialAmount.value / 100)) : 0;
  spatialWet.gain.setTargetAtTime(mix, eqContext.currentTime, .03);
  spatialDry.gain.setTargetAtTime(1 - mix * .3, eqContext.currentTime, .03);
}
let eqContext: AudioContext | undefined;
let eqFilters: BiquadFilterNode[] = [];
function applyEq() { eqFilters.forEach((filter, index) => { filter.gain.value = eqPresets[eqPreset.value].gains[index]; }); }
async function setEq(enabled: boolean, resumeAfterError = false) {
  if (eqBusy.value) return;
  eqBusy.value = true;
  const wasPlaying = playing.value || resumeAfterError;
  const position = elapsed.value;
  ++playGeneration;
  audio.value?.pause(); audio.value?.removeAttribute('src'); audio.value?.load();
  if (eqContext) { void eqContext.close(); eqContext = undefined; }
  spatialRouting?.dispose(); spatialRouting = undefined; routingMode = undefined; spatialChannels.value = 2;
  spatialConvolver = undefined; spatialWet = undefined; spatialDry = undefined;
  eqFilters = []; eqEnabled.value = enabled; ++audioKey.value;
  await nextTick();
  try {
    if (enabled && audio.value) {
      eqContext = new AudioContext();
      const source = eqContext.createMediaElementSource(audio.value);
      let previous: AudioNode = source;
      for (const frequency of [60, 230, 910, 3600, 14000]) {
        const filter = eqContext.createBiquadFilter(); filter.type = 'peaking'; filter.frequency.value = frequency; filter.Q.value = 1;
        previous.connect(filter); previous = filter; eqFilters.push(filter);
      }
      const preamp = eqContext.createGain(); preamp.gain.value = .5;
      previous.connect(preamp);
      spatialDry = eqContext.createGain(); spatialWet = eqContext.createGain(); spatialConvolver = eqContext.createConvolver();
      spatialWet.gain.value = 0;
      preamp.connect(spatialDry);
      preamp.connect(spatialConvolver); spatialConvolver.connect(spatialWet);
      updateRoom(); applySpatial(); applyEq(); await eqContext.resume();
    }
  } catch {
    if (eqContext) { void eqContext.close(); eqContext = undefined; }
    eqEnabled.value = false; eqFilters = []; ++audioKey.value; await nextTick();
    ElMessage.info('当前浏览器无法启用均衡器，已保留原声播放');
  }
  restoredPosition = position;
  eqBusy.value = false;
  if (wasPlaying && current.value) await play(current.value);
}

const browseItem = ref<{ id: string; title: string; cover: string; kind: string }>();
const searchKind = ref('song');
const searchHistory = ref<string[]>([]);
const suggestions = ref<string[]>([]);
let suggestionTimer: ReturnType<typeof setTimeout> | undefined;
let suggestionGeneration = 0;
const collectionBusy = ref(false);
const addSong = ref<Song>();
const ownedPlaylists = ref<Playlist[]>([]);
const knownLikes = ref<Record<string, boolean>>({});
const commentsOpen = ref(false);
const commentsSong = ref<Song>();
const comments = ref<{ id: string; name: string; text: string; likes: number }[]>([]);
const commentsBusy = ref(false), commentsError = ref(''), commentsMore = ref(false);
let commentsPage = 0, commentsCursor = '', commentsGeneration = 0;
try {
  const saved = localStorage.getItem('qqmusic-mode');
  if (saved && saved in modeLabels) mode.value = saved as PlayMode;
  const history = JSON.parse(localStorage.getItem('qqmusic-search-history') || '[]');
  if (Array.isArray(history)) searchHistory.value = history.filter(x => typeof x === 'string').slice(0, 12);
} catch { /* Optional preferences. */ }
watch(mode, value => { try { localStorage.setItem('qqmusic-mode', value); } catch {} });
watch(query, value => {
  clearTimeout(suggestionTimer); const generation = ++suggestionGeneration;
  suggestions.value = [];
  if (!value.trim()) return;
  suggestionTimer = setTimeout(async () => {
    try { const result = await api('suggestions?q=' + encodeURIComponent(value.trim())); if (!disposed && generation === suggestionGeneration) suggestions.value = result.words; } catch { /* Suggestions must not block search. */ }
  }, 300);
});
function rememberSearch(word: string) {
  searchHistory.value = [word, ...searchHistory.value.filter(x => x !== word)].slice(0, 12);
  try { localStorage.setItem('qqmusic-search-history', JSON.stringify(searchHistory.value)); } catch {}
}
function clearSearchHistory() { searchHistory.value = []; try { localStorage.removeItem('qqmusic-search-history'); } catch {} }
function openBrowse(kind: string, id: string, title: string) { nowPlayingOpen.value = false; browseItem.value = { kind, id, title, cover: '' }; }
async function playBrowse(song: Song, tracks: Song[]) { stopRadio(); queue.value = [...tracks]; browseItem.value = undefined; await play(song); }
async function collection(action: string, song?: Song, playlist?: string) {
  if (!account.value.loggedIn) { accountOpen.value = true; return; }
  if (collectionBusy.value) return;
  collectionBusy.value = true;
  try {
    let name: string | undefined;
    if (action === 'create') {
      const answer = await ElMessageBox.prompt('输入歌单名称', '新建 QQ 音乐歌单', { inputValidator: value => !!value?.trim() && value.trim().length <= 40 || '请输入 1–40 字的名称' });
      name = answer.value;
    }
    await api('collection', { action, mid: song?.mid, playlist, name });
    if (song && (action === 'like' || action === 'unlike')) knownLikes.value[song.mid] = action === 'like';
    ElMessage.success(action === 'create' ? '歌单已创建' : '已更新 QQ 音乐收藏');
    if (tab.value === 'library') void loadLibrary();
    if (action === 'add') addSong.value = undefined;
    if (action === 'create' && addSong.value) ownedPlaylists.value = (await api('library?kind=created')).playlists;
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(message(e)); }
  finally { collectionBusy.value = false; }
}
async function openAdd(song: Song) {
  if (!account.value.loggedIn) { accountOpen.value = true; return; }
  try { ownedPlaylists.value = (await api('library?kind=created')).playlists; addSong.value = song; } catch (e) { ElMessage.error(message(e)); }
}
function enqueue(song: Song) { if (!queue.value.some(s => s.mid === song.mid)) queue.value.push(song); ElMessage.success('已加入播放队列'); }
function removeQueue(index: number) { queue.value.splice(index, 1); }
function moveQueue(index: number) { if (index > 0) [queue.value[index - 1], queue.value[index]] = [queue.value[index], queue.value[index - 1]]; }
async function openComments(song: Song) {
  commentsSong.value = song; comments.value = []; commentsPage = 0; commentsCursor = ''; commentsMore.value = false; commentsOpen.value = true;
  await loadComments();
}
async function loadComments() {
  if (!commentsSong.value) return;
  const generation = ++commentsGeneration; commentsBusy.value = true; commentsError.value = '';
  try {
    const result = await api(`comments?mid=${encodeURIComponent(commentsSong.value.mid)}&page=${commentsPage + 1}&cursor=${encodeURIComponent(commentsCursor)}`);
    if (disposed || generation !== commentsGeneration) return;
    comments.value = [...new Map([...comments.value, ...result.comments].map(comment => [comment.id, comment])).values()]; commentsMore.value = result.more; commentsCursor = result.cursor; ++commentsPage;
  } catch (e) { if (generation === commentsGeneration) commentsError.value = message(e); }
  finally { if (generation === commentsGeneration) commentsBusy.value = false; }
}
function songAction(action: string, song: Song) {
  if (action === 'like' || action === 'unlike') void collection(action, song);
  else if (action === 'add') void openAdd(song);
  else if (action === 'queue') enqueue(song);
  else if (action === 'comments') void openComments(song);
  else if (action === 'album' && song.albumMid) openBrowse('album', song.albumMid, song.album);
  else if (action.startsWith('singer:')) { const singer = song.singers?.find(x => x.mid === action.slice(7)); if (singer) openBrowse('singer', singer.mid, singer.name); }
  else if (action === 'remove' && selectedPlaylist.value) void collection('remove', song, selectedPlaylist.value.id);
}
const today = new Date().getDate();
const recommendations = ref<Song[]>([]);
const recommendBusy = ref(false);
const recommendError = ref('');
const recommendLoginRequired = ref(false);
const libraryKind = ref('songs');
const librarySongs = ref<Song[]>([]);
const playlists = ref<Playlist[]>([]);
const selectedPlaylist = ref<Playlist>();
const libraryBusy = ref(false);
const libraryError = ref('');
const libraryLoginRequired = ref(false);
const libraryPage = ref(1);
const libraryMore = ref(false);
const recent = ref<Song[]>([]);
let libraryGeneration = 0;
const visibleSongs = computed(() => tab.value === 'home' ? homeMode.value === 'daily' ? recommendations.value : [] : tab.value === 'search' ? songs.value : libraryKind.value === 'recent' ? recent.value : librarySongs.value);
let recommendGeneration = 0;
const queue = ref<Song[]>([]);
const page = ref(1);
const more = ref(false);
const busy = ref(false);
const loadingTrack = ref(false);
const current = ref<Song>();
const nowPlayingOpen = ref(false);
watch(current, value => { if (!value) nowPlayingOpen.value = false; });
const audio = ref<HTMLAudioElement>();
const playing = ref(false);
const elapsed = ref(0);
const duration = ref(0);
const account = ref({ loggedIn: false, account: '' });
const accountOpen = ref(false);
const qr = ref('');
const qrBusy = ref(false);
const loginProvider = ref<'qq' | 'wx'>('qq');
const scanApp = computed(() => loginProvider.value === 'wx' ? '微信' : '手机 QQ');
const loginHint = ref('使用手机 QQ 扫码，确认登录 QQ 音乐');
const error = ref('');
const qualityOptions = [{ value: 'standard', label: '标准 128k' }, { value: 'high', label: '高品质 320k' }, { value: 'lossless', label: '无损 FLAC' }, { value: 'premium', label: '臻品音质' }, { value: 'master', label: '臻品母带' }];
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
let restoredPosition = 0;
let lastSnapshot = 0;
function saveSession() {
  if (!current.value) return;
  try { localStorage.setItem('qqmusic-session-' + (account.value.account || 'guest'), JSON.stringify({ queue: queue.value.slice(0, 200), song: current.value, position: elapsed.value })); } catch {}
}
function restoreSession() {
  if (current.value) return;
  try {
    const value = JSON.parse(localStorage.getItem('qqmusic-session-' + (account.value.account || 'guest')) || 'null');
    const valid = (s: any): s is Song => !!s && /^[a-zA-Z0-9]{1,32}$/.test(s.mid) && ['title', 'singer', 'album', 'cover'].every(k => typeof s[k] === 'string');
    if (valid(value?.song)) { current.value = value.song; queue.value = Array.isArray(value.queue) ? value.queue.filter(valid).slice(0, 200) : [value.song]; restoredPosition = Math.max(0, Number(value.position) || 0); elapsed.value = restoredPosition; }
  } catch {}
}
function loadedMetadata() {
  if (audio.value && restoredPosition && Number.isFinite(audio.value.duration)) { audio.value.currentTime = Math.min(restoredPosition, audio.value.duration); restoredPosition = 0; }
  updateTime();
}
function updateMediaSession() {
  if (!('mediaSession' in navigator) || !current.value) return;
  try {
    const song = current.value;
    navigator.mediaSession.metadata = new MediaMetadata({ title: song.title, artist: song.singer, album: song.album, artwork: song.cover ? [{ src: song.cover }] : [] });
    navigator.mediaSession.playbackState = playing.value ? 'playing' : 'paused';
  } catch { /* Older car browsers may only implement part of Media Session. */ }
}
watch([current, playing], updateMediaSession);
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
async function refreshAccount() {
  account.value = await api('account');
  knownLikes.value = {};
  void refreshMembership();
  loadRecent();
  restoreSession();
  if (tab.value === 'library') void loadLibrary();
  if (homeMode.value === 'daily') void loadRecommendations();
}
async function refreshMembership() {
  const generation = ++membershipGeneration;
  membership.value = { label: '正在查询会员…', level: null, isVip: null };
  if (!account.value.loggedIn) return;
  try {
    const result = await api('membership');
    if (!disposed && generation === membershipGeneration) membership.value = result;
  } catch {
    if (!disposed && generation === membershipGeneration) membership.value = { label: '会员状态暂不可用', level: null, isVip: null };
  }
}
function historyKey() { return 'qqmusic-recent-' + (account.value.account || 'guest'); }
function loadRecent() {
  recent.value = [];
  try {
    const data = JSON.parse(localStorage.getItem(historyKey()) || '[]');
    if (Array.isArray(data)) recent.value = data.filter(s => s && ['mid', 'title', 'singer', 'album', 'cover'].every(k => typeof s[k] === 'string') && Number.isFinite(s.duration)).slice(0, 100);
  } catch { /* History is optional when storage is unavailable. */ }
}
function recordPlayback() {
  playing.value = true;
  error.value = '';
  if (!current.value) return;
  recent.value = [current.value, ...recent.value.filter(s => s.mid !== current.value!.mid)].slice(0, 100);
  try { localStorage.setItem(historyKey(), JSON.stringify(recent.value)); } catch { /* Keep in memory. */ }
}
async function loadLibrary(append = false) {
  const generation = ++libraryGeneration;
  const next = append ? libraryPage.value + 1 : 1;
  if (!append) { librarySongs.value = []; playlists.value = []; libraryMore.value = false; }
  libraryError.value = '';
  libraryLoginRequired.value = !account.value.loggedIn;
  libraryBusy.value = false;
  if (libraryKind.value === 'recent' || !account.value.loggedIn) return;
  libraryBusy.value = true;
  try {
    const kind = selectedPlaylist.value ? 'playlist' : libraryKind.value;
    const result = await api(`library?kind=${kind}&page=${next}${selectedPlaylist.value ? '&id=' + encodeURIComponent(selectedPlaylist.value.id) : ''}`);
    if (disposed || generation !== libraryGeneration) return;
    libraryLoginRequired.value = result.loginRequired;
    librarySongs.value = append ? [...librarySongs.value, ...result.songs] : result.songs;
    playlists.value = append ? [...playlists.value, ...result.playlists] : result.playlists;
    if (libraryKind.value === 'songs' && !selectedPlaylist.value) for (const song of result.songs) knownLikes.value[song.mid] = true;
    libraryPage.value = next;
    libraryMore.value = result.more;
  } catch (e) { if (generation === libraryGeneration && !disposed) libraryError.value = message(e); }
  finally { if (generation === libraryGeneration) libraryBusy.value = false; }
}
function openPlaylist(playlist?: Playlist) { selectedPlaylist.value = playlist; void loadLibrary(); }
watch(libraryKind, () => { selectedPlaylist.value = undefined; void loadLibrary(); });
watch(tab, value => { if (value === 'library') void loadLibrary(); });
function openDaily() { homeMode.value = 'daily'; void loadRecommendations(); }
function stopRadio() {
  ++radioGeneration;
  radioActive.value = false;
  radioBusy.value = false;
  radioRequest = undefined;
  radioError.value = '';
  advancing.value = false;
}
function refillRadio(): Promise<void> {
  if (radioRequest) return radioRequest;
  const generation = radioGeneration;
  radioBusy.value = true;
  const task = (async () => {
    try {
      const fresh = await freshRadioBatch<Song>(async () => {
        if (disposed || generation !== radioGeneration) return [];
        const result = await api('recommend');
        if (result.loginRequired) throw new Error('请先登录 QQ 音乐，再播放猜你喜欢');
        return result.songs;
      }, queue.value.map(song => song.mid));
      if (disposed || generation !== radioGeneration) return;
      if (!fresh.length) throw new Error('暂时没有新的推荐，点击下一首重试');
      queue.value.push(...fresh);
      radioError.value = '';
    } catch (e) {
      if (!disposed && generation === radioGeneration) radioError.value = message(e);
    } finally {
      if (generation === radioGeneration) { radioBusy.value = false; radioRequest = undefined; }
    }
  })();
  radioRequest = task;
  return task;
}
async function startRadio() {
  if (!account.value.loggedIn) { accountOpen.value = true; return; }
  if (radioActive.value && current.value) { if (!playing.value) await toggle(); return; }
  if (radioBusy.value) return;
  stopRadio();
  radioActive.value = true;
  const generation = radioGeneration;
  ++playGeneration;
  audio.value?.pause();
  loadingTrack.value = false;
  current.value = undefined;
  queue.value = [];
  await refillRadio();
  if (disposed || generation !== radioGeneration) return;
  if (queue.value.length) await play(queue.value[0]);
}
async function loadRecommendations() {
  const generation = ++recommendGeneration;
  recommendations.value = [];
  recommendError.value = '';
  recommendLoginRequired.value = !account.value.loggedIn;
  recommendBusy.value = false;
  if (!account.value.loggedIn) return;
  recommendBusy.value = true;
  try {
    const result = await api('daily');
    if (disposed || generation !== recommendGeneration) return;
    recommendations.value = result.songs;
    recommendLoginRequired.value = result.loginRequired;
  } catch (e) {
    if (!disposed && generation === recommendGeneration) recommendError.value = message(e);
  } finally {
    if (generation === recommendGeneration) recommendBusy.value = false;
  }
}
async function search(loadMore = false) {
  if (busy.value || (!loadMore && !query.value.trim())) return;
  tab.value = 'search';
  busy.value = true;
  error.value = '';
  const keyword = loadMore ? searched.value : query.value.trim();
  if (!loadMore) rememberSearch(keyword);
  suggestions.value = [];
  if (searchKind.value !== 'song') { busy.value = false; openBrowse(searchKind.value + '-search', keyword, keyword + ' · 分类搜索'); return; }
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
  if (current.value?.mid !== song.mid) restoredPosition = 0;
  const generation = ++playGeneration;
  sources = [];
  sourceIndex = 0;
  if (fromList) { stopRadio(); queue.value = [...visibleSongs.value]; }
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
    if (eqContext?.state === 'suspended') await eqContext.resume();
    await audio.value.play();
    if (radioActive.value && generation === playGeneration && queue.value.length - queue.value.findIndex(s => s.mid === song.mid) <= 2) void refillRadio();
  } catch (e) {
    if (generation === playGeneration && !disposed && sourceIndex === 0) error.value = message(e);
  } finally { if (generation === playGeneration) loadingTrack.value = false; }
}
function mediaError() {
  if (eqEnabled.value && !eqBusy.value) { ElMessage.info('此音源不支持浏览器音效处理，已切回原声'); void setEq(false, true); return; }
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
async function step(delta: number, ended = false) {
  if (advancing.value || loadingTrack.value) return;
  const generation = radioGeneration;
  const trackGeneration = playGeneration;
  advancing.value = true;
  try {
    const currentIndex = queue.value.findIndex(s => s.mid === current.value?.mid);
    let i = radioActive.value ? currentIndex + delta : nextIndex(queue.value.length, currentIndex, delta, mode.value, ended);
    if (radioActive.value && delta > 0 && i >= queue.value.length) await refillRadio();
    if (disposed || generation !== radioGeneration || trackGeneration !== playGeneration) return;
    if (i >= 0 && i < queue.value.length) {
      await play(queue.value[i]);
      // Keep a bounded playback window for long drives.
      if (radioActive.value && i > 100) queue.value.splice(0, i - 50);
    }
  } finally { if (generation === radioGeneration) advancing.value = false; }
}
async function toggle() {
  if (!current.value || loadingTrack.value) return;
  if (playing.value) audio.value?.pause();
  else if (!audio.value?.getAttribute('src') || audio.value.error) await play(current.value);
  else try { if (eqContext?.state === 'suspended') await eqContext.resume(); await audio.value.play(); } catch { error.value = '播放被浏览器暂停，请再次点击播放'; }
}
function time(value: number) { return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`; }
function updateTime() {
  elapsed.value = audio.value?.currentTime || 0;
  const value = audio.value?.duration || 0;
  duration.value = Number.isFinite(value) ? value : 0;
  if (Date.now() - lastSnapshot > 5000) { lastSnapshot = Date.now(); saveSession(); }
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
    const result = await api('login', { provider: loginProvider.value });
    if (disposed || generation !== loginGeneration) return;
    qr.value = result.image;
    loginHint.value = `使用${scanApp.value}扫码，确认登录 QQ 音乐`;
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
        loginHint.value = state === 'CONF' ? '已扫码，请在手机上确认' : `等待${scanApp.value}扫码确认`;
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
    stopRadio();
    ++playGeneration;
    audio.value?.pause();
    audio.value?.removeAttribute('src');
    audio.value?.load();
    saveSession();
    current.value = undefined;
    restoredPosition = 0;
    loadingTrack.value = false;
    account.value = { loggedIn: false, account: '' };
    ++membershipGeneration;
    membership.value = { label: '未登录', level: null, isVip: null };
    selectedPlaylist.value = undefined;
    loadRecent();
    void loadLibrary();
    queue.value = [];
    if (homeMode.value === 'daily') void loadRecommendations();
    qr.value = '';
  } catch (e) { ElMessage.error(message(e)); }
}
onMounted(() => {
  refreshAccount().catch(e => { error.value = message(e); });
  if ('mediaSession' in navigator) {
    const handlers: Partial<Record<MediaSessionAction, MediaSessionActionHandler>> = {
      play: () => { if (!playing.value) void toggle(); }, pause: () => audio.value?.pause(),
      previoustrack: () => { void step(-1); }, nexttrack: () => { void step(1); },
      seekto: event => { if (audio.value && duration.value && event.seekTime !== undefined) audio.value.currentTime = Math.min(duration.value, Math.max(0, event.seekTime)); }
    };
    for (const [action, handler] of Object.entries(handlers)) try { navigator.mediaSession.setActionHandler(action as MediaSessionAction, handler!); } catch {}
  }
});
onBeforeUnmount(() => { saveSession(); if (eqContext) void eqContext.close(); if ('mediaSession' in navigator) { for (const action of ['play', 'pause', 'previoustrack', 'nexttrack', 'seekto'] as MediaSessionAction[]) try { navigator.mediaSession.setActionHandler(action, null); } catch {} } disposed = true; clearTimeout(suggestionTimer); ++suggestionGeneration; ++commentsGeneration; stopPoll(); stopRadio(); ++playGeneration; audio.value?.pause(); audio.value?.removeAttribute('src'); audio.value?.load(); });
</script>

<template>
  <section class="music-page">
    <header class="music-header">
      <div class="brand"><img class="qqmusic-logo" src="/icon/QQMUSIC_LOGO.ico" alt="" /><strong>QQ 音乐</strong></div>
      <el-radio-group v-model="tab" class="music-navigation" aria-label="音乐页面"><el-radio-button value="home">首页</el-radio-button><el-radio-button value="library">我的音乐</el-radio-button></el-radio-group>
      <el-select v-model="quality" aria-label="播放音质" title="播放音质，下次播放生效" style="width: 132px; margin-left: auto" @change="changeQuality">
        <el-option v-for="option in qualityOptions" :key="option.value" :label="option.label" :value="option.value" :disabled="['lossless', 'premium', 'master'].includes(option.value) && !audio?.canPlayType('audio/flac')" />
      </el-select>
      <el-button round class="account-entry" @click="accountOpen = true"><span>{{ account.loggedIn ? membership.label : '登录 QQ 音乐' }}<small v-if="account.loggedIn && membership.level"> · LV{{ membership.level }}</small></span></el-button>
      <el-button circle :icon="Search" aria-label="搜索音乐" title="搜索音乐" :type="tab === 'search' ? 'primary' : 'default'" @click="openSearch" />
    </header>
    <form v-if="tab === 'search'" class="search" @submit.prevent="search()">
      <el-input ref="searchInput" v-model="query" :prefix-icon="Search" placeholder="搜索歌曲、歌手或专辑" maxlength="100" clearable aria-label="搜索歌曲" />
      <el-button type="primary" native-type="submit" :loading="busy">搜索</el-button>
    </form>
    <div v-if="tab === 'search'" class="search-tools"><el-radio-group v-model="searchKind" size="small"><el-radio-button v-for="entry in [{id:'song',name:'歌曲'},{id:'singer',name:'歌手'},{id:'album',name:'专辑'},{id:'playlist',name:'歌单'},{id:'mv',name:'MV'},{id:'audio',name:'有声'}]" :key="entry.id" :value="entry.id">{{ entry.name }}</el-radio-button></el-radio-group><div class="search-words"><el-button v-for="word in (suggestions.length ? suggestions : searchHistory)" :key="word" size="small" text @click="query = word; search()">{{ word }}</el-button><el-button v-if="!suggestions.length && searchHistory.length" size="small" text @click="clearSearchHistory">清空历史</el-button></div></div>
    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />
    <div class="results">
      <template v-if="tab === 'home'">
        <template v-if="homeMode === 'cards'">
          <div class="home-intro"><el-button class="explore-top" @click="openBrowse('singers', '', '歌手')">歌手</el-button><el-button class="explore-top" @click="openBrowse('tops', '', '音乐排行榜')">排行榜</el-button><h2>让音乐陪你出发</h2><p>今天的好歌，和下一首惊喜</p></div>
          <div class="discovery-cards">
            <button class="discovery-card daily-card" @click="openDaily">
              <span class="calendar-art"><small>每日</small><b>{{ today }}</b></span>
              <span class="card-copy"><strong>每日推荐</strong><span>为你准备的今日歌单</span></span>
              <span class="card-action">查看歌曲 <el-icon><ArrowRight /></el-icon></span>
            </button>
            <button class="discovery-card radio-card" :class="{ 'is-playing': radioActive && playing }" :disabled="radioBusy && !current" @click="startRadio">
              <span class="record-art"><span></span></span>
              <span class="card-copy"><strong>猜你喜欢</strong><span>{{ radioActive && current ? current.title : '一键开听，好歌接着放' }}</span></span>
              <span class="card-action"><el-icon><VideoPlay /></el-icon>{{ radioBusy && !current ? '正在为你选歌…' : radioActive && playing ? '正在播放' : '立即播放' }}</span>
            </button>
          </div>
          <div v-if="radioActive" class="radio-status" role="status"><span class="radio-dot"></span><span>{{ radioBusy ? '正在寻找下一批好歌…' : '猜你喜欢 · 连续播放' }}</span><el-button v-if="current" text @click="step(1)" :loading="advancing">下一首</el-button></div>
          <QQMusicPlaylistShelf v-for="theme in ['华语', '流行', '摇滚', '古典', '轻音乐', '驾车']" :key="theme" :theme="theme" :api="api" @open="item => openBrowse('playlist', item.id, item.title)" />
        </template>
        <template v-else>
          <div class="recommend-header"><el-button :icon="ArrowLeft" @click="homeMode = 'cards'">返回首页</el-button><strong>每日推荐<span v-if="recommendations.length" class="muted"> · {{ recommendations.length }} 首</span></strong><div><el-button v-if="recommendations.length" :icon="VideoPlay" @click="play(recommendations[0], true)">播放全部</el-button><el-button v-if="account.loggedIn && !recommendLoginRequired" :loading="recommendBusy" @click="loadRecommendations">刷新</el-button></div></div>
          <div v-if="recommendLoginRequired" class="empty"><p>登录 QQ 音乐，发现为你推荐的歌曲</p><el-button type="primary" @click="accountOpen = true">QQ / 微信登录</el-button></div>
          <p v-else-if="recommendBusy" class="empty" role="status">正在加载推荐歌曲…</p>
          <el-alert v-else-if="recommendError" :title="recommendError" type="warning" :closable="false" show-icon />
          <p v-else-if="!recommendations.length" class="empty">暂时没有推荐歌曲，请刷新重试</p>
        </template>
      </template>
      <template v-else-if="tab === 'library'">
        <el-radio-group v-model="libraryKind" class="library-tabs" aria-label="我的音乐分类">
          <el-radio-button value="songs">收藏歌曲</el-radio-button><el-radio-button value="playlists">收藏歌单</el-radio-button><el-radio-button value="created">自建歌单</el-radio-button><el-radio-button value="recent">最近播放</el-radio-button>
        </el-radio-group>
        <el-button v-if="libraryKind === 'created'" :loading="collectionBusy" @click="collection('create')">新建歌单</el-button>
        <p v-if="libraryKind === 'recent'" class="muted">本机最近播放 · 最多 100 首，不包含手机端播放记录</p>
        <div v-else class="recommend-header"><span><el-button v-if="selectedPlaylist" :icon="ArrowLeft" @click="openPlaylist()">返回歌单</el-button> {{ selectedPlaylist?.title }}</span><el-button :loading="libraryBusy" @click="loadLibrary()">刷新</el-button></div>
        <div v-if="libraryKind !== 'recent' && libraryLoginRequired" class="empty"><p>登录后查看你的收藏和歌单</p><el-button type="primary" @click="accountOpen = true">QQ / 微信登录</el-button></div>
        <el-alert v-else-if="libraryError" :title="libraryError" type="warning" :closable="false" show-icon />
        <p v-else-if="libraryBusy && !visibleSongs.length && !playlists.length" class="empty" role="status">正在加载…</p>
        <p v-else-if="!libraryBusy && !visibleSongs.length && !playlists.length" class="empty">{{ libraryKind === 'recent' ? '还没有本机播放记录，播放歌曲后会显示在这里' : '这里暂时没有内容' }}</p>
        <button v-for="playlist in playlists" :key="playlist.id" class="song" @click="openPlaylist(playlist)"><img v-if="playlist.cover" :src="playlist.cover" alt="" loading="lazy" /><span class="song-text"><strong>{{ playlist.title }}</strong><span>{{ playlist.count }} 首歌曲</span></span><el-icon><ArrowRight /></el-icon></button>
      </template>
      <template v-else>
        <p v-if="!searched && !busy" class="empty">搜索你喜欢的歌曲、歌手或专辑</p>
        <p v-else-if="!songs.length && !busy" class="empty">没有找到相关歌曲，试试其他关键词</p>
      </template>
      <div v-for="song in visibleSongs" :key="song.mid" class="song-row"><button class="song" :class="{ active: current?.mid === song.mid }" @click="play(song, true)">
        <img :src="song.cover" alt="" loading="lazy" />
        <span class="song-text"><strong>{{ song.title }}</strong><span>{{ song.singer }} · {{ song.album }}</span></span>
        <span class="song-badges"><span class="quality-badge" :class="song.maxQuality" title="歌曲音源的最高音质；实际播放取决于账号权益、所选音质及播放器支持。可选择标准、高品质、FLAC 无损、臻品音质与母带，受账号和浏览器支持限制。">{{ maxQualityLabel(song) }}</span><span class="access-badge" :class="song.access" :title="song.access === 'standard' ? '未标记会员播放限制，高音质和实际可播性以账号权益为准' : '以 QQ 音乐当前账号实际播放权限为准'">{{ accessLabel(song) }}</span></span>
        <span class="muted">{{ time(song.duration) }}</span><el-icon><VideoPlay /></el-icon>
      </button><el-dropdown trigger="click" @command="(command: string) => songAction(command, song)"><el-button circle aria-label="歌曲操作">···</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item :command="knownLikes[song.mid] ? 'unlike' : 'like'" :disabled="collectionBusy">{{ knownLikes[song.mid] ? '取消红心收藏' : '红心收藏' }}</el-dropdown-item><el-dropdown-item v-if="knownLikes[song.mid] === undefined" command="unlike">取消已有收藏</el-dropdown-item><el-dropdown-item command="queue">加入播放队列</el-dropdown-item><el-dropdown-item command="add">添加到歌单</el-dropdown-item><el-dropdown-item command="comments">热门评论</el-dropdown-item><el-dropdown-item v-if="song.albumMid" command="album">查看专辑</el-dropdown-item><el-dropdown-item v-for="singer in song.singers" :key="singer.mid" :command="'singer:' + singer.mid">歌手 · {{ singer.name }}</el-dropdown-item><el-dropdown-item v-if="selectedPlaylist && libraryKind === 'created'" command="remove">从此歌单移除</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div>
      <el-button v-if="tab === 'search' && more" class="load-more" :loading="busy" @click="search(true)">加载更多</el-button>
      <el-button v-if="tab === 'library' && libraryMore" class="load-more" :loading="libraryBusy" @click="loadLibrary(true)">加载更多</el-button>
    </div>
    <el-alert v-if="radioActive && radioError" :title="radioError" type="warning" :closable="false" show-icon />
    <footer class="player">
      <button class="now-playing" :disabled="!current" aria-label="打开正在播放页面" @click="nowPlayingOpen = true"><img v-if="current" :src="current.cover" alt="" /><div class="song-text"><strong>{{ current?.title || '还没有播放歌曲' }}</strong><span>{{ loadingTrack ? '正在加载…' : current?.singer || '从搜索结果中选择歌曲' }}</span></div></button>
      <div class="play-controls">
        <el-button circle :disabled="radioActive" :aria-label="radioActive ? '猜你喜欢连续推荐' : modeLabels[mode] + '，点击切换'" :title="radioActive ? '猜你喜欢保持连续推荐模式' : modeLabels[mode] + '，点击切换'" @click="cycleMode"><QQMusicControlIcon :kind="mode" /></el-button>
        <el-button circle :class="{ 'eq-active': eqEnabled }" :aria-label="eqEnabled ? '均衡器已开启，调整音效' : '打开均衡器'" :title="eqEnabled ? '均衡器 · ' + eqPresets[eqPreset].name : '均衡器'" @click="eqOpen = true"><QQMusicControlIcon kind="equalizer" /></el-button>
        <el-button circle aria-label="播放队列" title="播放队列" @click="queueOpen = true">☷</el-button>
        <el-button v-if="current" circle :loading="collectionBusy" :title="knownLikes[current.mid] ? '取消红心收藏' : '红心收藏'" :aria-label="knownLikes[current.mid] ? '取消红心收藏' : '红心收藏'" @click="collection(knownLikes[current.mid] ? 'unlike' : 'like', current)">{{ knownLikes[current.mid] ? '♥' : '♡' }}</el-button>
        <el-button circle :icon="ArrowLeft" aria-label="上一首" :disabled="!current || (!radioActive && mode === 'order' && queue.findIndex(s => s.mid === current?.mid) <= 0)" @click="step(-1)" />
        <el-button circle type="primary" :icon="playing ? VideoPause : VideoPlay" :aria-label="playing ? '暂停' : '播放'" :loading="loadingTrack" :disabled="!current" @click="toggle" />
        <el-button circle :icon="ArrowRight" aria-label="下一首" :disabled="!current || advancing || loadingTrack || (!radioActive && mode === 'order' && queue.findIndex(s => s.mid === current?.mid) >= queue.length - 1)" @click="step(1)" />
      </div>
      <div class="seek"><span>{{ time(elapsed) }}</span><input type="range" min="0" :max="duration || 1" step="0.1" :value="elapsed" :disabled="!duration || loadingTrack" aria-label="播放进度" @input="seek" /><span>{{ time(duration) }}</span></div>
    </footer>
    <QQMusicNowPlaying v-if="nowPlayingOpen && current" :song="current" :mode="mode" :mode-label="modeLabels[mode]" :radio-active="radioActive" :eq-enabled="eqEnabled" @mode="cycleMode" @equalizer="eqOpen = true" :liked="!!knownLikes[current.mid]" :collection-busy="collectionBusy" :load-word-lyrics="() => api('word-lyrics?mid=' + encodeURIComponent(current!.mid))" @queue="queueOpen = true" @like="collection(knownLikes[current.mid] ? 'unlike' : 'like', current)" @comments="openComments(current)" @add="openAdd(current)" :playing="playing" :elapsed="elapsed" :duration="duration" :loading="loadingTrack" :previous-disabled="mode === 'order' && queue.findIndex(s => s.mid === current?.mid) <= 0" :next-disabled="advancing || loadingTrack || (!radioActive && mode === 'order' && queue.findIndex(s => s.mid === current?.mid) >= queue.length - 1)" :error="error" :load-lyrics="() => api('lyrics?mid=' + encodeURIComponent(current!.mid))" @close="nowPlayingOpen = false" @toggle="toggle" @previous="step(-1)" @next="step(1)" @seek="value => { if (audio && duration) audio.currentTime = Math.min(duration, value); }" />
    <el-dialog v-model="eqOpen" title="音效 · 均衡器与空间感" width="min(440px, 94vw)" align-center><div class="eq-settings"><el-switch :model-value="eqEnabled" :loading="eqBusy" active-text="开启音效" @change="(value: string | number | boolean) => setEq(!!value)" /><el-select v-if="eqEnabled" v-model="eqPreset" aria-label="均衡器音效" @change="applyEq"><el-option v-for="(preset, id) in eqPresets" :key="id" :value="id" :label="preset.name" /></el-select></div><div class="spatial-settings"><el-switch v-model="spatialEnabled" :disabled="!eqEnabled || eqBusy" active-text="空间音效" @change="applySpatial" /><template v-if="spatialEnabled && eqEnabled"><el-tag>{{ spatialChannels === 8 ? '7.1 合成环绕' : spatialChannels === 6 ? '5.1 合成环绕' : '双声道混响' }}</el-tag><el-switch v-model="forceStereo" active-text="兼容模式（强制双声道）" @change="applySpatial" /><el-radio-group v-model="spatialRoom" @change="updateRoom"><el-radio-button value="room">小房间</el-radio-button><el-radio-button value="hall">音乐厅</el-radio-button></el-radio-group><label>空间强度 {{ spatialAmount }}%<el-slider v-model="spatialAmount" :min="0" :max="50" aria-label="空间混响强度" @input="applySpatial" /></label></template><p>自动尝试 7.1 → 5.1 → 双声道；音效失败时恢复原声。当前为普通歌曲合成环绕，不是原生全景声解码。若车机声场异常，可开启兼容模式。</p></div></el-dialog>
    <el-dialog v-model="queueOpen" title="播放队列" width="min(620px, 94vw)" align-center><p v-if="radioActive">猜你喜欢连续推荐模式</p><div class="queue-list"><div v-for="(song, index) in queue" :key="song.mid + index" class="queue-row"><el-button text :type="song.mid === current?.mid ? 'primary' : 'default'" @click="play(song)">{{ index + 1 }}. {{ song.title }}</el-button><el-button text :disabled="index === 0" @click="moveQueue(index)">上移</el-button><el-button text @click="removeQueue(index)">移除</el-button></div><p v-if="!queue.length">队列为空</p></div></el-dialog>
    <el-dialog :model-value="!!browseItem" title="发现音乐" width="min(900px, 94vw)" align-center destroy-on-close @update:model-value="(value: boolean) => { if (!value) browseItem = undefined; }"><QQMusicBrowse v-if="browseItem" :initial="browseItem" :api="api" @play="playBrowse" @video="audio?.pause()" /></el-dialog>
    <el-dialog :model-value="!!addSong" title="添加到我的歌单" width="min(500px, 94vw)" align-center @update:model-value="(value: boolean) => { if (!value) addSong = undefined; }"><el-button :loading="collectionBusy" @click="collection('create')">新建歌单</el-button><p v-if="!ownedPlaylists.length">暂无自建歌单</p><el-button v-for="playlist in ownedPlaylists" :key="playlist.id" class="playlist-choice" :disabled="collectionBusy" @click="collection('add', addSong, playlist.id)">{{ playlist.title }}</el-button></el-dialog>
    <el-dialog v-model="commentsOpen" :title="(commentsSong?.title || '') + ' · 热门评论'" width="min(650px, 94vw)" align-center @closed="++commentsGeneration"><el-alert v-if="commentsError" :title="commentsError" type="warning" /><article v-for="comment in comments" :key="comment.id" class="comment"><strong>{{ comment.name }}</strong><p>{{ comment.text }}</p><small>赞 {{ comment.likes }}</small></article><p v-if="!comments.length && !commentsBusy && !commentsError">暂无评论</p><el-button v-if="commentsMore || commentsError || commentsBusy" :loading="commentsBusy" @click="loadComments">{{ commentsError ? '重试' : '加载更多' }}</el-button></el-dialog>
    <audio :key="audioKey" :crossorigin="eqEnabled ? 'anonymous' : undefined" ref="audio" preload="metadata" @playing="recordPlayback" @pause="playing = false" @timeupdate="updateTime" @durationchange="updateTime" @loadedmetadata="loadedMetadata" @ended="playing = false; step(1, true)" @error="mediaError" />
    <el-dialog v-model="accountOpen" title="QQ 音乐账号" width="min(400px, 90vw)" align-center @close="stopPoll(); qrBusy = false; qr = ''; loginHint = `使用${scanApp}扫码，确认登录 QQ 音乐`">
      <div class="account-panel" v-if="account.loggedIn"><p>已登录账号 {{ account.account }}</p><p class="membership-label">{{ membership.label }}<span v-if="membership.level"> · LV{{ membership.level }}</span></p><el-button @click="refreshMembership">刷新会员信息</el-button><el-button @click="logout">退出 QQ 音乐登录</el-button></div>
      <div class="account-panel" v-else>
        <el-radio-group v-model="loginProvider" class="login-providers" aria-label="登录方式" :disabled="qrBusy" @change="startLogin">
          <el-radio-button value="qq">QQ 登录</el-radio-button>
          <el-radio-button value="wx">微信登录</el-radio-button>
        </el-radio-group>
        <img v-if="qr" class="qr" :src="qr" :alt="`${scanApp}扫码登录 QQ 音乐`" />
        <p>{{ loginHint }}</p>
        <el-button type="primary" :loading="qrBusy" @click="startLogin">{{ qr ? '刷新二维码' : '获取登录二维码' }}</el-button>
      </div>
      <p class="account-note">支持 QQ、微信扫码授权，无需输入密码。请选择你平时登录 QQ 音乐的方式；账号及会员权益可能不同。登录仅用于当前浏览器。</p>
    </el-dialog>
  </section>
</template>

<style scoped>
.spatial-settings{display:flex;flex-direction:column;gap:16px;margin-top:20px;border-top:1px solid var(--color-border);padding-top:16px}.spatial-settings label{font-size:13px}.spatial-settings p{font-size:12px;line-height:1.7;color:var(--color-text-soft);margin:0}
.play-controls .eq-active{color:#159766;border-color:#8dd6b9;background:#eaf8f1}@media(max-width:480px){.player .now-playing,.player .play-controls{grid-column:1/-1}.player .play-controls{justify-content:flex-end}}
.eq-settings{display:flex;align-items:center;gap:12px;margin-top:12px}.eq-settings .el-select{width:150px}
.song-row{display:flex;gap:6px;align-items:center}.song-row>.song{min-width:0;flex:1}.explore-top{float:right}.search-words{display:flex;flex-wrap:wrap;gap:3px}.queue-list{max-height:50vh;overflow:auto;margin-top:14px}.queue-row{display:flex;align-items:center}.queue-row>.el-button:first-child{flex:1;min-width:0;justify-content:flex-start;overflow:hidden}.playlist-choice{display:block;margin:10px 0;width:100%}.comment{border-bottom:1px solid var(--color-border);padding:14px 0}.comment p{white-space:pre-wrap;line-height:1.7}.comment small{color:var(--color-text-soft)}
.music-header{flex-wrap:wrap;gap:10px}.music-header .brand{flex-shrink:0;white-space:nowrap}.music-navigation{flex-shrink:0}.music-header .account-entry{margin-left:0}@media(max-width:800px){.music-header{gap:8px}.music-header .brand{gap:7px;font-size:18px}.music-navigation :deep(.el-radio-button__inner){padding:8px 10px}}
.qqmusic-logo{width:30px;height:30px;object-fit:contain;flex-shrink:0}
.song-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px;max-width:210px;flex-shrink:0}.quality-badge{font-size:11px;white-space:nowrap;border:1px solid #b7d9cd;border-radius:5px;padding:3px 6px;color:#28745c;background:#eef9f4}.quality-badge.master,.quality-badge.premium{color:#765293;border-color:#d7c4e5;background:#f6f0fc}@media(max-width:650px){.song-badges{max-width:112px}}
.account-entry{max-width:190px}.account-entry span{overflow:hidden;text-overflow:ellipsis}.access-badge{flex-shrink:0;font-size:11px;border-radius:5px;padding:3px 6px;background:var(--color-surface);color:var(--color-text-soft);border:1px solid var(--color-border)}.access-badge.vip{color:#956918;background:#fff4d9;border-color:#edd5a0}.access-badge.purchase,.access-badge.paid{color:#ac5744;background:#fff1eb;border-color:#efcfbf}.membership-label{font-weight:600}
.home-intro{margin:12px 0 20px}.home-intro h2{font-size:24px;font-weight:650;margin:0 0 8px}.home-intro p{margin:0;color:var(--color-text-soft);font-size:14px}
.discovery-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;padding:2px 2px 16px}
.discovery-card{position:relative;min-height:238px;padding:24px;border:0;border-radius:24px;text-align:left;overflow:hidden;cursor:pointer;color:#fff;display:flex;flex-direction:column;align-items:flex-start;isolation:isolate;box-shadow:0 8px 22px #12352b12;transition:transform .18s,box-shadow .18s}
.discovery-card:hover{transform:translateY(-2px);box-shadow:0 12px 26px #12352b24}.discovery-card:focus-visible{outline:3px solid #409eff;outline-offset:3px}.discovery-card:disabled{cursor:wait}.daily-card{background:linear-gradient(130deg,#276b58,#163f38)}.radio-card{background:linear-gradient(130deg,#74538a,#34375c)}
.calendar-art{width:70px;height:76px;background:#fffef3;color:#265749;border-radius:13px;display:flex;align-items:center;flex-direction:column;box-shadow:6px 6px 0 #ffffff18;transform:rotate(-7deg);margin-bottom:22px}.calendar-art small{width:100%;text-align:center;padding:5px 0;border-bottom:1px solid #dce7df;font-size:11px;letter-spacing:3px}.calendar-art b{font-size:35px;line-height:44px}
.record-art{position:absolute;width:185px;height:185px;border-radius:50%;right:-38px;top:-28px;background:repeating-radial-gradient(circle,#25253d 0 4px,#38364e 5px 6px);box-shadow:0 0 0 14px #ffffff07;z-index:-1}.record-art span{position:absolute;inset:62px;border-radius:50%;background:radial-gradient(circle,#31304b 0 5px,#dab2bc 6px 100%)}.radio-card .card-copy{margin-top:98px}
.card-copy{display:flex;flex-direction:column;gap:7px;max-width:100%;margin-top:auto}.card-copy strong{font-size:24px;letter-spacing:1px}.card-copy>span{font-size:13px;color:#ffffffe0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}.card-action{display:flex;gap:6px;align-items:center;margin-top:20px;font-size:13px;color:#ffffffeb}.radio-card .card-action{background:#ffffff20;border:1px solid #ffffff20;border-radius:22px;padding:8px 14px;margin-top:14px}.radio-status{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--color-text-soft)}.radio-dot{width:7px;height:7px;border-radius:50%;background:#19b978}.radio-status .el-button{margin-left:auto}
@media(max-height:650px){.home-intro{margin:4px 0 12px}.home-intro h2{font-size:20px}.discovery-card{min-height:192px;padding:18px}.calendar-art{width:56px;height:64px;margin-bottom:12px}.calendar-art b{font-size:28px;line-height:34px}.radio-card .card-copy{margin-top:76px}.card-copy strong{font-size:21px}}
@media(max-width:480px){.discovery-cards{gap:10px}.discovery-card{padding:16px;border-radius:18px}.card-copy strong{font-size:20px}.card-copy>span{font-size:12px}.record-art{right:-85px}}
.library-tabs{display:flex;flex-wrap:wrap;margin-bottom:12px}
.recommend-header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.login-providers{display:flex;justify-content:center;margin-bottom:16px}
.music-page{position:relative;height:100%;min-height:0;display:flex;flex-direction:column;gap:12px;padding:16px;box-sizing:border-box;color:var(--color-text)}
.music-header,.brand,.search,.song,.now-playing,.play-controls,.seek{display:flex;align-items:center;gap:12px}
.music-header{justify-content:space-between}.brand{font-size:20px}.brand .el-icon{color:#19b978}.search .el-input{flex:1}.results{flex:1;min-height:0;overflow:auto}.empty{text-align:center;padding:36px 8px;color:var(--color-text-soft)}.empty h2{margin:14px 0 6px}.empty p{font-size:14px}.muted{color:var(--color-text-soft);font-size:12px}.song{width:100%;padding:10px 8px;text-align:left;border:0;border-bottom:1px solid var(--color-border);background:transparent;color:inherit;cursor:pointer;border-radius:10px}.song:hover,.song.active{background:rgba(25,185,120,.09)}.song img,.now-playing img{width:44px;height:44px;object-fit:cover;border-radius:8px}.song-text{display:flex;flex-direction:column;gap:4px;min-width:0;flex:1}.song-text strong,.song-text span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.song-text strong{font-size:15px;font-weight:500}.song-text span{font-size:12px;color:var(--color-text-soft)}.song>.el-icon{font-size:24px;color:#19b978}.load-more{display:block;margin:12px auto}.player{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 16px;border-top:1px solid var(--color-border);padding-top:12px}.now-playing{min-width:0;text-align:left;border:0;background:transparent;color:inherit;padding:0;cursor:pointer}.now-playing:disabled{cursor:default}.now-playing:focus-visible{outline:2px solid #19b978;outline-offset:4px;border-radius:8px}.play-controls{gap:8px}.play-controls .el-button{margin:0;width:42px;height:42px}.seek{grid-column:1/-1;gap:10px;font-size:12px;font-variant-numeric:tabular-nums}.seek input{flex:1;min-width:0;accent-color:#19b978;height:28px;cursor:pointer}.account-panel{text-align:center}.qr{width:190px;height:190px;image-rendering:pixelated;background:white;padding:10px}.account-note{font-size:12px;color:var(--color-text-soft);line-height:1.8;margin-top:20px}@media(max-width:600px){.music-page{padding:10px;gap:10px}.brand{font-size:18px}.song{gap:8px}.player{gap:8px}.play-controls{gap:4px}.play-controls .el-button{width:36px;height:36px}}
</style>
