<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { VideoPlay, VideoPause, ArrowLeft, ArrowRight, Close } from '@element-plus/icons-vue';
import { backgroundMusic as music, musicCommands } from '@/stores/backgroundMusic';
const router = useRouter(), open = ref(false), failedCover = ref(false);
watch(() => router.currentRoute.value.path, () => { open.value = false; });
watch(() => music.song?.cover, () => { failedCover.value = false; });
async function fullPlayer() { await router.push('/apps/qqmusic'); musicCommands.open?.(); }
</script>
<template>
  <div v-if="music.song && router.currentRoute.value.path !== '/apps/qqmusic'" class="background-music">
    <button class="disc-button" aria-label="后台音乐控制" :aria-expanded="open" @click="open = !open">
      <span class="disc" :class="{ spinning: music.playing }"><img v-if="music.song.cover && !failedCover" :src="music.song.cover" alt="" @error="failedCover = true" /><span v-else>♫</span></span>
      <span class="play-dot">{{ music.playing ? 'Ⅱ' : '▶' }}</span>
    </button>
    <template v-if="open">
      <button class="music-dismiss" aria-label="关闭后台音乐控制" @click="open = false" />
      <section class="music-popover" aria-label="后台音乐播放器" @keydown.esc="open = false">
        <header><div><strong>{{ music.song.title }}</strong><small>{{ music.song.singer }}</small></div><button aria-label="收起音乐控制" @click="open = false"><el-icon><Close /></el-icon></button></header>
        <progress :value="music.elapsed" :max="music.duration || 1" aria-label="歌曲播放进度" />
        <div class="music-actions">
          <button aria-label="上一首" :disabled="music.loading || music.previousDisabled" @click="musicCommands.previous?.()"><el-icon><ArrowLeft /></el-icon></button>
          <button class="music-toggle" :aria-label="music.playing ? '暂停音乐' : '播放音乐'" :disabled="music.loading" @click="musicCommands.toggle?.()"><el-icon><VideoPause v-if="music.playing" /><VideoPlay v-else /></el-icon></button>
          <button aria-label="下一首" :disabled="music.loading || music.nextDisabled" @click="musicCommands.next?.()"><el-icon><ArrowRight /></el-icon></button>
          <button class="full-player" @click="fullPlayer">打开播放器</button>
        </div>
        <small v-if="music.loading">正在加载歌曲…</small><small v-if="music.error" role="status">{{ music.error }}</small>
      </section>
    </template>
  </div>
</template>
<style scoped>
.background-music{flex:0 0 54px;display:grid;place-items:center}.disc-button{position:relative;border:0;background:none;cursor:pointer;padding:5px;width:48px;height:48px}.disc{display:grid;place-items:center;width:38px;height:38px;border-radius:50%;overflow:hidden;background:#152b2a;border:3px solid #263c39;box-shadow:0 2px 8px #0003;color:white;animation:spin 10s linear infinite;animation-play-state:paused}.disc img{width:100%;height:100%;object-fit:cover}.disc.spinning{animation-play-state:running}.play-dot{position:absolute;right:0;bottom:0;border:2px solid white;border-radius:50%;background:#13ac7b;color:white;font-size:9px;width:16px;height:16px;display:grid;place-items:center}.music-dismiss{position:fixed;inset:0;border:0;background:transparent;z-index:1000}.music-popover{position:fixed;z-index:1001;left:calc(var(--menu-width) + 10px);bottom:18px;width:min(330px,calc(100vw - var(--menu-width) - 30px));box-sizing:border-box;padding:16px;border-radius:20px;border:1px solid #ffffff80;background:rgba(246,252,250,.97);backdrop-filter:blur(20px);box-shadow:0 8px 36px #10292340;color:#254940}.music-popover header{display:flex;align-items:center;gap:10px}.music-popover header>div{flex:1;min-width:0}.music-popover strong,.music-popover small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.music-popover small{font-size:12px;margin-top:5px;color:#607d71}.music-popover button{border:0;display:grid;place-items:center;border-radius:50%;min-width:40px;height:40px;background:#e6eeea;color:#254940;cursor:pointer;font-size:19px}.music-popover button:disabled{opacity:.4;cursor:default}.music-actions{display:flex;gap:10px;align-items:center}.music-actions .music-toggle{background:#13ac7b;color:white;width:46px;height:46px}.music-actions .full-player{font-size:12px;border-radius:10px;flex:1}.music-popover progress{display:block;width:100%;height:4px;margin:16px 0;accent-color:#13ac7b;border:0;border-radius:4px;overflow:hidden}.music-popover progress::-webkit-progress-bar{background:#dce9e3}.music-popover progress::-webkit-progress-value{background:#13ac7b}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.disc{animation:none}}
</style>
