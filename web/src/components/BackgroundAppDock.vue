<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { CopyDocument, Close, ArrowLeft, ArrowRight } from '@element-plus/icons-vue';
import QQMusicControlIcon from '@/views/apps/QQMusicControlIcon.vue';
import NavigationTurnIcon from './NavigationTurnIcon.vue';
import { backgroundMusic as music, musicCommands } from '@/stores/backgroundMusic';
import { backgroundNavigation as nav, navigationCommands } from '@/stores/backgroundNavigation';
import { backgroundApps, type BackgroundApp } from '@/stores/backgroundApps';
const router = useRouter(), open = ref(false), failedCover = ref(false);
const entries = computed(() => Object.values(backgroundApps).filter(app => app.id !== 'qqmusic'));
const count = computed(() => entries.value.length + (music.song ? 1 : 0));
const icons = computed(() => [
  ...(music.song ? [{ id: 'qqmusic', icon: music.song.cover && !failedCover.value ? music.song.cover : '/icon/QQMUSIC_LOGO.ico' }] : []),
  ...entries.value.map(app => ({ id: app.id, icon: app.icon })),
].slice(0, 3));
watch(() => router.currentRoute.value.path, () => { open.value = false; });
watch(() => music.song?.cover, () => { failedCover.value = false; });
async function openApp(app: BackgroundApp) { open.value = false; await router.push(app.route); app.open?.(); }
async function fullPlayer() { open.value = false; await router.push('/apps/qqmusic'); musicCommands.open?.(); }
</script>
<template>
  <section class="background-dock" aria-label="后台应用">
    <button class="background-slot" aria-label="后台应用列表" :title="count ? `${count} 个后台应用` : '后台应用'" :aria-expanded="open" @click="open = !open">
      <span v-if="count" class="icon-stack" :class="{ multiple: count > 1 }">
        <span v-for="(item, index) in icons" :key="item.id" class="stack-icon" :class="{ disc: item.id === 'qqmusic', spinning: item.id === 'qqmusic' && music.playing }" :style="{ '--stack-index': index, zIndex: 3 - index }">
          <img :src="item.icon" alt="" @error="item.id === 'qqmusic' && (failedCover = true)" />
        </span>
      </span>
      <CopyDocument v-else class="empty-icon" />
      <span v-if="count > 1" class="count-badge">{{ count }}</span>
      <i v-else-if="music.playing || entries.some(app => app.running)" class="running-dot" />
    </button>
    <Teleport v-if="open" to="body">
        <button class="dock-dismiss" aria-label="关闭后台应用面板" @click="open = false" />
        <section class="dock-panel" aria-label="后台应用面板" @keydown.esc="open = false">
          <header class="panel-header"><strong>后台应用 <small v-if="count">{{ count }}</small></strong><button aria-label="收起后台应用" @click="open = false"><Close /></button></header>
          <div class="task-list">
            <article v-if="music.song" class="task-card music-card" aria-label="QQ 音乐后台卡片">
              <div class="task-heading"><img :src="music.song.cover && !failedCover ? music.song.cover : '/icon/QQMUSIC_LOGO.ico'" alt="" @error="failedCover = true"/><div><small>QQ 音乐 · {{ music.playing ? '正在播放' : '已暂停' }}</small><strong>{{ music.song.title }}</strong><span>{{ music.song.singer }}</span></div></div>
              <progress :value="music.elapsed" :max="music.duration || 1" aria-label="歌曲播放进度" />
              <div class="music-actions">
                <button aria-label="上一首" :disabled="music.loading || music.previousDisabled" @click="musicCommands.previous?.()"><ArrowLeft /></button>
                <button class="music-toggle" :aria-label="music.playing ? '暂停音乐' : '播放音乐'" :disabled="music.loading" @click="musicCommands.toggle?.()"><QQMusicControlIcon :kind="music.playing ? 'pause' : 'play'" /></button>
                <button aria-label="下一首" :disabled="music.loading || music.nextDisabled" @click="musicCommands.next?.()"><ArrowRight /></button>
                <button class="open-player" @click="fullPlayer">打开播放器</button>
              </div>
              <p v-if="music.loading">正在加载歌曲…</p><p v-if="music.error" role="status">{{ music.error }}</p>
            </article>
            <article v-for="app in entries" :key="app.id" class="task-card" :aria-label="app.name + '后台卡片'">
              <div class="task-heading"><img :src="app.icon" alt=""/><div><strong>{{ app.name }}</strong><small>{{ app.running ? '正在后台运行' : '已暂停' }}</small></div></div>
              <template v-if="app.id === 'amap' && nav.active">
                <div class="nav-guidance"><NavigationTurnIcon :arrow="nav.arrow"/><div><strong>{{ nav.instruction }}</strong><span>{{ nav.road }}</span><small>剩余 {{ nav.remaining }} · {{ nav.remainingDuration }}{{ nav.simulated ? ' · 模拟导航' : '' }}</small></div></div>
                <div class="task-actions"><button @click="navigationCommands.toggleVoice?.()">{{ nav.muted ? '开启语音' : '静音' }}</button><button @click="navigationCommands.stop?.()">结束导航</button><button @click="openApp(app)">打开导航</button></div>
              </template>
              <template v-else><p>{{ app.detail || (app.running ? '正在后台运行' : '已暂停') }}</p><button @click="openApp(app)">打开应用</button></template>
            </article>
            <p v-if="!count" class="empty-message">暂无后台应用，音乐播放或导航开始后会显示在这里。</p>
          </div>
        </section>
    </Teleport>
  </section>
</template>
<style scoped>
.background-dock{flex:0 0 auto;min-height:62px;width:100%;padding:6px 0;border-top:1px solid var(--color-border);background:var(--color-surface);box-sizing:border-box;display:grid;place-items:center}
.background-slot{position:relative;width:48px;max-width:100%;height:48px;padding:0;display:grid;place-items:center;border:0;border-radius:13px;background:none;color:var(--color-text-soft);cursor:pointer}.background-slot:focus-visible{outline:2px solid var(--color-accent);outline-offset:-2px}.empty-icon{width:30px;height:30px;opacity:.65}
.icon-stack{position:relative;width:38px;height:38px}.stack-icon{position:absolute;inset:0;border-radius:10px;background:var(--color-surface);box-shadow:0 1px 5px #0003;overflow:hidden;border:2px solid var(--color-surface);box-sizing:border-box}.stack-icon img{width:100%;height:100%;object-fit:contain}.stack-icon.disc{border-radius:50%}.disc img{object-fit:cover}.multiple{width:31px;height:31px;margin-right:7px;margin-bottom:5px}.multiple .stack-icon{transform:translate(calc(var(--stack-index)*5px),calc(var(--stack-index)*4px)) rotate(calc(var(--stack-index)*7deg))}.disc.spinning img{animation:disc-spin 10s linear infinite}.count-badge,.running-dot{position:absolute;z-index:5;right:0;bottom:0;border:2px solid var(--color-surface);border-radius:12px;background:#13ac7b;color:white}.count-badge{min-width:17px;height:17px;font-size:10px;display:grid;place-items:center}.running-dot{width:8px;height:8px;right:3px;bottom:3px}
.dock-dismiss{position:fixed;inset:0;background:transparent;border:0;z-index:2100}.dock-panel{position:fixed;z-index:2101;left:calc(clamp(48px,6.4vw,80px) + 10px);bottom:12px;width:min(360px,calc(100vw - clamp(48px,6.4vw,80px) - 24px));max-height:calc(100dvh - 24px);box-sizing:border-box;padding:12px;border:1px solid var(--color-border);border-radius:20px;background:var(--color-surface);color:var(--color-text);box-shadow:0 10px 32px #0003;display:flex;flex-direction:column}
.panel-header{display:flex;align-items:center;justify-content:space-between;flex-shrink:0;padding:0 4px 8px}.panel-header small{font-size:12px;opacity:.6;margin-left:6px}.dock-panel button{border:0;border-radius:10px;background:var(--color-background-mute);color:inherit;padding:8px 10px;cursor:pointer;min-height:40px;display:grid;place-items:center}.dock-panel button:disabled{opacity:.4;cursor:default}.panel-header button{width:40px}.dock-panel svg{width:20px;height:20px}.task-list{min-height:0;overflow:auto;overscroll-behavior:contain;display:grid;gap:10px}.task-card{padding:12px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-background-soft)}.task-heading{display:flex;gap:10px;align-items:center;min-width:0}.task-heading>img{width:42px;height:42px;border-radius:10px;object-fit:cover}.task-heading>div{min-width:0;display:grid;gap:3px}.task-heading strong,.task-heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.task-heading small,.task-heading span,.nav-guidance small{font-size:12px;color:var(--color-text-soft)}.music-actions,.task-actions{display:flex;align-items:center;gap:7px}.music-actions button{flex-shrink:0}.music-actions .music-toggle{background:#13ac7b;color:white}.music-actions .open-player{flex:1;font-size:12px}.music-card progress{display:block;width:100%;height:4px;margin:12px 0;accent-color:#13ac7b}.dock-panel p{font-size:13px;color:var(--color-text-soft);line-height:1.6;margin:10px 0}.nav-guidance{display:flex;align-items:center;gap:10px;margin:12px 0}.nav-guidance>svg{width:30px;height:38px;flex-shrink:0}.nav-guidance>div{display:grid;gap:4px;min-width:0}.nav-guidance span{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.task-actions{justify-content:flex-end}.task-actions button{font-size:12px}.empty-message{padding:4px 8px}@keyframes disc-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.disc.spinning img{animation:none}}
</style>
