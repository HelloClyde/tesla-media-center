<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { getWqzbStream } from '@/functions/wqzbStream';
import { useAudioChannel } from '@/functions/useAudioChannel';

interface Channel { id: number; channel_name: string }
interface Room {
  chatroom_id: number;
  room_title: string;
  user_nickname?: string;
  screenshot_url?: string;
  match_screenshot_url?: string;
  heat_number?: number;
  match_id?: number;
  sport_id?: number;
  status?: number;
}
interface Plate { id: number; name: string; is_page?: number; rooms: Room[] }
interface ApiResult<T> { code: number; message?: string; data: T }

const API = 'https://apc.z2f3v4o2s1u3z5k5i1.cc';
const channels = ref<Channel[]>([]);
const currentChannel = ref(53);
const plates = ref<Plate[]>([]);
const loading = ref(false);
const loadingMore = ref<number | null>(null);
const error = ref('');
const nextPages = ref<Record<number, number>>({});
const exhausted = ref<Record<number, boolean>>({});
const selectedRoom = ref<Room | null>(null);
const playbackError = ref('');
const playbackBusy = ref(false);
const playing = ref(false);
const appRoot = ref<HTMLElement | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const loadingLayer = ref<HTMLDivElement | null>(null);
const audioBlocked = ref(false);
const { channelAudio, startAudioChannel } = useAudioChannel();
let controller: AbortController | undefined;
let generation = 0;
let playbackGeneration = 0;
let playbackController: AbortController | undefined;
let player: any = undefined;
let savedListScrollTop = 0;

const roomCount = computed(() => plates.value.reduce((count, plate) => count + plate.rooms.length, 0));

async function getData<T>(path: string, params: Record<string, number>, signal?: AbortSignal): Promise<T> {
  const url = new URL(path, API);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`请求失败 (${response.status})`);
  const result = await response.json() as ApiResult<T>;
  if (result.code !== 200) throw new Error(result.message || '玩球直播暂时不可用');
  return result.data;
}

async function loadChannel(id: number) {
  ++generation;
  const ticket = generation;
  controller?.abort();
  controller = new AbortController();
  currentChannel.value = id;
  plates.value = [];
  nextPages.value = {};
  exhausted.value = {};
  error.value = '';
  loading.value = true;
  try {
    const data = await getData<Plate[]>('/v1/plate/getlist', { channel_id: id, page: 0, page_size: 18 }, controller.signal);
    if (ticket !== generation) return;
    plates.value = data.filter(plate => plate && Array.isArray(plate.rooms));
    for (const plate of plates.value) nextPages.value[plate.id] = 1;
  } catch (cause) {
    if (ticket === generation && !(cause instanceof DOMException && cause.name === 'AbortError'))
      error.value = cause instanceof Error ? cause.message : '加载直播间失败';
  } finally {
    if (ticket === generation) loading.value = false;
  }
}

async function loadMore(plate: Plate) {
  if (loadingMore.value !== null || exhausted.value[plate.id]) return;
  const page = nextPages.value[plate.id] || 1;
  loadingMore.value = plate.id;
  try {
    const rooms = await getData<Room[]>('/v1/plate/pagelist', { plate_id: plate.id, page, page_size: 18 });
    if (!plates.value.includes(plate)) return;
    const seen = new Set(plate.rooms.map(room => room.chatroom_id));
    plate.rooms.push(...rooms.filter(room => !seen.has(room.chatroom_id)));
    nextPages.value[plate.id] = page + 1;
    exhausted.value[plate.id] = rooms.length < 18;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载更多失败';
  } finally {
    loadingMore.value = null;
  }
}

function cover(room: Room) { return room.screenshot_url || room.match_screenshot_url || ''; }
function heat(value?: number) { return value ? value >= 10000 ? `${(value / 10000).toFixed(1)}万` : String(value) : ''; }

function stopPlayback() {
  ++playbackGeneration;
  playbackController?.abort();
  playbackController = undefined;
  player?.destroy(); player = undefined;
  channelAudio.value?.pause();
  audioBlocked.value = false;
  playing.value = false;
}

function closeRoom() {
  stopPlayback();
  selectedRoom.value = null;
  playbackError.value = '';
  playbackBusy.value = false;
  void nextTick(() => {
    if (!selectedRoom.value && appRoot.value) appRoot.value.scrollTop = savedListScrollTop;
  });
}

async function openRoom(room: Room) {
  if (!selectedRoom.value) savedListScrollTop = appRoot.value?.scrollTop ?? 0;
  stopPlayback();
  selectedRoom.value = room;
  // The player is positioned at the top of this scroll container. A room
  // selected farther down the grid must first bring that layer into view.
  if (appRoot.value) appRoot.value.scrollTop = 0;
  void nextTick(() => {
    if (selectedRoom.value === room && appRoot.value) appRoot.value.scrollTop = 0;
  });
  playbackError.value = '';
  playbackBusy.value = true;
  playbackController = new AbortController();
  const ticket = playbackGeneration;
  try {
    const url = await getWqzbStream(room.chatroom_id, playbackController.signal);
    if (ticket !== playbackGeneration) return;
    await nextTick();
    if (ticket !== playbackGeneration || !canvas.value) return;
    const box = canvas.value.parentElement?.getBoundingClientRect();
    if (box) {
      canvas.value.width = Math.max(1, Math.round(box.width));
      canvas.value.height = Math.max(1, Math.round(box.height));
    }
    startAudioChannel();
    player = new Player();
    player.setLoadingDiv(loadingLayer.value);
    player.setAudioBlockedCallback?.((blocked: boolean) => {
      if (ticket === playbackGeneration) audioBlocked.value = blocked;
    });
    const state = player.play(url, canvas.value, (event: { error?: number; message?: string }) => {
      if (ticket === playbackGeneration && event.error && event.error !== 1) {
        playbackError.value = event.message || '直播播放中断';
        playing.value = false;
      }
    }, 256 * 1024, true);
    if (state?.e) throw new Error(state.m || '软解播放器启动失败');
    playing.value = true;
  } catch (cause) {
    if (ticket === playbackGeneration && !(cause instanceof DOMException && cause.name === 'AbortError'))
      playbackError.value = cause instanceof Error ? cause.message : '直播播放失败';
  } finally {
    if (ticket === playbackGeneration) playbackBusy.value = false;
  }
}

function togglePlayback() {
  if (!selectedRoom.value || playbackBusy.value) return;
  if (playing.value) {
    player?.pause();
    channelAudio.value?.pause();
    playing.value = false;
  } else void openRoom(selectedRoom.value);
}

function resumeAudio() {
  startAudioChannel();
  void player?.resumeBlockedAudio?.().then((resumed: boolean) => {
    if (!resumed) playbackError.value = '请再次点击以启动声音';
  });
}

async function initialize() {
  try {
    channels.value = await getData<Channel[]>('/v1/channel/getlist', {});
    const first = channels.value.find(channel => channel.id === 53) || channels.value[0];
    if (first) await loadChannel(first.id);
    else error.value = '暂无直播频道';
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '加载频道失败';
  }
}

onMounted(initialize);
onBeforeUnmount(() => { ++generation; controller?.abort(); stopPlayback(); });
</script>

<template>
  <main ref="appRoot" class="wqzb-app" :class="{ 'player-open': selectedRoom }">
    <header class="wqzb-header">
      <div>
        <div class="wqzb-eyebrow">LIVE SPORTS</div>
        <h1>玩球直播</h1>
        <p>选择直播间，即可观看体育直播</p>
      </div>
      <button class="wqzb-refresh" type="button" @click="loadChannel(currentChannel)">刷新直播间</button>
    </header>

    <nav v-if="channels.length" class="wqzb-channels" aria-label="直播频道">
      <button v-for="channel in channels" :key="channel.id" type="button"
        :class="{ active: channel.id === currentChannel }" @click="loadChannel(channel.id)">
        {{ channel.channel_name }}
      </button>
    </nav>

    <div v-if="error" class="wqzb-error" role="alert">
      <span>{{ error }}</span>
      <button type="button" @click="initialize">重试</button>
    </div>
    <div v-if="loading" class="wqzb-state">正在加载直播间…</div>
    <div v-else-if="!error && !roomCount" class="wqzb-state">当前频道暂无直播间</div>

    <section v-for="plate in plates.filter(item => item.rooms.length)" :key="plate.id" class="wqzb-section">
      <div class="wqzb-section-head">
        <h2>{{ plate.name }}</h2>
        <span>{{ plate.rooms.length }} 个直播间</span>
      </div>
      <div class="wqzb-grid">
        <button v-for="room in plate.rooms" :key="room.chatroom_id" class="wqzb-card" type="button"
          @click="openRoom(room)"
          :aria-label="`观看 ${room.room_title}`">
          <div class="wqzb-cover">
            <img v-if="cover(room)" :src="cover(room)" alt="" loading="lazy" referrerpolicy="no-referrer" />
            <span v-else class="wqzb-cover-placeholder">▶</span>
            <span class="wqzb-live">直播</span>
          </div>
          <div class="wqzb-card-body">
            <strong>{{ room.room_title }}</strong>
            <div class="wqzb-meta"><span>{{ room.user_nickname || '玩球直播' }}</span><span v-if="heat(room.heat_number)">🔥 {{ heat(room.heat_number) }}</span></div>
          </div>
        </button>
      </div>
      <button v-if="plate === plates[plates.length - 1] && !exhausted[plate.id]" class="wqzb-more" type="button"
        :disabled="loadingMore !== null" @click="loadMore(plate)">
        {{ loadingMore === plate.id ? '加载中…' : '查看更多直播间' }}
      </button>
    </section>

    <div v-if="selectedRoom" class="wqzb-player-backdrop" @click.self="closeRoom">
      <section class="wqzb-player" aria-label="直播播放器">
        <div class="wqzb-player-head">
          <div><span class="wqzb-live-inline">直播</span><strong>{{ selectedRoom.room_title }}</strong></div>
          <button type="button" @click="closeRoom">返回直播间</button>
        </div>
        <div class="wqzb-video-box">
          <canvas ref="canvas"></canvas>
          <div v-if="playbackBusy" class="wqzb-video-overlay">正在连接直播…</div>
          <div ref="loadingLayer" class="wqzb-buffering-hint" style="display:none">正在缓冲直播…</div>
        </div>
        <div class="wqzb-player-foot">
          <span v-if="playbackError" role="alert">{{ playbackError }}</span>
          <span v-else>直播内容由玩球直播提供 · FFmpeg 软解码</span>
          <div>
            <button type="button" :disabled="playbackBusy" @click="togglePlayback">{{ playing ? '暂停' : '继续直播' }}</button>
            <button type="button" @click="openRoom(selectedRoom)">重试</button>
            <button v-if="audioBlocked" type="button" @click="resumeAudio">开启声音</button>
          </div>
        </div>
      </section>
    </div>
    <audio ref="channelAudio" class="wqzb-channel-audio" aria-hidden="true"></audio>
  </main>
</template>

<style scoped>
.wqzb-app{position:relative;height:100%;overflow:auto;background:#101824;color:#f4f7fc;padding:24px 28px 48px;box-sizing:border-box}.wqzb-app.player-open{overflow:hidden}
.wqzb-header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:8px 0 22px;border-bottom:1px solid #ffffff1b}
.wqzb-eyebrow{color:#5bd9c6;font-size:12px;letter-spacing:.22em;font-weight:700}
h1{font-size:30px;margin:5px 0 3px}h2{font-size:21px;margin:0}.wqzb-header p{margin:0;color:#a8b6c9;font-size:14px}
button{font:inherit;cursor:pointer}.wqzb-refresh,.wqzb-more{border:1px solid #66829a;background:#203247;color:#fff;border-radius:11px;padding:12px 18px;min-height:46px}.wqzb-refresh:hover,.wqzb-more:hover{background:#2e4761}
.wqzb-channels{display:flex;gap:10px;overflow-x:auto;overflow-y:hidden;padding:20px 0 10px;scrollbar-width:none;-ms-overflow-style:none;touch-action:pan-x}.wqzb-channels::-webkit-scrollbar{display:none}.wqzb-channels button{flex:none;border:1px solid #40526a;background:#1d2b3c;color:#c8d6e4;border-radius:99px;padding:10px 18px;min-height:46px}.wqzb-channels button.active{background:#35c5aa;color:#09232b;border-color:#35c5aa;font-weight:700}
.wqzb-section{margin-top:25px}.wqzb-section-head{display:flex;align-items:baseline;gap:12px;margin-bottom:16px}.wqzb-section-head span{color:#92a4b9;font-size:13px}
.wqzb-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}.wqzb-card{display:block;width:100%;padding:0;text-align:left;background:#1b293a;border:1px solid #35485d;border-radius:16px;overflow:hidden;color:inherit;transition:transform .15s,border-color .15s}.wqzb-card:hover,.wqzb-card:focus-visible{transform:translateY(-3px);border-color:#54d7bc;outline:none}.wqzb-cover{position:relative;aspect-ratio:16/9;background:linear-gradient(135deg,#193956,#111e32);overflow:hidden}.wqzb-cover img{width:100%;height:100%;object-fit:cover}.wqzb-cover-placeholder{display:grid;place-items:center;height:100%;font-size:38px;color:#6bd5c7}.wqzb-live{position:absolute;left:10px;top:10px;background:#e34e50;color:white;font-size:12px;font-weight:700;padding:4px 8px;border-radius:6px}.wqzb-card-body{padding:13px 14px 15px}.wqzb-card-body strong{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;min-height:44px;line-height:22px;font-size:15px}.wqzb-meta{display:flex;justify-content:space-between;gap:10px;color:#9caec2;font-size:12px;margin-top:10px}.wqzb-more{margin-top:18px;width:100%}.wqzb-more:disabled{opacity:.6;cursor:wait}.wqzb-state{padding:50px;text-align:center;color:#a8b6c9}.wqzb-error{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:#462b35;color:#ffe7eb;padding:15px;border-radius:12px;margin-top:20px}.wqzb-error button{color:#fff;background:#825063;border:0;border-radius:7px;padding:8px 12px}
.wqzb-player-backdrop{position:absolute;inset:0;z-index:10;background:#050a10ed;display:grid;place-items:center;padding:16px 16px 16px calc(16px + clamp(16px,2.5vw,24px));box-sizing:border-box}.wqzb-player{width:min(1100px,100%);background:#111b29;border:1px solid #4c6176;border-radius:18px;overflow:hidden;box-shadow:0 22px 70px #000a;color:#f4f7fc}.wqzb-player-head,.wqzb-player-foot{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:14px 18px}.wqzb-player-head>div{display:flex;align-items:center;gap:10px;min-width:0}.wqzb-player-head strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wqzb-player button{flex:none;border:1px solid #536b82;background:#26394d;color:white;padding:9px 13px;border-radius:9px;text-decoration:none;cursor:pointer;min-height:42px}.wqzb-live-inline{background:#e34e50;padding:4px 8px;border-radius:5px;font-size:12px}.wqzb-video-box{position:relative;background:#000;aspect-ratio:16/9;max-height:calc(100vh - 160px)}.wqzb-video-box canvas{width:100%;height:100%}.wqzb-video-overlay{position:absolute;inset:0;display:grid;place-items:center;color:#fff;background:#0008;pointer-events:none}.wqzb-buffering-hint{position:absolute;top:12px;right:12px;z-index:1;padding:6px 10px;border-radius:8px;background:#101824b8;color:#e9f2fa;font-size:12px;line-height:1.4;pointer-events:none}.wqzb-player-foot{color:#a8b6c9;font-size:13px}.wqzb-player-foot>div{display:flex;gap:8px}.wqzb-channel-audio{display:none}
@media(max-width:700px){.wqzb-app{padding:16px}.wqzb-header{align-items:flex-start}.wqzb-header p{display:none}.wqzb-grid{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}.wqzb-card-body strong{font-size:14px}}
</style>
