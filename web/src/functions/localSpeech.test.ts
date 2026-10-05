import { afterEach, beforeEach, expect, it, vi } from 'vitest';
let workers: FakeWorker[], starts: number;
class FakeWorker {
  onmessage: ((e: {data:any})=>void)|undefined;
  onerror: (()=>void)|undefined;
  messages:any[]=[];
  constructor(){workers.push(this);}
  postMessage(data:any){this.messages.push(data);}
  terminate(){}
  emit(data:any){this.onmessage?.({data});}
}
beforeEach(()=>{
  vi.resetModules();workers=[];starts=0;
  vi.stubGlobal('Worker',FakeWorker);
  vi.stubGlobal('AudioContext',class {
    state='running';destination={};resume(){return Promise.resolve();}close(){return Promise.resolve();}
    createGain(){return {gain:{value:1,setTargetAtTime:vi.fn()},connect(){},disconnect(){}};}
    createDynamicsCompressor(){return {threshold:{value:0},knee:{value:0},ratio:{value:0},attack:{value:0},release:{value:0},connect(){},disconnect(){}};}
    createBuffer(_channels:number,length:number){return {getChannelData:()=>new Float32Array(length)};}
    createBufferSource(){return {connect(){},disconnect(){},start(){starts++;},stop(){},onended:null};}
  });
});
afterEach(()=>vi.unstubAllGlobals());
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
it('does not play a result after cancellation; reuses its bounded short-phrase cache',async()=>{
  const m=await import('./localSpeech');const playing=m.speakLocal('前方右转');await tick();
  workers[0].emit({type:'ready'});await tick();
  const id=workers[0].messages[0].id;m.stopLocalSpeech();
  workers[0].emit({type:'audio',id,samples:new Float32Array([.1,.2]),sampleRate:22050,ms:5});
  await playing;expect(starts).toBe(0);
  await m.speakLocal('前方右转');expect(starts).toBe(1);expect(workers[0].messages).toHaveLength(1);
  m.releaseLocalSpeech();
});
it('invalidates pending playback when stopped during loading',async()=>{
  const m=await import('./localSpeech');const playing=m.speakLocal('掉头');await tick();m.stopLocalSpeech();
  workers[0].emit({type:'ready'});await playing;
  expect(workers[0].messages).toHaveLength(0);expect(starts).toBe(0);m.releaseLocalSpeech();
});
it('reports initialization errors and permits a new worker retry',async()=>{
  const m=await import('./localSpeech');const first=m.loadLocalSpeech();const check=expect(first).rejects.toThrow('missing');
  workers[0].emit({type:'error',message:'missing'});await check;
  const next=m.loadLocalSpeech();workers[1].emit({type:'ready'});await next;expect(m.localSpeechState.ready).toBe(true);m.releaseLocalSpeech();
});

it('keeps the loaded voice available after one unsupported phrase',async()=>{
  const m=await import('./localSpeech');const loading=m.loadLocalSpeech();
  workers[0].emit({type:'ready'});await loading;
  const first=m.speakLocal('G60');await tick();
  workers[0].emit({type:'error',id:workers[0].messages[0].id,message:'unsupported'});
  await expect(first).rejects.toThrow('unsupported');
  expect(m.localSpeechState.ready).toBe(true);
  const second=m.speakLocal('前方右转');await tick();
  workers[0].emit({type:'audio',id:workers[0].messages[1].id,samples:new Float32Array([.1]),sampleRate:24000,ms:5});
  await second;expect(starts).toBe(1);m.releaseLocalSpeech();
});

it('pre-synthesizes silently and plays cached audio without waiting for another warmup',async()=>{
  const m=await import('./localSpeech');const warm=m.preloadLocalSpeech(['前方右转','请右转']);await tick();
  workers[0].emit({type:'ready'});await tick();
  const first=workers[0].messages[0];expect(first.text).toBe('前方右转');expect(starts).toBe(0);
  workers[0].emit({type:'audio',id:first.id,samples:new Float32Array([.1,.2]),sampleRate:22050,ms:5});await tick();
  expect(workers[0].messages[1].text).toBe('请右转');
  await m.speakLocal('前方右转');expect(starts).toBe(1);expect(m.localSpeechState.cacheHit).toBe(true);
  m.cancelLocalSpeechPreload();
  workers[0].emit({type:'audio',id:workers[0].messages[1].id,samples:new Float32Array([.1]),sampleRate:22050,ms:5});
  await warm;m.releaseLocalSpeech();
});
it('shares an in-flight phrase with playback and cancels obsolete remaining warmups',async()=>{
  const m=await import('./localSpeech');const warm=m.preloadLocalSpeech(['前方左转','请左转']);await tick();
  workers[0].emit({type:'ready'});await tick();
  const playback=m.speakLocal('前方左转');await tick();
  expect(workers[0].messages).toHaveLength(1);m.cancelLocalSpeechPreload();
  workers[0].emit({type:'audio',id:workers[0].messages[0].id,samples:new Float32Array([.1]),sampleRate:22050,ms:5});
  await Promise.all([warm,playback]);expect(starts).toBe(1);expect(workers[0].messages).toHaveLength(1);m.releaseLocalSpeech();
});

it('sends an urgent turn before queued warmups and rejects a turn that is already passed',async()=>{
  const m=await import('./localSpeech');const warm=m.preloadLocalSpeech(['前方左转','请左转']);await tick();
  workers[0].emit({type:'ready'});await tick();
  const first=workers[0].messages[0];
  let relevant=true;
  const urgent=m.speakLocal('前方右转',4000,()=>relevant);await tick();
  expect(workers[0].messages.map(message=>message.text)).toEqual(['前方左转','前方右转']);
  workers[0].emit({type:'audio',id:first.id,samples:new Float32Array([.1]),sampleRate:24000,ms:5});await tick();
  const turn=workers[0].messages[1];
  relevant=false;
  workers[0].emit({type:'audio',id:turn.id,samples:new Float32Array([.1]),sampleRate:24000,ms:5});
  expect(await urgent).toBe(false);expect(starts).toBe(0);
  m.cancelLocalSpeechPreload();
  const remaining=workers[0].messages.find(message=>message.text==='请左转');
  if(remaining)workers[0].emit({type:'audio',id:remaining.id,samples:new Float32Array([.1]),sampleRate:24000,ms:5});
  await warm;m.releaseLocalSpeech();
});
