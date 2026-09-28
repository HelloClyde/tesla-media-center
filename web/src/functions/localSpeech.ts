import { reactive } from 'vue';
export const localSpeechState = reactive({ status:'尚未加载端侧语音', ready:false, loading:false, speaking:false,
  error:'', synthesisMs:0, audioSeconds:0, cacheHit:false });
type Audio = {samples:Float32Array; sampleRate:number; ms:number};
let worker:Worker|undefined, context:AudioContext|undefined, source:AudioBufferSourceNode|undefined;
let loading:Promise<void>|undefined, rejectLoad:((e:Error)=>void)|undefined;
let loadTimer:ReturnType<typeof setTimeout>|undefined;
let sequence=0, request=0;
let tail:Promise<unknown>=Promise.resolve();
const pending=new Map<number,{resolve:(a:Audio)=>void;reject:(e:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
const cache=new Map<string,Audio>();
let cacheBytes=0;
function fail(message:string) {
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
      worker=new Worker('/tts/worker.js?v=3');
      loadTimer=setTimeout(()=>fail('语音资源加载超时，请检查网络后重试'),180000);
      worker.onerror=()=>fail('端侧语音执行失败，请检查 WASM 支持及部署资源');
      worker.onmessage=({data})=>{
        if(data.type==='progress')localSpeechState.status=data.status;
        if(data.type==='ready'){clearTimeout(loadTimer);rejectLoad=undefined;localSpeechState.ready=true;localSpeechState.loading=false;localSpeechState.status='端侧中文语音已就绪';resolve();}
        if(data.type==='error')fail(data.message);
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
    const task=tail.catch(()=>{}).then(async()=>{
      if(token!==sequence||Date.now()-started>maxDelayMs)return;
      let audio=cache.get(value);localSpeechState.cacheHit=!!audio;
      if(!audio){
        localSpeechState.status='正在本地合成语音…';
        audio=await new Promise<Audio>((resolve,reject)=>{
          const id=++request;
          const timer=setTimeout(()=>fail('语音合成超时，此设备可能不适合运行当前模型'),60000);
          pending.set(id,{resolve,reject,timer});worker!.postMessage({type:'speak',id,text:value});
        });
        if(audio.samples.byteLength<8*1024*1024){
          cache.set(value,audio);cacheBytes+=audio.samples.byteLength;
          while(cacheBytes>8*1024*1024||cache.size>24){const key=cache.keys().next().value!;cacheBytes-=cache.get(key)!.samples.byteLength;cache.delete(key);}
        }
      }
      localSpeechState.synthesisMs=audio.ms;localSpeechState.audioSeconds=audio.samples.length/audio.sampleRate;
      if(token!==sequence)return;
      if(Date.now()-started>maxDelayMs){localSpeechState.status='语音已过时，跳过本次播报';return;}
      if(context!.state!=='running')throw new Error('声音通道未启用，请点击语音按钮');
      const buffer=context!.createBuffer(1,audio.samples.length,audio.sampleRate);buffer.getChannelData(0).set(audio.samples);
      source=context!.createBufferSource();source.buffer=buffer;source.connect(context!.destination);
      localSpeechState.speaking=true;localSpeechState.status='正在播放端侧合成语音';
      const current=source;current.onended=()=>{current.disconnect();if(source===current){source=undefined;localSpeechState.speaking=false;localSpeechState.status='播报完成';}};
      current.start();
    });
    tail=task;await task;
  }catch(e){if(token===sequence){localSpeechState.error=e instanceof Error?e.message:String(e);localSpeechState.status=localSpeechState.error;}throw e;}
}
export function releaseLocalSpeech() {
  stopLocalSpeech();fail('语音引擎已释放');localSpeechState.error='';
  void context?.close();context=undefined;cache.clear();cacheBytes=0;
}
