<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { FullScreen, VideoPlay } from '@element-plus/icons-vue';
import { get } from '@/functions/requests';
import { generateSilentWav } from '@/functions/audioUtils';

declare const Player: any;
declare const playerStateIdle: number;
declare const playerStatePausing: number;
declare const playerStatePlaying: number;

const playerCanvas = ref<HTMLCanvasElement | null>(null);
const videoLoading = ref<HTMLElement | null>(null);
const timeTrack = ref<HTMLInputElement | null>(null);
const timeLabel = ref<HTMLLabelElement | null>(null);
const silentAudioRef = ref<HTMLAudioElement | null>(null);

let videoPlayer: any = null;
const waitHeaderLength = 512 * 1024;

const state = reactive({
  input: '',
  loading: false,
  isPlay: false,
  showScreen: true,
  title: '',
  authorName: '',
  videoId: '',
  videoUrl: '',
  cover: '',
  streamUrl: '',
});

function playOrPause() {
  if (!videoPlayer) {
    return;
  }
  const currentState = videoPlayer.getState();
  if (currentState === playerStatePlaying) {
    state.isPlay = false;
    videoPlayer.pause();
  } else if (currentState === playerStateIdle) {
    state.isPlay = false;
  } else if (currentState === playerStatePausing) {
    state.isPlay = true;
    videoPlayer.resume();
  }
}

function unlockAudio() {
  if (!silentAudioRef.value) {
    return;
  }
  silentAudioRef.value.src = `data:audio/wav;base64,${generateSilentWav(60)}`;
  silentAudioRef.value.play().catch(() => {
    document.addEventListener('click', () => silentAudioRef.value?.play(), { once: true });
  });
}

function playStream(streamUrl: string) {
  if (!videoPlayer || !playerCanvas.value) {
    return;
  }
  videoPlayer.stop();
  videoPlayer.showLoading?.();
  videoPlayer.play(`stream://${streamUrl}`, playerCanvas.value, (event: any) => {
    if (event?.error === 1) {
      state.isPlay = false;
      return;
    }
    if (event?.error) {
      state.isPlay = false;
      ElMessage.error(event.message || `抖音播放失败（error=${event.error}）`);
    }
  }, waitHeaderLength, true);
  videoPlayer.setTrack(timeTrack.value, timeLabel.value);
  state.isPlay = true;
  unlockAudio();
}

function resolveAndPlay() {
  const source = state.input.trim();
  if (!source) {
    ElMessage.warning('请粘贴抖音视频分享链接或视频 ID');
    return;
  }
  state.loading = true;
  get(`/api/douyin/resolve?url=${encodeURIComponent(source)}`, '解析抖音视频失败').then((data) => {
    state.videoId = data.videoId || '';
    state.title = data.title || '抖音视频';
    state.authorName = data.authorName || '';
    state.videoUrl = data.videoUrl || '';
    state.cover = data.cover || '';
    state.streamUrl = data.streamUrl || '';
    if (!state.streamUrl) {
      ElMessage.error('后端未返回可播放流');
      return;
    }
    playStream(state.streamUrl);
  }).finally(() => {
    state.loading = false;
  });
}

function fullscreen() {
  videoPlayer?.fullscreen?.();
}

function openDouyinPage() {
  const url = state.videoUrl || 'https://www.douyin.com/?recommend=1';
  window.open(url, '_blank', 'noreferrer');
}

onMounted(() => {
  videoPlayer = new Player();
  videoPlayer.setLoadingDiv(videoLoading.value);
  videoPlayer.setFinishCallback(() => {
    state.isPlay = false;
  });
});

onUnmounted(() => {
  videoPlayer?.stop?.();
});
</script>

<template>
  <main class="douyin-page">
    <section class="douyin-player-stage">
      <canvas id="douyin-player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
      <div v-show="!state.showScreen" class="screen-cap"></div>
      <div class="douyin-float" @click="playOrPause">
        <div ref="videoLoading" class="loadEffect" style="display:none;">
          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div v-if="!state.isPlay" class="douyin-play-btn">
          <el-icon :size="92"><VideoPlay /></el-icon>
        </div>
      </div>
    </section>

    <section class="douyin-controls">
      <div class="douyin-progress-row">
        <input ref="timeTrack" class="douyin-progress" type="range" value="0">
      </div>
      <div class="douyin-toolbar">
        <div class="douyin-meta">
          <strong>{{ state.title || '抖音播放' }}</strong>
          <span>{{ state.authorName || '输入分享链接后由后端解析播放地址，再通过 canvas 播放。' }}</span>
        </div>
        <div class="douyin-actions">
          <el-input
            v-model="state.input"
            class="douyin-input"
            clearable
            placeholder="粘贴抖音分享链接或视频 ID"
            @keyup.enter="resolveAndPlay"
          />
          <el-button type="primary" :loading="state.loading" @click="resolveAndPlay">播放</el-button>
          <el-switch v-model="state.showScreen" inline-prompt active-text="视频" inactive-text="音频" />
          <el-icon :size="34" class="douyin-icon-btn" @click="fullscreen"><FullScreen /></el-icon>
          <el-button plain @click="openDouyinPage">原页</el-button>
          <audio ref="silentAudioRef" loop controls class="silent-audio">
            <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
          </audio>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.douyin-page {
  min-height: 100%;
  background:
    radial-gradient(circle at 18% 12%, rgba(254, 44, 85, 0.22), transparent 30%),
    radial-gradient(circle at 80% 10%, rgba(37, 244, 238, 0.2), transparent 28%),
    linear-gradient(135deg, #090b10 0%, #121826 52%, #05070a 100%);
  color: #f8fafc;
}

.douyin-player-stage {
  position: relative;
  height: calc(100dvh - 190px);
  min-height: 430px;
  display: grid;
  place-items: center;
  overflow: hidden;
  background: #05070a;
}

#douyin-player-canvas {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.screen-cap {
  position: absolute;
  inset: 0;
  background: #05070a;
}

.douyin-float {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.douyin-play-btn {
  color: rgba(255, 255, 255, 0.72);
  filter: drop-shadow(0 10px 24px rgba(0, 0, 0, 0.44));
}

.douyin-controls {
  height: 190px;
  padding: 12px 18px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(6, 10, 16, 0.92);
}

.douyin-progress-row {
  margin-bottom: 12px;
}

.douyin-progress {
  width: 100%;
}

.douyin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.douyin-meta {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 220px;
}

.douyin-meta strong {
  font-size: 22px;
}

.douyin-meta span {
  color: rgba(248, 250, 252, 0.64);
  font-size: 13px;
}

.douyin-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  justify-content: flex-end;
}

.douyin-input {
  max-width: 560px;
  min-width: 280px;
}

.douyin-icon-btn {
  cursor: pointer;
  color: rgba(248, 250, 252, 0.8);
}

.silent-audio {
  display: none;
}

@media (max-width: 900px) {
  .douyin-player-stage {
    height: calc(100dvh - 240px);
  }

  .douyin-controls {
    height: 240px;
  }

  .douyin-toolbar,
  .douyin-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .douyin-input {
    max-width: none;
    min-width: 0;
    width: 100%;
  }
}
</style>
