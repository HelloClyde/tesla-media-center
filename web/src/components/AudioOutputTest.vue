<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
const context = ref<AudioContext>();
const supported = typeof window.AudioContext !== 'undefined';
const error = ref('');
const layout = ref(2), level = ref(8), currentChannel = ref(-1), sequencing = ref(false);
const sampleRate = ref(0), maxChannels = ref(0), outputChannels = ref(0), latency = ref(0);
const labels = computed(() => layout.value === 2 ? ['左声道 L', '右声道 R'] : layout.value === 6 ? ['前左 L', '前右 R', '中置 C', '低频 LFE', '环绕左 SL', '环绕右 SR'] : ['前左 L', '前右 R', '中置 C', '低频 LFE', '侧左 SL', '侧右 SR', '后左 BL', '后右 BR']);
let generation = 0, disposed = false;
let timer: ReturnType<typeof setTimeout> | undefined;
let oscillator: OscillatorNode | undefined, gain: GainNode | undefined, merger: ChannelMergerNode | undefined;
function stopTone() {
  clearTimeout(timer);
  try { oscillator?.stop(); } catch {}
  oscillator?.disconnect(); gain?.disconnect(); merger?.disconnect();
  oscillator = undefined; gain = undefined; merger = undefined; currentChannel.value = -1;
}
function stop() { ++generation; stopTone(); sequencing.value = false; }
async function prepare() {
  if (!supported) throw new Error('当前浏览器不支持 Web Audio 声音测试');
  if (!context.value) context.value = new AudioContext();
  const ctx = context.value;
  await ctx.resume();
  if (ctx.state !== 'running') throw new Error('音频输出未启动，请再次点击检测');
  sampleRate.value = ctx.sampleRate;
  maxChannels.value = ctx.destination.maxChannelCount;
  outputChannels.value = ctx.destination.channelCount;
  latency.value = ctx.baseLatency || 0;
  return ctx;
}
async function detect() {
  stop(); error.value = '';
  try { await prepare(); } catch (e) { if (!disposed) error.value = e instanceof Error ? e.message : '无法检测音频输出'; }
}
function tone(ctx: AudioContext, index: number) {
  stopTone();
  ctx.destination.channelCount = layout.value;
  ctx.destination.channelInterpretation = 'discrete';
  outputChannels.value = ctx.destination.channelCount;
  merger = ctx.createChannelMerger(layout.value);
  merger.channelInterpretation = 'discrete';
  oscillator = ctx.createOscillator(); gain = ctx.createGain();
  oscillator.type = 'sine'; oscillator.frequency.value = layout.value > 2 && index === 3 ? 80 : 440;
  const now = ctx.currentTime;
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(level.value / 100 * .3, now + .06);
  gain.gain.setValueAtTime(level.value / 100 * .3, now + .65);
  gain.gain.linearRampToValueAtTime(0, now + .8);
  oscillator.connect(gain); gain.connect(merger, 0, index); merger.connect(ctx.destination);
  oscillator.start(now); oscillator.stop(now + .85);
  currentChannel.value = index;
}
async function play(index: number, sequence = false) {
  stop(); const id = generation; error.value = '';
  try {
    const ctx = await prepare();
    if (disposed || id !== generation) return;
    if (ctx.destination.maxChannelCount < layout.value) throw new Error(`浏览器最多报告 ${ctx.destination.maxChannelCount} 个输出声道，无法直接测试此布局`);
    sequencing.value = sequence;
    const advance = (next: number) => {
      if (disposed || id !== generation) return;
      try {
        tone(ctx, next);
        timer = setTimeout(() => {
          stopTone();
          if (sequence && next + 1 < layout.value) advance(next + 1);
          else sequencing.value = false;
        }, 1100);
      } catch { stop(); error.value = '当前浏览器不接受此声道布局，请切回双声道'; }
    };
    advance(index);
  } catch (e) { if (!disposed && id === generation) { stop(); error.value = e instanceof Error ? e.message : '声音测试失败'; } }
}
function visibility() { if (document.hidden) stop(); }
document.addEventListener('visibilitychange', visibility);
onBeforeUnmount(() => { disposed = true; stop(); document.removeEventListener('visibilitychange', visibility); void context.value?.close(); });
</script>
<template>
  <section class="audio-test">
    <header><div><h2>声音输出测试</h2><p>先暂停其他音乐，车机音量调低，再逐个试听声道。</p></div><el-button :disabled="!supported" @click="detect">检测输出能力</el-button></header>
    <el-alert v-if="error || !supported" :title="error || '当前浏览器不支持 Web Audio'" type="warning" :closable="false" />
    <div class="capabilities"><div><span>最大输出声道（浏览器报告）</span><strong>{{ maxChannels || '未检测' }}</strong></div><div><span>当前配置声道</span><strong>{{ outputChannels || '未检测' }}</strong></div><div><span>采样率</span><strong>{{ sampleRate ? (sampleRate / 1000) + ' kHz' : '未检测' }}</strong></div><div><span>基础延迟</span><strong>{{ latency ? Math.round(latency * 1000) + ' ms' : '未报告' }}</strong></div></div>
    <div class="test-controls"><el-radio-group v-model="layout" aria-label="测试声道布局" @change="stop"><el-radio-button :value="2">立体声</el-radio-button><el-radio-button :value="6" :disabled="!maxChannels || maxChannels < 6">5.1</el-radio-button><el-radio-button :value="8" :disabled="!maxChannels || maxChannels < 8">7.1</el-radio-button></el-radio-group><el-button type="primary" :disabled="!supported" @click="play(0, true)">{{ sequencing ? '重新依次测试' : '依次测试' }}</el-button><el-button type="danger" plain @click="stop">停止</el-button></div>
    <label class="volume">测试信号强度 {{ level }}%<el-slider v-model="level" :min="1" :max="20" aria-label="测试音量" @change="stop" /></label>
    <div class="channels"><button v-for="(label, index) in labels" :key="label" :class="{ sounding: currentChannel === index }" :disabled="!supported" @click="play(index)"><span>{{ index + 1 }}</span><strong>{{ label }}</strong><small>{{ currentChannel === index ? '正在发声…' : '点击试听' }}</small></button></div>
    <p class="test-status" role="status">{{ currentChannel >= 0 ? '正在测试：' + labels[currentChannel] : '测试已停止' }}</p>
    <p class="note">每次播放约 0.8 秒测试音，不需要麦克风权限。切换 Tab、离开页面或隐藏页面时自动停止。5.1 / 7.1 按标准声道顺序送出，标签表示目标通道；车机仍可能将信号混合到其他扬声器。</p>
    <p class="note">浏览器报告的声道数不等于车内喇叭数量，也不能证明每个喇叭可独立控制。请结合实际听到的位置判断；最大声道为 2 时，只能直接测试左右声道。</p>
  </section>
</template>
<style scoped>
.audio-test{padding:16px;color:var(--color-text)}header{display:flex;align-items:center;justify-content:space-between;gap:16px}h2{font-size:22px;margin:0 0 8px}header p,.note{font-size:13px;color:var(--color-text-soft);line-height:1.7}.capabilities{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0}.capabilities>div{padding:14px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface)}.capabilities span{font-size:12px;color:var(--color-text-soft);display:block}.capabilities strong{display:block;font-size:20px;margin-top:10px}.test-controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px}.test-controls .el-button{margin:0}.volume{display:block;max-width:340px;font-size:13px;margin:18px 0}.channels{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}.channels button{border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);color:inherit;padding:20px 12px;cursor:pointer;display:flex;flex-direction:column;gap:10px;align-items:center}.channels button>span{display:grid;place-items:center;border-radius:50%;width:30px;height:30px;background:#409eff18;color:#409eff}.channels small{color:var(--color-text-soft)}.channels .sounding{border-color:#19b978;background:#19b97818}.test-status{font-size:14px;color:#159966}.note{margin-bottom:0}@media(max-width:600px){header{align-items:flex-start;flex-direction:column}.capabilities{grid-template-columns:repeat(2,minmax(0,1fr))}.audio-test{padding:8px}}
</style>
