<script setup lang="ts">
import { onMounted, onBeforeUnmount, onActivated, onDeactivated, ref } from 'vue';
import { backgroundMusic as music } from '@/stores/backgroundMusic';
import { mediaKeyDiagnostics as diagnostics, mediaActionNames, testMediaAction, logMediaKey } from '@/functions/mediaKeyDiagnostics';
const sessionState=ref('未读取');
const actions:MediaSessionAction[]=['previoustrack','play','pause','nexttrack'];
let timer:ReturnType<typeof setInterval> | undefined;
function refresh() { sessionState.value='mediaSession' in navigator ? navigator.mediaSession.playbackState : '不支持'; }
function key(event:KeyboardEvent) {
  // Observe only control keys; never record typed text or intercept normal controls.
  if (['MediaTrackPrevious','MediaTrackNext','MediaPlayPause','MediaStop','ArrowLeft','ArrowRight'].includes(event.key)) {
    logMediaKey('键盘事件',`${event.key}${event.repeat ? '（重复）' : ''} · ${event.isTrusted ? '浏览器输入' : '合成事件'}`);
  }
}
function start() { stop();document.addEventListener('keydown',key);refresh();timer=setInterval(refresh,1000); }
function stop() { document.removeEventListener('keydown',key);clearInterval(timer); }
onMounted(start);onActivated(start);onDeactivated(stop);onBeforeUnmount(stop);
</script>
<template>
  <section class="media-key-test">
    <h2>方向盘 / 媒体按键测试</h2>
    <p>先在 QQ 音乐播放一首歌，确保队列里有多首歌曲，再回到这里拨动方向盘左滚轮。上一首、下一首、播放和暂停都会记录。</p>
    <div class="facts">
      <span>Media Session：<strong>{{ diagnostics.supported ? '接口存在' : '不支持' }}</strong></span>
      <span>媒体会话状态：<strong>{{ sessionState }}</strong></span>
      <span>QQ 音乐：<strong>{{ music.song?.title || '未选择歌曲' }}</strong> · {{ music.loading ? '加载中' : music.playing ? '播放中' : '已暂停' }}</span>
    </div>
    <div class="registrations"><span v-for="action in actions" :key="action">{{ mediaActionNames[action] }}：{{ diagnostics.registrations[action] || '尚未注册' }}</span></div>
    <p v-if="music.error" role="alert">QQ 音乐：{{ music.error }}</p>
    <p>出现“系统媒体指令”表示浏览器确实转发了控制指令，但网页不能辨别它来自方向盘还是其他系统控制。只有“键盘事件”表示收到按键，尚不代表已切歌。</p>
    <div class="buttons"><button v-for="action in actions" :key="action" :disabled="diagnostics.registrations[action] !== '已注册'" @click="testMediaAction(action)">测试{{ mediaActionNames[action] }}</button><button @click="diagnostics.events.splice(0)">清空记录</button></div>
    <p class="hint">测试按钮会实际控制音乐，仅验证网页处理逻辑，不能证明方向盘支持。接口存在或注册成功也不代表车机一定会转发按键。日志只在本次页面运行期间保留，最多 100 条。</p>
    <ol v-if="diagnostics.events.length" class="events" aria-label="媒体按键事件记录"><li v-for="event in diagnostics.events" :key="event.id"><time>{{ event.time }}</time><b>{{ event.source }}</b><span>{{ event.message }}</span></li></ol>
    <p v-else class="empty">等待操作。清空记录后拨动滚轮，观察这里是否新增“系统媒体指令”。</p>
  </section>
</template>
<style scoped>
.media-key-test{padding:24px;border:1px solid var(--color-border);border-radius:18px;background:var(--color-surface);color:var(--color-text)}h2{margin:0 0 16px}p{line-height:1.7}.facts,.registrations{display:flex;gap:12px 24px;flex-wrap:wrap;margin:16px 0}.facts span,.registrations span{padding:10px;border-radius:8px;background:var(--color-bg)}.buttons{display:flex;gap:10px;flex-wrap:wrap}button{font:inherit;color:inherit;background:var(--color-surface);border:1px solid var(--color-border);border-radius:10px;min-height:44px;padding:10px 16px;cursor:pointer}button:disabled{opacity:.45;cursor:default}.hint,.empty{color:var(--color-text-secondary);font-size:13px}.events{list-style:none;padding:0;max-height:440px;overflow:auto}.events li{display:flex;gap:10px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid var(--color-border);overflow-wrap:anywhere}.events time{font-variant-numeric:tabular-nums;color:var(--color-text-secondary)}.events b{font-size:13px;color:#168fbb}
</style>
