<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { CaretRight, FolderOpened, RefreshRight, Refresh, VideoPause } from '@element-plus/icons-vue';
import { get } from '@/functions/requests';
import { generateSilentWav } from '@/functions/audioUtils';

declare global {
  interface Window {
    GameBoyAdvance?: any;
    biosBin?: ArrayBuffer;
    __gbaScriptsPromise?: Promise<void>;
  }
}

const canvasRef = ref<HTMLCanvasElement | null>(null);
const silentAudioRef = ref<HTMLAudioElement | null>(null);

const state = reactive({
  viewMode: 'library',
  rootPath: '',
  currentPath: '',
  libraryTab: 'remote',
  loadingList: false,
  loadingRemote: false,
  loadingRom: false,
  emulatorReady: false,
  emulatorError: '',
  statusText: '选择一个 GBA ROM 开始游玩',
  debugText: '',
  localItems: [] as any[],
  remoteItems: [] as any[],
  activeRomPath: '',
  activeRomName: '',
  activeRomUrl: '',
  playing: false,
});

const breadcrumbs = computed(() => {
  const segments = state.currentPath ? state.currentPath.split('/').filter(Boolean) : [];
  const items = [{ label: 'ROM 库', path: '' }];
  let current = '';
  for (const segment of segments) {
    current = current ? `${current}/${segment}` : segment;
    items.push({ label: segment, path: current });
  }
  return items;
});

const romFiles = computed(() => state.localItems.filter((item: any) => item.type === 'file'));
const folderItems = computed(() => state.localItems.filter((item: any) => item.type === 'dir'));

const SCRIPT_PATHS = [
  '/vendor/gbajs2/js/util.js',
  '/vendor/gbajs2/js/core.js',
  '/vendor/gbajs2/js/arm.js',
  '/vendor/gbajs2/js/thumb.js',
  '/vendor/gbajs2/js/mmu.js',
  '/vendor/gbajs2/js/io.js',
  '/vendor/gbajs2/js/audio.js',
  '/vendor/gbajs2/js/video.js',
  '/vendor/gbajs2/js/video/proxy.js',
  '/vendor/gbajs2/js/video/software.js',
  '/vendor/gbajs2/js/irq.js',
  '/vendor/gbajs2/js/keypad.js',
  '/vendor/gbajs2/js/sio.js',
  '/vendor/gbajs2/js/savedata.js',
  '/vendor/gbajs2/js/gpio.js',
  '/vendor/gbajs2/js/gba.js',
  '/vendor/gbajs2/resources/xhr.js',
  '/vendor/gbajs2/resources/biosbin.js',
];

function loadScript(src: string) {
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector(`script[data-gba-src="${src}"]`) as HTMLScriptElement | null;
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`load failed: ${src}`)), { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset.gbaSrc = src;
    script.onload = () => {
      script.dataset.loaded = 'true';
      resolve();
    };
    script.onerror = () => reject(new Error(`load failed: ${src}`));
    document.body.appendChild(script);
  });
}

function ensureGbaScripts() {
  if (!window.__gbaScriptsPromise) {
    window.__gbaScriptsPromise = SCRIPT_PATHS.reduce((chain, src) => {
      return chain.then(() => loadScript(src));
    }, Promise.resolve());
  }
  return window.__gbaScriptsPromise;
}

function ensureEmulator() {
  return ensureGbaScripts().then(() => {
    if (!window.GameBoyAdvance || !window.biosBin) {
      throw new Error('GBA 内核加载失败');
    }
    state.emulatorReady = true;
    state.emulatorError = '';
    return true;
  }).catch((error: any) => {
    state.emulatorReady = false;
    state.emulatorError = error?.message || 'GBA 内核加载失败';
    throw error;
  });
}

let gbaInstance: any = null;
let saveSyncTimer: number | null = null;
let silentAudioUnlockHandler: (() => void) | null = null;

function getActiveSaveKey(item?: any) {
  const candidate = item?.id || item?.path || state.activeRomPath || state.activeRomName;
  return String(candidate || '').replace(/[^a-zA-Z0-9._-]/g, '_');
}

async function loadServerSave(gba: any, item: any) {
  const saveKey = getActiveSaveKey(item);
  if (!saveKey) {
    return;
  }
  const response = await fetch(`/api/gba/saves/${encodeURIComponent(saveKey)}`, { credentials: 'same-origin' });
  if (!response.ok) {
    if (response.status !== 404) {
      throw new Error('读取服务端存档失败');
    }
    return;
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > 0) {
    gba.setSavedata(buffer);
  }
}

async function syncSaveToServer(force = false) {
  if (!gbaInstance?.mmu?.save || !state.activeRomName) {
    return;
  }
  const save = gbaInstance.mmu.save;
  if (!force && !gbaInstance.mmu.saveNeedsFlush?.()) {
    return;
  }
  const saveKey = getActiveSaveKey({ path: state.activeRomPath, name: state.activeRomName });
  if (!saveKey) {
    return;
  }
  const payload = save.buffer ? save.buffer.slice(0) : null;
  if (!payload) {
    return;
  }
  const response = await fetch(`/api/gba/saves/${encodeURIComponent(saveKey)}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/octet-stream',
    },
    body: payload,
  });
  if (!response.ok) {
    throw new Error('写入服务端存档失败');
  }
  if (gbaInstance.mmu.flushSave) {
    gbaInstance.mmu.flushSave();
  }
}

function ensureSilentAudioPlayback() {
  const audio = silentAudioRef.value;
  if (!audio) {
    return;
  }
  if (!audio.src) {
    audio.src = 'data:audio/wav;base64,' + generateSilentWav(60);
  }
  audio.play().catch(() => {
    if (silentAudioUnlockHandler) {
      return;
    }
    silentAudioUnlockHandler = () => {
      audio.play().catch(() => {});
    };
    document.addEventListener('click', silentAudioUnlockHandler, { passive: true });
    document.addEventListener('touchstart', silentAudioUnlockHandler, { passive: true });
  });
}

function startSaveSyncLoop() {
  if (saveSyncTimer !== null) {
    window.clearInterval(saveSyncTimer);
  }
  saveSyncTimer = window.setInterval(() => {
    syncSaveToServer().catch((error: any) => {
      console.error(error);
    });
  }, 3000);
}

function stopSaveSyncLoop() {
  if (saveSyncTimer !== null) {
    window.clearInterval(saveSyncTimer);
    saveSyncTimer = null;
  }
}

function createEmulator() {
  if (!window.GameBoyAdvance || !window.biosBin || !canvasRef.value) {
    throw new Error('GBA 内核尚未就绪');
  }
  if (gbaInstance) {
    gbaInstance.pause();
  }
  const gba = new window.GameBoyAdvance();
  gba.keypad.eatInput = true;
  gba.logLevel = gba.LOG_ERROR;
  gba.setLogger((_level: number, error: Error | string) => {
    const message = typeof error === 'string' ? error : error?.message || '模拟器运行异常';
    state.emulatorError = message;
    state.debugText = message;
    console.error(error);
  });
  gba.setCanvas(canvasRef.value);
  gba.setBios(window.biosBin);
  gbaInstance = gba;
  return gba;
}

function formatBytes(size?: number) {
  if (!size) {
    return '-';
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function loadRomList(path = state.currentPath) {
  state.loadingList = true;
  return get(`/api/gba/list?path=${encodeURIComponent(path)}`, '读取 GBA ROM 列表失败').then((data) => {
    state.rootPath = data.rootPath || '';
    state.currentPath = data.path || '';
    state.localItems = data.items || [];
  }).finally(() => {
    state.loadingList = false;
  });
}

function loadRemoteCatalog() {
  state.loadingRemote = true;
  return fetch('/catalogs/gba-js-org.json', { credentials: 'same-origin' })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error('读取在线 GBA 游戏库失败');
      }
      return response.json();
    })
    .then((data) => {
      const items = Array.isArray(data?.items) ? data.items : [];
      state.remoteItems = items.map((item: any) => ({
        ...item,
        type: 'remote',
        path: `remote:${item.id}`,
      }));
    })
    .catch((error: any) => {
      state.remoteItems = [];
      ElMessage.error(error?.message || '读取在线 GBA 游戏库失败');
    })
    .finally(() => {
      state.loadingRemote = false;
    });
}

function refreshLibrary() {
  return Promise.all([loadRomList(), loadRemoteCatalog()]);
}

function formatRemoteRomTitle(item: any) {
  if (item?.zhName) {
    return `${item.zhName}（${item.name}）`;
  }
  return item?.name || '';
}

function goToPath(path: string) {
  loadRomList(path);
}

function pauseEmulator() {
  if (!gbaInstance) {
    return;
  }
  syncSaveToServer(true).catch((error: any) => {
    console.error(error);
  });
  gbaInstance.pause();
  state.playing = false;
  state.statusText = state.activeRomName ? `已暂停《${state.activeRomName}》` : '模拟器已暂停';
}

function resumeEmulator() {
  if (!gbaInstance || !state.activeRomPath) {
    return;
  }
  ensureSilentAudioPlayback();
  if (gbaInstance.audio?.context?.resume) {
    gbaInstance.audio.context.resume().catch(() => {});
  }
  gbaInstance.runStable();
  state.playing = true;
  state.statusText = `正在运行《${state.activeRomName}》`;
}

function resetEmulator() {
  if (!state.activeRomPath) {
    return;
  }
  syncSaveToServer(true).catch((error: any) => {
    console.error(error);
  });
  const allItems = [...state.localItems, ...state.remoteItems];
  loadRom(allItems.find((item: any) => item.path === state.activeRomPath) || {
    path: state.activeRomPath,
    url: state.activeRomUrl,
    name: state.activeRomName,
  });
}

function loadRom(item: any) {
  state.loadingRom = true;
  state.statusText = `正在加载《${item.name}》...`;
  state.debugText = '';
  state.viewMode = 'play';
  ensureEmulator().then(async () => {
    await nextTick();
    ensureSilentAudioPlayback();
    const gba = createEmulator();
    const response = await fetch(item.url, { credentials: 'same-origin' });
    if (!response.ok) {
      throw new Error('ROM 下载失败');
    }
    const blob = await response.blob();
    const file = new File([blob], item.name, { type: 'application/octet-stream' });
    await new Promise<void>((resolve, reject) => {
      gba.loadRomFromFile(file, (result: boolean) => {
        if (result) {
          state.debugText = `${gba.mmu?.cart?.title || item.name} 已载入`;
          resolve();
          return;
        }
        reject(new Error('ROM 无法识别，请确认文件是有效的 .gba 游戏'));
      });
    });
    await loadServerSave(gba, item);
    if (gba.audio?.context?.resume) {
      gba.audio.context.resume().catch(() => {});
    }
    gba.runStable();
    startSaveSyncLoop();
    state.activeRomPath = item.path;
    state.activeRomName = item.name;
    state.activeRomUrl = item.url;
    state.playing = true;
    state.statusText = `正在运行《${item.name}》`;
    ElMessage.success(`已启动 ${item.name}`);
  }).catch((error: any) => {
    state.playing = false;
    state.statusText = error?.message || 'ROM 加载失败';
    ElMessage.error(error?.message || 'ROM 加载失败');
  }).finally(() => {
    state.loadingRom = false;
  });
}

function updateVirtualKey(keyName: string, pressed: boolean) {
  const gba = gbaInstance;
  if (!gba?.keypad || typeof gba.keypad[keyName] !== 'number') {
    return;
  }
  const toggle = 1 << gba.keypad[keyName];
  if (pressed) {
    gba.keypad.currentDown &= ~toggle;
    return;
  }
  gba.keypad.currentDown |= toggle;
}

function handleVirtualControl(keyName: string, pressed: boolean, event?: Event) {
  event?.preventDefault();
  updateVirtualKey(keyName, pressed);
}

function enterPlayMode() {
  if (!state.activeRomPath) {
    ElMessage.warning('请先从游戏库启动一个 ROM');
    return;
  }
  state.viewMode = 'play';
}

function backToLibrary() {
  syncSaveToServer(true).catch((error: any) => {
    console.error(error);
  });
  state.viewMode = 'library';
}

onMounted(() => {
  ensureEmulator().catch(() => {});
  ensureSilentAudioPlayback();
  loadRomList();
  loadRemoteCatalog();
});

onUnmounted(() => {
  stopSaveSyncLoop();
  syncSaveToServer(true).catch((error: any) => {
    console.error(error);
  });
  pauseEmulator();
  if (silentAudioUnlockHandler) {
    document.removeEventListener('click', silentAudioUnlockHandler);
    document.removeEventListener('touchstart', silentAudioUnlockHandler);
    silentAudioUnlockHandler = null;
  }
});
</script>

<template>
  <div class="gba-page">
    <template v-if="state.viewMode === 'library'">
      <section class="library-shell">
        <div class="library-topbar">
          <div>
            <h2>游戏库</h2>
            <p>本地 {{ romFiles.length }} 个 ROM、{{ folderItems.length }} 个文件夹；在线补充 {{ state.remoteItems.length }} 个 ROM</p>
          </div>
          <div class="library-actions">
            <el-button v-if="state.activeRomName" @click="enterPlayMode">继续 {{ state.activeRomName }}</el-button>
            <el-button circle :icon="RefreshRight" :loading="state.loadingList || state.loadingRemote" @click="refreshLibrary()" />
          </div>
        </div>

        <div class="library-tabs">
          <button class="library-tab" :class="{ active: state.libraryTab === 'remote' }" @click="state.libraryTab = 'remote'">
            在线 ROM
            <span>{{ state.remoteItems.length }}</span>
          </button>
          <button class="library-tab" :class="{ active: state.libraryTab === 'local' }" @click="state.libraryTab = 'local'">
            本地 ROM
            <span>{{ romFiles.length }}</span>
          </button>
        </div>

        <div v-if="state.libraryTab === 'local'" class="breadcrumbs">
          <button
            v-for="item in breadcrumbs"
            :key="item.path || 'root'"
            class="crumb-button"
            :class="{ active: item.path === state.currentPath }"
            @click="goToPath(item.path)"
          >
            {{ item.label }}
          </button>
        </div>

        <div v-if="state.libraryTab === 'local'" class="library-section-title">
          <strong>本地 ROM</strong>
          <span>{{ state.rootPath || './roms/gba' }}</span>
        </div>

        <div v-if="state.libraryTab === 'local'" class="rom-grid">
          <button
            v-for="item in state.localItems"
            :key="item.path"
            class="rom-card"
            :class="{
              folder: item.type === 'dir',
              active: item.type === 'file' && item.path === state.activeRomPath,
            }"
            @click="item.type === 'dir' ? goToPath(item.path) : loadRom(item)"
          >
            <div class="rom-card-icon">
              <el-icon v-if="item.type === 'dir'"><FolderOpened /></el-icon>
              <el-icon v-else><CaretRight /></el-icon>
            </div>
            <div class="rom-card-body">
              <strong>{{ item.name }}</strong>
              <span v-if="item.type === 'dir'">进入文件夹</span>
              <span v-else>{{ formatBytes(item.size) }}</span>
            </div>
          </button>

          <div v-if="!state.loadingList && state.localItems.length === 0" class="empty-card">
            <strong>还没有可启动的 GBA ROM</strong>
            <span>把 `.gba` 文件放到 {{ state.rootPath || './roms/gba' }} 后刷新即可。</span>
          </div>
        </div>

        <div v-if="state.libraryTab === 'remote'" class="library-section-title remote">
          <strong>在线 ROM</strong>
          <span>来自 gba.js.org 的公开示例库</span>
        </div>

        <div v-if="state.libraryTab === 'remote'" class="rom-grid remote-grid">
          <button
            v-for="item in state.remoteItems"
            :key="item.path"
            class="rom-card remote-card"
            :class="{ active: item.path === state.activeRomPath }"
            @click="loadRom(item)"
          >
            <div class="rom-card-icon">
              <el-icon><CaretRight /></el-icon>
            </div>
            <div class="rom-card-body">
              <strong>{{ formatRemoteRomTitle(item) }}</strong>
              <span>{{ item.provider }}</span>
            </div>
          </button>

          <div v-if="!state.loadingRemote && state.remoteItems.length === 0" class="empty-card">
            <strong>在线 GBA 游戏库暂时不可用</strong>
            <span>稍后再刷新页面试试。</span>
          </div>
        </div>
      </section>
    </template>

    <template v-else>
      <section class="play-shell">
        <audio ref="silentAudioRef" loop controls style="display: none;" />
        <div class="play-stage">
          <div class="top-stage">
            <div class="screen-section">
            <div class="screen-bezel compact">
              <canvas ref="canvasRef" class="gba-screen" width="240" height="160"></canvas>
              <div v-if="state.loadingRom" class="screen-overlay">
                <strong>加载中</strong>
                <span>{{ state.statusText || '正在准备 GBA ROM…' }}</span>
              </div>
              <div v-if="!state.activeRomPath" class="screen-overlay">
                <strong>从游戏库选择一个 ROM</strong>
                <span>默认键位：方向键 / Z / X / Enter / \\ / A / S</span>
              </div>
            </div>
          </div>

          <div class="utility-panel">
              <div class="bottom-status">
                <strong>{{ state.activeRomName || '等待启动' }}</strong>
                <span><em>{{ state.emulatorError || state.statusText }}</em></span>
              </div>
              <div v-if="state.debugText || state.emulatorError" class="debug-strip">
                <span>{{ state.emulatorError || state.debugText }}</span>
              </div>
              <div class="utility-actions">
                <el-button @click="backToLibrary()">返回游戏库</el-button>
                <el-button :icon="state.playing ? VideoPause : CaretRight" :disabled="!state.activeRomPath" @click="state.playing ? pauseEmulator() : resumeEmulator()">
                  {{ state.playing ? '暂停' : '继续' }}
                </el-button>
                <el-button :icon="Refresh" :disabled="!state.activeRomPath || state.loadingRom" @click="resetEmulator()">重启</el-button>
              </div>
            </div>
          </div>

          <div class="controls-section">
            <div class="touch-layout">
              <div class="control-cluster">
                <div class="control-pad">
                  <button class="control-btn up" @pointerdown="handleVirtualControl('UP', true, $event)" @pointerup="handleVirtualControl('UP', false, $event)" @pointerleave="handleVirtualControl('UP', false, $event)" @pointercancel="handleVirtualControl('UP', false, $event)">▲</button>
                  <button class="control-btn left" @pointerdown="handleVirtualControl('LEFT', true, $event)" @pointerup="handleVirtualControl('LEFT', false, $event)" @pointerleave="handleVirtualControl('LEFT', false, $event)" @pointercancel="handleVirtualControl('LEFT', false, $event)">◀</button>
                  <button class="control-btn right" @pointerdown="handleVirtualControl('RIGHT', true, $event)" @pointerup="handleVirtualControl('RIGHT', false, $event)" @pointerleave="handleVirtualControl('RIGHT', false, $event)" @pointercancel="handleVirtualControl('RIGHT', false, $event)">▶</button>
                  <button class="control-btn down" @pointerdown="handleVirtualControl('DOWN', true, $event)" @pointerup="handleVirtualControl('DOWN', false, $event)" @pointerleave="handleVirtualControl('DOWN', false, $event)" @pointercancel="handleVirtualControl('DOWN', false, $event)">▼</button>
                </div>
              </div>

              <div class="center-controls">
                <div class="shoulder-row">
                  <button class="mini-btn shoulder" @pointerdown="handleVirtualControl('L', true, $event)" @pointerup="handleVirtualControl('L', false, $event)" @pointerleave="handleVirtualControl('L', false, $event)" @pointercancel="handleVirtualControl('L', false, $event)">L</button>
                  <button class="mini-btn shoulder" @pointerdown="handleVirtualControl('R', true, $event)" @pointerup="handleVirtualControl('R', false, $event)" @pointerleave="handleVirtualControl('R', false, $event)" @pointercancel="handleVirtualControl('R', false, $event)">R</button>
                </div>
                <div class="mini-controls">
                  <button class="mini-btn" @pointerdown="handleVirtualControl('SELECT', true, $event)" @pointerup="handleVirtualControl('SELECT', false, $event)" @pointerleave="handleVirtualControl('SELECT', false, $event)" @pointercancel="handleVirtualControl('SELECT', false, $event)">SELECT</button>
                  <button class="mini-btn" @pointerdown="handleVirtualControl('START', true, $event)" @pointerup="handleVirtualControl('START', false, $event)" @pointerleave="handleVirtualControl('START', false, $event)" @pointercancel="handleVirtualControl('START', false, $event)">START</button>
                </div>
              </div>

              <div class="control-cluster action-cluster">
                <div class="action-buttons">
                  <button class="action-btn b" @pointerdown="handleVirtualControl('B', true, $event)" @pointerup="handleVirtualControl('B', false, $event)" @pointerleave="handleVirtualControl('B', false, $event)" @pointercancel="handleVirtualControl('B', false, $event)">B</button>
                  <button class="action-btn a" @pointerdown="handleVirtualControl('A', true, $event)" @pointerup="handleVirtualControl('A', false, $event)" @pointerleave="handleVirtualControl('A', false, $event)" @pointercancel="handleVirtualControl('A', false, $event)">A</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.gba-page {
  height: 100%;
  min-height: 100%;
  padding: 24px 28px 28px;
  background:
    radial-gradient(circle at top right, rgba(34, 197, 94, 0.12), transparent 32%),
    radial-gradient(circle at left center, rgba(56, 189, 248, 0.16), transparent 28%),
    var(--color-background);
  color: var(--color-text);
  overflow: hidden;
}

.library-shell,
.play-shell,
.hint-card {
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-surface) 88%, transparent);
  box-shadow: 0 22px 60px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(18px);
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.14);
  color: #0284c7;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.metric-card {
  border-radius: 20px;
  padding: 18px 20px;
  background: color-mix(in srgb, var(--color-background-soft) 78%, transparent);
}

.metric-card span,
.panel-header p,
.rom-card-body span,
.stage-topbar p,
.hint-card span {
  color: var(--color-text-soft);
  font-size: 13px;
}

.metric-card strong,
.hint-card strong {
  display: block;
  margin-top: 6px;
  font-size: 16px;
  line-height: 1.45;
}

.library-shell,
.play-shell {
  border-radius: 28px;
}

.library-shell {
  padding: 18px;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.library-topbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.library-topbar h2,
.bottom-status strong {
  margin: 0;
  font-size: 20px;
}

.launch-card {
  cursor: pointer;
  transition: 0.2s ease;
}

.launch-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 32px rgba(14, 165, 233, 0.12);
}

.library-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.breadcrumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}

.library-tabs {
  display: flex;
  gap: 10px;
  margin: 14px 0 10px;
}

.library-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-background-soft) 82%, transparent);
  color: var(--color-text-soft);
  cursor: pointer;
  transition: 0.2s ease;
}

.library-tab span {
  min-width: 20px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
  color: inherit;
  font-size: 12px;
  text-align: center;
}

.library-tab.active {
  border-color: rgba(14, 165, 233, 0.34);
  background: rgba(14, 165, 233, 0.12);
  color: #0284c7;
}

.library-tab.active span {
  background: rgba(14, 165, 233, 0.18);
}

.library-section-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 6px 2px 12px;
}

.library-section-title strong {
  font-size: 15px;
}

.library-section-title span {
  color: var(--color-text-soft);
  font-size: 12px;
}

.library-section-title.remote {
  margin-top: 18px;
}

.crumb-button {
  border: none;
  border-radius: 999px;
  padding: 8px 12px;
  background: var(--color-background-soft);
  color: var(--color-text-soft);
  cursor: pointer;
  transition: 0.2s ease;
}

.crumb-button.active,
.crumb-button:hover {
  background: rgba(14, 165, 233, 0.14);
  color: #0284c7;
}

.rom-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  overflow-y: auto;
  padding-right: 4px;
  min-height: 0;
}

.rom-card,
.empty-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 20px;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  background: color-mix(in srgb, var(--color-background-soft) 82%, transparent);
}

.rom-card {
  width: 100%;
  cursor: pointer;
  text-align: left;
  transition: 0.2s ease;
}

.rom-card:hover,
.rom-card.active {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.36);
  box-shadow: 0 16px 32px rgba(14, 165, 233, 0.12);
}

.rom-card.folder:hover {
  border-color: rgba(34, 197, 94, 0.36);
  box-shadow: 0 16px 32px rgba(34, 197, 94, 0.12);
}

.rom-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(14, 165, 233, 0.12);
  color: #0284c7;
  font-size: 20px;
}

.rom-card.folder .rom-card-icon {
  background: rgba(34, 197, 94, 0.12);
  color: #16a34a;
}

.remote-card .rom-card-icon {
  background: rgba(249, 115, 22, 0.12);
  color: #ea580c;
}

.rom-card-body {
  min-width: 0;
}

.rom-card-body strong {
  display: block;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-card {
  flex-direction: column;
  align-items: flex-start;
}

.remote-grid {
  margin-top: 0;
}

.bottom-status {
  min-width: 0;
}

.bottom-status strong {
  display: block;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bottom-status span {
  display: block;
  color: var(--color-text-soft);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
}

.bottom-status em {
  display: inline-block;
  min-width: 100%;
  font-style: normal;
  padding-left: 100%;
  animation: status-marquee 12s linear infinite;
}

.screen-bezel {
  position: relative;
  border-radius: 32px;
  background:
    linear-gradient(145deg, rgba(15, 23, 42, 0.96), rgba(15, 23, 42, 0.78));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 28px 70px rgba(15, 23, 42, 0.32);
  display: block;
}

.gba-screen {
  width: 100%;
  height: auto;
  aspect-ratio: 3 / 2;
  background: #020617;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  display: block;
}

.screen-overlay {
  position: absolute;
  inset: 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 8px;
  border-radius: 18px;
  color: rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(2, 6, 23, 0.72), rgba(2, 6, 23, 0.9));
  text-align: center;
}

.play-shell {
  height: 100%;
  padding: 18px;
  overflow: hidden;
}

.play-stage {
  display: grid;
  grid-template-rows: auto 260px;
  gap: 16px;
  height: 100%;
  overflow: hidden;
  align-content: start;
}

.top-stage {
  display: flex;
  gap: 16px;
  min-height: fit-content;
  overflow: visible;
  flex-wrap: nowrap;
  align-items: flex-start;
}

.screen-section {
  flex: 1 1 auto;
  min-height: fit-content;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: visible;
}

.screen-bezel.compact {
  width: min(100%, 620px);
  margin: 0;
  aspect-ratio: 3 / 2;
  height: auto;
  max-height: none;
  align-self: flex-start;
  overflow: visible;
}

.utility-panel {
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border-radius: 26px;
  background: color-mix(in srgb, var(--color-background-soft) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  overflow: hidden;
}

.utility-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.utility-actions :deep(.el-button) {
  width: 100%;
  margin: 0;
}

.controls-section {
  border-radius: 26px;
  padding: 14px 18px;
  background: color-mix(in srgb, var(--color-background-soft) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  overflow: hidden;
}

.touch-layout {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) minmax(180px, auto) minmax(240px, 1fr);
  gap: 16px;
  align-items: center;
  height: 100%;
}

.debug-strip {
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.08);
  color: var(--color-text-soft);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.control-cluster {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.control-pad {
  width: min(200px, 100%);
  aspect-ratio: 1;
  position: relative;
}

.control-btn,
.mini-btn,
.action-btn {
  border: none;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.control-btn {
  position: absolute;
  width: 68px;
  height: 68px;
  border-radius: 20px;
  background: linear-gradient(145deg, #111827, #1f2937);
  color: white;
  font-size: 28px;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.22);
}

.control-btn:active,
.mini-btn:active,
.action-btn:active {
  transform: translateY(1px) scale(0.98);
}

.control-btn.up { top: 0; left: 66px; }
.control-btn.left { top: 66px; left: 0; }
.control-btn.right { top: 73px; right: -25px; }
.control-btn.down { bottom: 0; left: 66px; }

.mini-controls,
.shoulder-row {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.center-controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.mini-btn {
  min-width: 84px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
  color: var(--color-text);
  font-weight: 700;
}

.action-cluster {
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: 16px;
}

.action-btn {
  width: 84px;
  height: 84px;
  border-radius: 999px;
  color: white;
  font-size: 30px;
  font-weight: 800;
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.26);
}

.action-btn.a {
  background: linear-gradient(145deg, #0f766e, #14b8a6);
}

.action-btn.b {
  background: linear-gradient(145deg, #b45309, #f59e0b);
}

@keyframes status-marquee {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-100%);
  }
}

@media (max-width: 1200px) {
}

@media (max-width: 720px) {
  .touch-layout,
  .rom-grid {
    grid-template-columns: 1fr;
  }

  .top-stage {
    flex-direction: column;
  }

  .utility-panel {
    flex-basis: auto;
  }

  .library-topbar {
    flex-direction: column;
  }

  .control-cluster {
    justify-content: center;
  }

  .play-shell,
  .library-shell {
    height: auto;
  }

  .gba-page,
  .play-shell,
  .play-stage {
    overflow: auto;
  }
}
</style>
