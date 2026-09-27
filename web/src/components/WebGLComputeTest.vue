<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { WebGLBenchmark, type ComputeResult } from '@/functions/webglBenchmark';
const info = ref<ReturnType<WebGLBenchmark['info']>>();
const results = ref<ComputeResult[]>([]), busy = ref(false), message = ref('点击检测能力开始，不会自动运行压力测试。');
const maxSize = ref(256), memoryLimit = ref(32), allocated = ref(0), memoryPassed = ref(false);
let engine: WebGLBenchmark | undefined, generation = 0;
function stop(reason = '测试已停止，GPU 资源已释放') { generation++; engine?.dispose(); engine = undefined; busy.value = false; message.value = reason; }
function prepare() { engine?.dispose(); engine = new WebGLBenchmark(); info.value = engine.info(); return engine; }
function detect() { try { prepare(); message.value = '能力检测完成'; } catch (e) { info.value = undefined; message.value = (e as Error).message; } finally { engine?.dispose(); engine = undefined; } }
async function run(kind: 'compute' | 'memory') {
  if (busy.value) return;
  const id = ++generation; busy.value = true;
  if (kind === 'compute') results.value = []; else { allocated.value = 0; memoryPassed.value = false; }
  try {
    const runner = prepare();
    if (kind === 'compute') {
      for (const size of [64, 128, 256, 512].filter(n => n <= maxSize.value)) {
        message.value = `正在测试 ${size} × ${size} 矩阵…`;
        const result = await runner.compute(size); if (generation !== id) return; results.value.push(result);
        if (result.milliseconds > 250) { message.value = '单次计算超过 250 ms，已提前结束，保留当前结果'; return; }
      }
      message.value = '计算测试完成，所有抽样结果均通过 CPU 对照校验';
    } else {
      message.value = '逐步分配并校验纹理…';
      await runner.memory(memoryLimit.value, value => { if (generation === id) allocated.value = value; });
      if (generation === id) { memoryPassed.value = true; message.value = '纹理分配测试完成，测试资源已释放'; }
    }
  } catch (e) { if (generation === id) message.value = (e as Error).message; }
  finally { if (generation === id) { engine?.dispose(); engine = undefined; busy.value = false; } }
}
const assessment = computed(() => {
  if (!info.value) return '先检测能力，再运行计算测试。';
  if (!info.value.floatTarget) return '此浏览器缺少本测试需要的浮点渲染支持，不能据此确认可运行模型。';
  if (!results.value.length) return '已具备浮点计算接口，仍需完成实测。';
  if (/swiftshader|llvmpipe|software/i.test(info.value.renderer)) return '检测到可能的软件渲染器，当前结果不能代表硬件 GPU 算力。';
  return '已通过基础浮点矩阵计算，可进一步测试小型分类、识别模型。是否能运行目标模型，还取决于算子支持、内存和实际推理延迟。';
});
function hidden() { if (document.hidden) stop('页面进入后台，测试已停止'); }
document.addEventListener('visibilitychange', hidden);
onBeforeUnmount(() => { document.removeEventListener('visibilitychange', hidden); stop(); });
</script>

<template>
  <section class="compute-test">
    <h2>WebGL 算力测试</h2>
    <p>检测浏览器 GPU 的浮点计算能力，帮助评估小模型能否在车机本地运行。建议停车时测试。</p>
    <div class="actions"><button :disabled="busy" @click="detect">检测能力</button><button :disabled="!busy" @click="stop()">停止测试</button></div>
    <dl v-if="info" class="capabilities">
      <div><dt>GPU / 渲染器</dt><dd>{{ info.renderer }}</dd></div>
      <div><dt>WebGL 版本</dt><dd>{{ info.version }}</dd></div>
      <div><dt>浮点渲染</dt><dd>{{ info.floatTarget ? '支持' : '不支持' }} · highp 精度 {{ info.precision }} 位</dd></div>
      <div><dt>最大纹理边长</dt><dd>{{ info.maxTexture }} · 纹理单元 {{ info.textureUnits }}</dd></div>
      <div><dt>GPU 独立计时</dt><dd>{{ info.gpuTimer ? '支持（有效时显示 GPU 吞吐）' : '未开放，仅测端到端耗时' }}</dd></div>
      <div><dt>WebGPU 接口</dt><dd>{{ info.webgpu ? '存在（未验证适配器或推理）' : '未开放' }}</dd></div>
    </dl>
    <div class="test-block"><h3>FP32 矩阵乘法</h3><p>从 64 阶逐步测试，预热后取 5 次中位数，并与 CPU 结果对照。耗时包含 GPU 提交、完成等待和浏览器调度，不代表 GPU 理论峰值或模型推理速度。支持独立 GPU 计时且读数有效时，额外显示排除浏览器调度的 GPU 吞吐。</p>
      <div class="actions"><label>最大矩阵 <select v-model.number="maxSize" :disabled="busy"><option :value="128">128 × 128（轻量）</option><option :value="256">256 × 256（默认）</option><option :value="512">512 × 512</option></select></label><button :disabled="busy" @click="run('compute')">运行计算测试</button></div>
      <div v-if="results.length" class="table-wrap"><table><thead><tr><th>矩阵</th><th>耗时</th><th>有效 GFLOP/s</th><th>GPU GFLOP/s</th><th>最大误差</th></tr></thead><tbody><tr v-for="result in results" :key="result.size"><td>{{ result.size }} × {{ result.size }}</td><td>{{ result.milliseconds.toFixed(2) }} ms</td><td>{{ result.gflops.toFixed(3) }}</td><td>{{ result.gpuGflops?.toFixed(3) ?? '不可用' }}</td><td>{{ result.maxError.toExponential(1) }}</td></tr></tbody></table></div>
    </div>
    <div class="test-block"><h3>纹理分配测试</h3><p>每次增加 4 MiB 并写入、读回校验，结束即释放。浏览器可能使用共享内存或延迟分配，此结果不是显存总量，也不是模型可用内存上限。</p><div class="actions"><label>测试上限 <select v-model.number="memoryLimit" :disabled="busy"><option v-for="size in [16,32,64,128]" :key="size" :value="size">{{ size }} MiB</option></select></label><button :disabled="busy" @click="run('memory')">运行分配测试</button><span>已校验 {{ allocated }} MiB{{ memoryPassed ? ' · 完成' : '' }}</span></div></div>
    <p role="status" class="status">{{ message }}</p>
    <div class="assessment"><strong>小模型可行性</strong><p>{{ assessment }}</p><p>例如 10M 参数权重本身约需 FP32 38 MiB、FP16 19 MiB、INT8 10 MiB，实际还要加中间张量和运行时开销；低位权重也可能被展开。这里尚未执行真实模型，不能推算大语言模型的 tokens/s。</p></div>
  </section>
</template>

<style scoped>
.compute-test{padding:18px;border:1px solid var(--color-border);border-radius:20px;background:var(--color-surface);color:var(--color-text)}h2{margin-top:0}p{color:var(--color-text-soft);line-height:1.65}.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.actions label{display:flex;align-items:center;gap:8px}button,select{min-height:44px;border:1px solid var(--color-border);border-radius:12px;padding:8px 14px;background:var(--color-surface);color:var(--color-text)}button:not(:disabled){cursor:pointer}button:disabled{opacity:.45}.capabilities{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}.capabilities div,.test-block,.assessment{padding:14px;border:1px solid var(--color-border);border-radius:14px}.capabilities dt{font-size:12px;color:var(--color-text-soft)}dd{margin:8px 0 0;overflow-wrap:anywhere}.test-block{margin-top:16px}h3{margin-top:0}.table-wrap{overflow-x:auto;margin-top:16px}table{border-collapse:collapse;width:100%;text-align:left;white-space:nowrap}th,td{padding:12px 10px;border-bottom:1px solid var(--color-border)}.status{color:var(--color-text);overflow-wrap:anywhere}.assessment{margin-top:16px}
</style>
