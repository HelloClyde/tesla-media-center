import { navigationVoiceVolume } from './navigationVolume';
import { reactive, watch } from 'vue';
export const localSpeechState = reactive({ status:'尚未加载端侧语音', ready:false, loading:false, speaking:false,
  error:'', modelCacheStatus:'', synthesisMs:0, audioSeconds:0, cacheHit:false });
type Audio = {samples:Float32Array; sampleRate:number; ms:number};
let worker:Worker|undefined, context:AudioContext|undefined, source:AudioBufferSourceNode|undefined;
let voiceGain:GainNode|undefined, limiter:DynamicsCompressorNode|undefined;
watch(navigationVoiceVolume, value => {
  if (voiceGain && context) voiceGain.gain.setTargetAtTime(value / 100, context.currentTime, .03);
}, { flush:'sync' });
let loading:Promise<void>|undefined, rejectLoad:((e:Error)=>void)|undefined;
let loadTimer:ReturnType<typeof setTimeout>|undefined;
let sequence=0, request=0;
let tail:Promise<unknown>=Promise.resolve();
const pending=new Map<number,{resolve:(a:Audio)=>void;reject:(e:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
const cache=new Map<string,Audio>();
let cacheBytes=0, preloadSequence=0, engineGeneration=0;
const synthesizing=new Map<string,Promise<Audio>>();
const phrase=(text:string)=>text.trim().slice(0,300);
function synthesize(value:string):Promise<Audio> {
  const cached=cache.get(value);if(cached)return Promise.resolve(cached);
  const existing=synthesizing.get(value);if(existing)return existing;
  const engine=engineGeneration;
  const task=tail.catch(()=>{}).then(async()=>{
    if(engine!==engineGeneration)throw new Error('语音任务已取消');
    await loadLocalSpeech();
    if(engine!==engineGeneration)throw new Error('语音任务已取消');
    const audio=await new Promise<Audio>((resolve,reject)=>{
      const id=++request;
      const timer=setTimeout(()=>fail('语音合成超时，此设备可能不适合运行当前模型'),60000);
      pending.set(id,{resolve,reject,timer});worker!.postMessage({type:'speak',id,text:value});
    });
    if(audio.samples.byteLength<8*1024*1024){
      cache.set(value,audio);cacheBytes+=audio.samples.byteLength;
      while(cacheBytes>8*1024*1024||cache.size>24){const key=cache.keys().next().value!;cacheBytes-=cache.get(key)!.samples.byteLength;cache.delete(key);}
    }
    return audio;
  });
  synthesizing.set(value,task);tail=task;
  const clean=()=>{if(synthesizing.get(value)===task)synthesizing.delete(value);};
  void task.then(clean,clean);
  return task;
}
export function cancelLocalSpeechPreload(){preloadSequence++;}
/** Synthesize silently; never creates or resumes an audio output context. */
export async function preloadLocalSpeech(texts:string[]) {
  const token=++preloadSequence;
  await loadLocalSpeech();
  for(const value of [...new Set(texts.map(phrase).filter(Boolean))].slice(0,6)){
    if(token!==preloadSequence)return;
    await synthesize(value);
  }
}
function fail(message:string) {
  engineGeneration++;
  const error=new Error(message);
  clearTimeout(loadTimer);rejectLoad?.(error);rejectLoad=undefined;
  pending.forEach(p=>{clearTimeout(p.timer);p.reject(error);});pending.clear();
  worker?.terminate();worker=undefined;loading=undefined;
  localSpeechState.ready=false;localSpeechState.loading=false;localSpeechState.error=message;localSpeechState.status=message;
}
export function loadLocalSpeech():Promise<void> {
  if(localSpeechState.ready)return Promise.resolve();
  if(loading)return loading;
  localSpeechState.loading=true;localSpeechState.error='';localSpeechState.status='加载端侧中文语音资源…';
  loading=new Promise<void>((resolve,reject)=>{
    rejectLoad=reject;
    try {
      worker=new Worker('/tts/amap-1.0/worker.js?v=1');
      loadTimer=setTimeout(()=>fail('语音资源加载超时，请检查网络后重试'),180000);
      worker.onerror=()=>fail('端侧语音执行失败，请检查 WASM 支持及部署资源');
      worker.onmessage=({data})=>{
        if(data.type==='cache')localSpeechState.modelCacheStatus=data.status;
        if(data.type==='progress')localSpeechState.status=data.status;
        if(data.type==='ready'){clearTimeout(loadTimer);rejectLoad=undefined;localSpeechState.ready=true;localSpeechState.loading=false;localSpeechState.status='端侧中文语音已就绪';resolve();}
        if(data.type==='error'){
          const p=typeof data.id==='number'?pending.get(data.id):undefined;
          if(p){pending.delete(data.id);clearTimeout(p.timer);p.reject(new Error(data.message));}
          else if(typeof data.id!=='number')fail(data.message);
        }
        if(data.type==='audio'){
          const p=pending.get(data.id);if(!p)return;pending.delete(data.id);clearTimeout(p.timer);
          if(!data.samples?.length||!Number.isFinite(data.sampleRate)||data.sampleRate<=0){p.reject(new Error('语音合成结果为空'));return;}
          p.resolve(data);
        }
      };
    }catch(e){queueMicrotask(()=>fail(e instanceof Error?e.message:String(e)));}
  });
  return loading;
}
/** Call during a user gesture to unlock audio before asynchronous model loading. */
export async function prepareLocalSpeech() {
  context ||= new AudioContext();
  if (!voiceGain) {
    voiceGain=context.createGain();voiceGain.gain.value=navigationVoiceVolume.value/100;
    limiter=context.createDynamicsCompressor();
    limiter.threshold.value=-3;limiter.knee.value=0;limiter.ratio.value=20;
    limiter.attack.value=.003;limiter.release.value=.15;
    voiceGain.connect(limiter);limiter.connect(context.destination);
  }
  await context.resume();
  if(context.state!=='running')throw new Error('请点击语音按钮启用声音播放');
  await loadLocalSpeech();
}
export function stopLocalSpeech() {
  sequence++;
  if(source){source.onended=null;try{source.stop();}catch{}source.disconnect();source=undefined;}
  localSpeechState.speaking=false;
  if(localSpeechState.ready)localSpeechState.status='已停止';
}
export async function speakLocal(text:string, maxDelayMs=Infinity) {
  stopLocalSpeech();const token=sequence, started=Date.now();
  const value=text.trim().slice(0,300);if(!value)return;
  localSpeechState.error='';
  try {
    await prepareLocalSpeech();
    if(token!==sequence||Date.now()-started>maxDelayMs)return;
    localSpeechState.cacheHit=cache.has(value);
    if(!localSpeechState.cacheHit)localSpeechState.status='正在本地合成语音…';
    const audio=await synthesize(value);
      localSpeechState.synthesisMs=audio.ms;localSpeechState.audioSeconds=audio.samples.length/audio.sampleRate;
      if(token!==sequence)return;
      if(Date.now()-started>maxDelayMs){localSpeechState.status='语音已过时，跳过本次播报';return;}
      if(context!.state!=='running')throw new Error('声音通道未启用，请点击语音按钮');
      const buffer=context!.createBuffer(1,audio.samples.length,audio.sampleRate);buffer.getChannelData(0).set(audio.samples);
      source=context!.createBufferSource();source.buffer=buffer;source.connect(voiceGain!);
      localSpeechState.speaking=true;localSpeechState.status='正在播放端侧合成语音';
      const current=source;current.onended=()=>{current.disconnect();if(source===current){source=undefined;localSpeechState.speaking=false;localSpeechState.status='播报完成';}};
      current.start();
  }catch(e){if(token===sequence){localSpeechState.error=e instanceof Error?e.message:String(e);localSpeechState.status=localSpeechState.error;}throw e;}
}
export function releaseLocalSpeech() {
  cancelLocalSpeechPreload();stopLocalSpeech();fail('语音引擎已释放');synthesizing.clear();localSpeechState.error='';
  voiceGain?.disconnect();limiter?.disconnect();voiceGain=undefined;limiter=undefined;
  void context?.close();context=undefined;cache.clear();cacheBytes=0;
}
