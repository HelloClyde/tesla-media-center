/* TMC adapter for the pinned sherpa-onnx browser runtime. Inference stays off the UI thread. */
const base = '/tts/matcha-1.13.8-q8-v1/';
let tts;
const progress = status => postMessage({type:'progress', status});
// IndexedDB also works when Cache Storage is unavailable (for example on HTTP).
function modelStore(url, data) {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open('tmc-tts-assets', 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore('assets');
    opening.onerror = () => reject(opening.error);
    opening.onblocked = () => reject(Error('语音缓存数据库被占用'));
    opening.onsuccess = () => {
      const db = opening.result;
      const tx = db.transaction('assets', data ? 'readwrite' : 'readonly');
      const request = data ? tx.objectStore('assets').put(data, url) : tx.objectStore('assets').get(url);
      tx.oncomplete = () => { db.close(); resolve(request.result); };
      tx.onerror = tx.onabort = () => { db.close(); reject(tx.error || Error('语音缓存读写失败')); };
    };
  });
}
let cacheFailed = false;
function cacheStatus(status, failed = false) {
  cacheFailed ||= failed;
  postMessage({type:'cache', status:cacheFailed ? '模型缓存未完整保存，下次可能重新下载；请检查浏览器存储空间或站点数据设置' : status});
}
async function asset(name) {
  const url = base + name;
  let cache;
  try {
    cache = await caches.open('tmc-tts-matcha-1.13.8');
    const hit = await cache.match(url);
    if (hit) {
      const data = await hit.arrayBuffer();
      if (data.byteLength) { progress('读取本地语音缓存'); cacheStatus('模型资源已从本地缓存读取'); return data; }
    }
  } catch { /* Fall back to IndexedDB. */ }
  try {
    const hit = await modelStore(url);
    if (hit instanceof ArrayBuffer && hit.byteLength) {
      progress('读取本地语音缓存'); cacheStatus('模型资源已从本地缓存读取（IndexedDB）'); return hit;
    }
  } catch { /* Download remains available if storage is disabled. */ }
  const response = await fetch(url);
  if (!response.ok) throw Error('语音资源加载失败（' + response.status + '），请检查部署资源');
  // Compressed Content-Length is not the size of the decompressed stream.
  const total = response.headers.get('Content-Encoding') ? 0 : Number(response.headers.get('Content-Length'));
  let data;
  if (response.body && total > 0) {
    const reader=response.body.getReader(), chunks=[];let length=0;
    for (;;) { const {done,value}=await reader.read();if(done)break;chunks.push(value);length+=value.length;
      progress('加载语音资源 ' + (length/1048576).toFixed(1) + ' / ' + (total/1048576).toFixed(1) + ' MiB'); }
    data=new Uint8Array(length);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
    data=data.buffer;
  } else data=await response.arrayBuffer();
  if (!data.byteLength) throw Error('语音资源为空，请重试');
  let saved = false;
  if (cache) {
    try { await cache.put(url, new Response(data)); saved = true; } catch { /* Try IndexedDB. */ }
  }
  if (!saved) {
    try { await modelStore(url, data); saved = true; } catch { /* Report persistence failure below. */ }
  }
  cacheStatus(saved ? '模型资源已保存到本地，下次无需重新下载' : '', !saved);
  return data;
}
async function init() {
  try {
    // Retire only this app's obsolete full-size voice assets.
    try {
      const cache = await caches.open('tmc-tts-matcha-1.13.8');
      for (const entry of await cache.keys()) {
        if (new URL(entry.url).pathname.startsWith('/tts/matcha-1.13.8/')) await cache.delete(entry);
      }
    } catch { /* Cache Storage is optional. */ }
    const data = await asset('sherpa-onnx-wasm-main-tts.data');
    const wasm = await asset('sherpa-onnx-wasm-main-tts.wasm');
    progress('初始化本地中文语音引擎');
    self.Module = {
      locateFile: name => base + name,
      wasmBinary: wasm,
      getPreloadedPackage: () => data,
      print: () => {}, printErr: message => console.debug('[TTS]',message),
      onAbort: () => postMessage({type:'error', message:'本地语音引擎启动失败，可能不支持 WASM SIMD 或内存不足'}),
      onRuntimeInitialized() {
        try { tts=createOfflineTts(self.Module);postMessage({type:'ready'}); }
        catch(e){postMessage({type:'error',message:String(e.message||e)});}
      },
    };
    importScripts(base+'sherpa-onnx-tts.js');
    importScripts(base+'sherpa-onnx-wasm-main-tts.js');
  } catch(e) {postMessage({type:'error',message:String(e.message||e)});}
}
self.onmessage = ({data}) => {
  if(data.type!=='speak'||!tts)return;
  try {
    const start=performance.now();
    const audio=tts.generate({text:String(data.text).slice(0,300),sid:0,speed:1});
    postMessage({type:'audio',id:data.id,samples:audio.samples,sampleRate:tts.sampleRate,ms:performance.now()-start},[audio.samples.buffer]);
  }catch(e){postMessage({type:'error',id:data.id,message:String(e.message||e)});}
};
void init();
