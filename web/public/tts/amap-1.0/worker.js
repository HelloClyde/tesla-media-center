/* Browser-only AMap default voice. Models come from the pinned APK at build time. */
const base = '/tts/amap-1.0/';
const cacheName = 'tmc-tts-amap-1.0';
let core;
let loading;

function progress(status) { postMessage({ type: 'progress', status }); }
function cacheStatus(status) { postMessage({ type: 'cache', status }); }

async function asset(name) {
  const url = base + name;
  let cache;
  try {
    cache = await caches.open(cacheName);
    const hit = await cache.match(url);
    if (hit) {
      const data = await hit.arrayBuffer();
      if (data.byteLength) { cacheStatus('高德语音资源已从本地缓存读取'); return data; }
    }
  } catch { /* Storage is optional. */ }
  const response = await fetch(url);
  if (!response.ok) throw Error(`高德语音资源加载失败：${name}（${response.status}）`);
  const data = await response.arrayBuffer();
  if (!data.byteLength) throw Error(`高德语音资源为空：${name}`);
  if (cache) {
    try {
      await cache.put(url, new Response(data));
      cacheStatus('高德语音资源已保存到本地缓存');
    } catch { cacheStatus('语音资源缓存空间不足，下次可能重新下载'); }
  }
  return data;
}

async function init() {
  if (loading) return loading;
  loading = (async () => {
    try {
      progress('加载高德默认语音资源…');
      const [wasm, encoder, decoder, f0, control, dictionary] = await Promise.all([
        asset('amap-mnn.wasm'), asset('am_encoder.mnn'), asset('am_decoder.mnn'),
        asset('ddspganV2_f0.mnn'), asset('ddspganV2_ctrl.mnn'), asset('am_dict.json'),
      ]);
      importScripts(base + 'amap-mnn.js', base + 'amap-core.js');
      progress('初始化本地语音模型…');
      const mnn = await createAmapMnn({ wasmBinary: new Uint8Array(wasm),
        print: () => {}, printErr: message => console.debug('[AMap TTS]', message) });
      const voice = JSON.parse(new TextDecoder().decode(dictionary));
      core = new AmapCore.AmapTtsCore(mnn, voice);
      core.loadModels({ encoder: new Uint8Array(encoder), decoder: new Uint8Array(decoder),
        f0: new Uint8Array(f0), control: new Uint8Array(control) });
      try { await caches.delete('tmc-tts-matcha-1.13.8'); } catch { /* Optional cleanup. */ }
      try { indexedDB.deleteDatabase('tmc-tts-assets'); } catch { /* Optional cleanup. */ }
      postMessage({ type: 'ready' });
    } catch (error) { postMessage({ type: 'error', message: String(error.message || error) }); }
  })();
  return loading;
}

function joinClauses(parts) {
  const pauseSamples = 720;
  const fadeSamples = 480;
  const length = parts.reduce((sum, part) => sum + part.length, 0) + pauseSamples * (parts.length - 1);
  const output = new Float32Array(length);
  let offset = 0;
  for (let index = 0; index < parts.length; index++) {
    const part = parts[index];
    for (let sample = 0; sample < part.length; sample++) {
      const remaining = part.length - sample;
      const gain = remaining < fadeSamples ? remaining / fadeSamples : 1;
      output[offset + sample] = part[sample] * gain;
    }
    offset += part.length + (index < parts.length - 1 ? pauseSamples : 0);
  }
  return output;
}

self.onmessage = ({ data }) => {
  if (data.type !== 'speak' || !core) return;
  try {
    const start = performance.now();
    const clauses = AmapCore.amapTextFrontend(String(data.text).slice(0, 300));
    const samples = joinClauses(clauses.map(clause => core.synthesize(clause)));
    postMessage({ type: 'audio', id: data.id, samples, sampleRate: 24000,
      ms: performance.now() - start }, [samples.buffer]);
  } catch (error) { postMessage({ type: 'error', id: data.id, message: String(error.message || error) }); }
};

void init();
