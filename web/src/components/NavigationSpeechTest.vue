<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
const supported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
const engine = supported ? window.speechSynthesis : undefined;
const voices = ref<SpeechSynthesisVoice[]>([]), selected = ref('');
const text = ref('前方二百米右转，进入长安街。导航语音测试。');
const status = ref(supported ? '等待点击测试' : '浏览器不支持语音合成');
const logs = ref<string[]>([]), state = ref('');
let utterance: SpeechSynthesisUtterance | undefined;
let watchdog: ReturnType<typeof setTimeout> | undefined;
let poll: ReturnType<typeof setInterval> | undefined;
function log(message: string) { logs.value.unshift(`${new Date().toLocaleTimeString()} ${message}`); logs.value = logs.value.slice(0, 20); }
function snapshot() { state.value = engine ? `speaking=${engine.speaking} · pending=${engine.pending} · paused=${engine.paused}` : 'API 不可用'; }
function refresh() {
  voices.value = engine?.getVoices() || [];
  if (selected.value && !voices.value.some(v => v.voiceURI === selected.value)) selected.value = '';
  snapshot();
}
function stop() {
  clearTimeout(watchdog);
  if (utterance) { utterance.onstart = null; utterance.onend = null; utterance.onerror = null; }
  utterance = undefined; engine?.cancel(); snapshot();
}
function play() {
  if (!engine || !text.value.trim()) return;
  stop();
  const current = new SpeechSynthesisUtterance(text.value.trim());
  utterance = current;
  current.lang = 'zh-CN'; current.volume = 1; current.rate = 1;
  current.voice = voices.value.find(v => v.voiceURI === selected.value) || null;
  current.onstart = () => {
    clearTimeout(watchdog); status.value = '浏览器报告已开始播报，请确认是否听到声音'; log('start：语音开始'); snapshot();
    watchdog = setTimeout(() => { status.value = '播报长时间未结束，请停止后重试'; log('30 秒内未收到 end'); }, 30000);
  };
  current.onend = () => { clearTimeout(watchdog); status.value = '浏览器报告播报完成（不代表车内实际有声音）'; log('end：语音结束'); snapshot(); };
  current.onerror = event => { clearTimeout(watchdog); status.value = `播报失败：${event.error}`; log(`error：${event.error}`); snapshot(); };
  status.value = '已提交播报，等待浏览器响应';
  log(`请求中文播报 · ${current.voice?.name || '默认声音（与导航相同）'}`);
  watchdog = setTimeout(() => { status.value = '8 秒内未收到开始或错误回调，语音引擎可能不可用'; log('等待 start 超时'); snapshot(); }, 8000);
  // Keep speak synchronous with the user's click, just as in a gesture test.
  try { engine.speak(current); snapshot(); }
  catch (error) { clearTimeout(watchdog); status.value = `调用失败：${error instanceof Error ? error.message : String(error)}`; log(status.value); }
}
function cancel() { stop(); status.value = '已停止'; log('手动停止'); }
onMounted(() => { refresh(); engine?.addEventListener('voiceschanged', refresh); poll = setInterval(snapshot, 500); });
onBeforeUnmount(() => { stop(); clearInterval(poll); engine?.removeEventListener('voiceschanged', refresh); });
</script>

<template>
  <section class="speech-test">
    <h3>导航语音测试</h3>
    <p>使用与导航相同的浏览器中文语音合成。请先停车，再点击测试。</p>
    <div class="speech-meta">语音 API：{{ supported ? '支持' : '不支持' }} · 可用声音：{{ voices.length }} · 中文声音：{{ voices.filter(v => /^zh|cmn|yue/i.test(v.lang)).length }}</div>
    <label>测试文字<textarea v-model="text" rows="2" maxlength="300" /></label>
    <label>播报声音<select v-model="selected" :disabled="!supported">
      <option value="">默认中文（与导航相同）</option>
      <option v-for="voice in voices" :key="voice.voiceURI" :value="voice.voiceURI">{{ voice.name }} · {{ voice.lang }} · {{ voice.localService ? '本地' : '在线' }}</option>
    </select></label>
    <div class="speech-actions">
      <el-button type="primary" :disabled="!supported || !text.trim()" @click="play">播放导航语音</el-button>
      <el-button :disabled="!supported" @click="cancel">停止语音</el-button>
      <el-button @click="refresh">刷新声音列表</el-button>
    </div>
    <p role="status">{{ status }}</p>
    <small>{{ state }}</small>
    <p v-if="supported && !voices.length">声音列表为空；部分浏览器会延迟加载，也可能没有可用语音引擎。可以刷新后再试。</p>
    <p>如果下方声道测试能发声，而这里无声，问题更可能在浏览器语音引擎。即使出现 start/end，也需要以实际听到声音为准。</p>
    <ol class="speech-logs"><li v-for="(entry, index) in logs" :key="index">{{ entry }}</li></ol>
  </section>
</template>

<style scoped>
.speech-test{padding:18px;margin-bottom:18px;border:1px solid var(--color-border,#dce3eb);border-radius:16px;background:var(--color-surface,#fff)}
h3{margin:0 0 10px}p,.speech-meta{font-size:13px;line-height:1.7;margin:8px 0;color:var(--color-text-soft,#61758a)}
label{display:flex;flex-direction:column;gap:6px;margin:12px 0;font-size:14px}textarea,select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd5df;border-radius:8px;font:inherit;color:var(--color-text,#263d51);background:var(--color-surface,#fff)}
.speech-actions{display:flex;flex-wrap:wrap;gap:8px}.speech-actions .el-button{margin:0;min-height:40px}.speech-logs{max-height:180px;overflow:auto;font-size:12px;padding-left:20px;overflow-wrap:anywhere}small{overflow-wrap:anywhere}
</style>
