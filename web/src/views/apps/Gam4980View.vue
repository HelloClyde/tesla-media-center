<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { readSave, uploadSave } from './gam4980Saves';
import { gamepadKeys, createGamepadRepeater } from './gam4980Gamepad';
import { FolderOpened, VideoPlay, VideoPause, Download, RefreshRight } from '@element-plus/icons-vue';
type LibraryItem={type:'dir'|'file';name:string;path:string;size?:number;playable?:boolean;url?:string};
const view=ref<'library'|'player'>('library'), library=ref<LibraryItem[]>([]), directory=ref(''), rootPath=ref(''), search=ref(''), listing=ref(false), libraryError=ref(''), uploading=ref(false), uploadStatus=ref(''), downloading=ref(false);
const filteredGames=computed(()=>library.value.filter(item=>item.name.toLowerCase().includes(search.value.toLowerCase())));
let libraryRequest:AbortController|undefined, downloadRequest:AbortController|undefined;
async function listGames(path=''){
  libraryRequest?.abort();const controller=new AbortController();libraryRequest=controller;listing.value=true;libraryError.value='';
  try{const response=await fetch('/api/gam4980/list?path='+encodeURIComponent(path),{signal:controller.signal});if(!response.ok)throw Error(response.status===404?'游戏目录不存在，或服务器尚未更新游戏库接口':response.status===403?'服务器拒绝访问此目录':response.status>=500?'服务器游戏库服务不可用（HTTP '+response.status+'），请检查后端是否启动':'读取游戏目录失败（HTTP '+response.status+'）');const result=await response.json();if(result.status!=='ok')throw Error(result.status==='need_login'?'登录已失效，请重新登录':'读取游戏目录失败');if(controller.signal.aborted)return;library.value=result.data.items;directory.value=result.data.path;rootPath.value=result.data.rootPath;search.value='';}
  catch(e){if(!controller.signal.aborted)libraryError.value=e instanceof TypeError?'无法连接服务器，请检查后端服务和网络':(e as Error).message;}
  finally{if(libraryRequest===controller)listing.value=false;}
}
const uploadPicker=ref<HTMLInputElement>();
async function uploadGames(event:Event){
  const input=event.target as HTMLInputElement, files=Array.from(input.files||[]);input.value='';
  if(!files.length||uploading.value)return;
  uploading.value=true;libraryError.value='';uploadStatus.value='';
  let count=0;const failures:string[]=[];
  for(const file of files){
    if(disposed)break;
    uploadStatus.value='正在上传 '+file.name;
    if(!file.name.toLowerCase().endsWith('.gam')||file.size<0x46||file.size>0x1e0000){failures.push(file.name+'：文件格式或大小不支持');continue;}
    try{const response=await fetch('/api/gam4980/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const result=await response.json();if(!response.ok||result.status!=='ok')throw Error(result.status==='need_login'?'请重新登录':result.message||'上传失败');count++;}
    catch(e){failures.push(file.name+'：'+(e as Error).message);}
  }
  if(!disposed){await listGames();uploadStatus.value=count?'已上传 '+count+' 个游戏':'';libraryError.value=failures.join('；');uploading.value=false;}
}
async function selectGame(item:LibraryItem){
  if(item.type==='dir'){await listGames(item.path);return;}
  if(!item.playable||downloading.value)return;
  downloadRequest?.abort();const controller=new AbortController();downloadRequest=controller;downloading.value=true;libraryError.value='';
  try{const r=await fetch(item.url!,{signal:controller.signal});if(!r.ok)throw Error('下载游戏失败，请刷新目录重试');const blob=await r.blob();if(disposed||controller.signal.aborted)return;await load(new File([blob],item.name));}
  catch(e){if(!controller.signal.aborted)libraryError.value=e instanceof TypeError?'无法连接服务器，请检查后端服务和网络':(e as Error).message;}
  finally{if(downloadRequest===controller)downloading.value=false;}
}
function backToLibrary(){pause();retire();ready.value=false;view.value='library';void listGames(directory.value);}
const canvas=ref<HTMLCanvasElement>();
const picker=ref<HTMLInputElement>();
const savePicker=ref<HTMLInputElement>();
const title=ref('GAM4980'), status=ref('打开本地 .gam 游戏'), error=ref(''), syncError=ref('');
const ready=ref(false), playing=ref(false), loading=ref(false), keyboard=ref(false), theme=ref(0);
const gamepadName=ref(''), gamepadIssue=ref('');
const padRepeater=createGamepadRepeater();
let padFrame=0, padIdentity='', padArmed=false, startHeld=false;
function pollGamepad(now:number){
  if(disposed)return;
  try{
    if(!navigator.getGamepads){gamepadIssue.value='此浏览器不支持手柄';return;}
    const pad=Array.from(navigator.getGamepads()).find(p=>p?.connected);
    const identity=pad?`${pad.index}/${pad.id}`:'';
    if(identity!==padIdentity){padRepeater.reset();padArmed=false;startHeld=false;padIdentity=identity;}
    gamepadName.value=pad?.id||'';
    gamepadIssue.value=pad&&pad.mapping!=='standard'?'非标准手柄，按键位置可能不同':'';
    if(pad){
      const keys=gamepadKeys(pad),start=!!pad.buttons[9]?.pressed;
      if(document.hidden||!document.hasFocus()||!ready.value){padArmed=false;padRepeater.reset();}
      else {
        if(!keys.size&&!start)padArmed=true;
        if(padArmed){
          if(start&&!startHeld)toggle();
          if(playing.value){for(const code of padRepeater.update(keys,now))key(code);}
          else padRepeater.reset();
        }
      }
      startHeld=start;
    }
  }catch{gamepadIssue.value='浏览器未开放手柄访问，请使用 HTTPS 或本机地址';}
  padFrame=requestAnimationFrame(pollGamepad);
}
let exportPending=false;
let worker:Worker|undefined, file:File|undefined, saveKey='', saved:Uint8Array|undefined, disposed=false, loadId=0;
const controls=[{label:'上',key:0x35,area:'up'},{label:'左',key:0x37,area:'left'},{label:'下',key:0x38,area:'down'},{label:'右',key:0x39,area:'right'}];
const letters='12345678QWERTYUIASDFGHJK'.split('').map((label,i)=>({label,key:i+8}));
const extra=[{label:'9',key:0x30},{label:'0',key:0x31},{label:'O',key:0x32},{label:'P',key:0x33},{label:'L',key:0x34},...'ZXCVBNM'.split('').map((label,i)=>({label,key:0x21+i})),{label:'空格',key:0x36},{label:'Shift',key:0x28},{label:'帮助',key:0x29},{label:'菜单',key:1},{label:'翻页↑',key:0x3a},{label:'翻页↓',key:0x3b}];
const keyMap:Record<string,number>={ArrowUp:0x35,ArrowDown:0x38,ArrowLeft:0x37,ArrowRight:0x39,Enter:0x2f,Escape:0x2e,' ':0x36,Shift:0x28,PageUp:0x3a,PageDown:0x3b};
for(const item of [...letters,...extra])if(item.label.length===1)keyMap[item.label.toLowerCase()]=item.key;
function key(code:number){worker?.postMessage({type:'key',key:code});}
function onKey(e:KeyboardEvent){if(!playing.value || (e.target instanceof HTMLElement && ['INPUT','SELECT','TEXTAREA','BUTTON'].includes(e.target.tagName)))return;const code=keyMap[e.key]??keyMap[e.key.toLowerCase()];if(code!==undefined){e.preventDefault();key(code);}}
let held:ReturnType<typeof setInterval>|undefined;
function release(){if(held)clearInterval(held);held=undefined;}
function press(code:number){release();key(code);held=setInterval(()=>key(code),110);}
function pause(){padArmed=false;padRepeater.reset();release();playing.value=false;worker?.postMessage({type:'pause'});}
function visibility(){if(document.hidden)pause();}
function toggle(){if(!ready.value)return;playing.value=!playing.value;worker?.postMessage({type:playing.value?'play':'pause'});if(playing.value)canvas.value?.focus({preventScroll:true});}
async function store(bytes:Uint8Array, name:string){
  try{await uploadSave(name,bytes);if(!disposed){status.value='存档已同步到服务器';syncError.value='';}}
  catch(e){if(!disposed)syncError.value=(e as Error).message;throw e;}
}
function retire():Promise<void>{
  const old=worker;worker=undefined;
  if(!old)return Promise.resolve();
  return new Promise(resolve=>{
    const finish=()=>{clearTimeout(timeout);old.terminate();resolve();};
    const timeout=setTimeout(finish,2000);
    old.addEventListener('message',({data})=>{if(data.type==='retired')finish();});
    old.postMessage({type:'retire'});
  });
}
async function load(selected:File, reset=false){
  if(!selected.name.toLowerCase().endsWith('.gam')||selected.size<0x46||selected.size>0x1e0000){error.value='请选择 70 字节至 1.875 MB 的 .gam 文件';return;}
  view.value='player';const id=++loadId;pause();await retire();if(disposed||id!==loadId)return;ready.value=false;loading.value=true;error.value='';file=selected;title.value=selected.name;status.value='正在启动模拟器…';
  try{
    const game=await selected.arrayBuffer();
    // A content hash keeps saves separate even when different games share a name.
    // Use the same key over HTTP (car browser) and HTTPS, including older browser saves.
    let a=2166136261,b=5381;for(const v of new Uint8Array(game)){a=Math.imul(a^v,16777619);b=Math.imul(b,33)^v;}
    const hash=`${selected.size}-${a>>>0}-${b>>>0}`;
    if(crypto.subtle){
      const legacyHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',game)),v=>v.toString(16).padStart(2,'0')).join('');
      try{const old=localStorage.getItem('tmc:gam4980:save:'+legacyHash);if(old&&!localStorage.getItem('tmc:gam4980:save:'+hash))localStorage.setItem('tmc:gam4980:save:'+hash,old);}catch{/* Optional legacy backup. */}
    }
    if(disposed||id!==loadId)return;
    saveKey='tmc:gam4980:save:'+hash;saved=undefined;
    if(!reset)saved=await readSave(saveKey);
    if(disposed||id!==loadId)return;
    const current=new Worker('/gam4980/player-worker.js');worker=current;const currentSaveKey=saveKey;
    const deadline=setTimeout(()=>{if(worker===current&&loading.value){current.terminate();loading.value=false;error.value='启动超时，请检查运行资源后重试';}},30000);
    current.onerror=()=>{clearTimeout(deadline);if(worker===current){error.value='模拟线程异常，请重新打开游戏';loading.value=false;pause();current.terminate();}};
    current.onmessage=({data})=>{
      if(data.type==='save'){void store(data.bytes,currentSaveKey).catch(()=>{});if(worker===current){saved=data.bytes;if(exportPending){exportPending=false;downloadSave(data.bytes);}}return;}
      if(disposed||worker!==current)return;
      if(data.type==='frame'){
        const ctx=canvas.value?.getContext('2d');if(!ctx)return;const image=ctx.createImageData(159,96);
        for(let y=0;y<96;y++)for(let x=0;x<159;x++){const value=data.frame[y*160+x],i=(y*159+x)*4;image.data[i]=((value>>11)&31)*255/31;image.data[i+1]=((value>>5)&63)*255/63;image.data[i+2]=(value&31)*255/31;image.data[i+3]=255;}
        ctx.putImageData(image,0,0);
      }else if(data.type==='ready'){clearTimeout(deadline);ready.value=true;loading.value=false;status.value='存档自动同步到服务器';if(!document.hidden){playing.value=true;current.postMessage({type:'play'});canvas.value?.focus({preventScroll:true});}}
      else if(data.type==='stopped'){playing.value=false;status.value='游戏已退出，可重新启动';}
      else if(data.type==='error'){clearTimeout(deadline);error.value=data.message;loading.value=false;playing.value=false;}
    };
    current.postMessage({type:'load',game,save:saved,theme:theme.value},[game]);
  }catch(e){if(id===loadId&&!disposed){error.value=(e as Error).message||'无法读取游戏文件';loading.value=false;}}
}
function choose(e:Event){const input=e.target as HTMLInputElement;const selected=input.files?.[0];if(selected)void load(selected);input.value='';}
function exportSave(){exportPending=true;worker?.postMessage({type:'save'});}
function downloadSave(bytes:Uint8Array){const url=URL.createObjectURL(new Blob([new Uint8Array(bytes)],{type:'application/octet-stream'}));const a=document.createElement('a');a.href=url;a.download=title.value+'.sav';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

async function importSave(e:Event){
  const input=e.target as HTMLInputElement, selected=input.files?.[0];input.value='';
  if(!selected||!file)return;
  if(selected.size!==0x14000){error.value='存档应为 80 KB 的 GAM4980 .sav 文件';return;}
  pause();await retire();
  const bytes=new Uint8Array(await selected.arrayBuffer());
  if(disposed)return;
  try{await store(bytes,saveKey);await load(file);}catch{/* Keep backup and show sync failure. */}
}
onMounted(()=>{void listGames();padFrame=requestAnimationFrame(pollGamepad);document.addEventListener('pointerup',release);document.addEventListener('pointercancel',release);document.addEventListener('keydown',onKey);document.addEventListener('visibilitychange',visibility);window.addEventListener('blur',pause);});
onBeforeUnmount(()=>{disposed=true;libraryRequest?.abort();downloadRequest?.abort();cancelAnimationFrame(padFrame);padRepeater.reset();loadId++;release();retire();document.removeEventListener('pointerup',release);document.removeEventListener('pointercancel',release);document.removeEventListener('keydown',onKey);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('blur',pause);});
</script>

<template>
  <section v-if="view==='library'" class="gam-player gam-library">
    <header class="gam-header"><div><small>经典掌机 · GAM4980</small><h1>游戏库</h1></div><button :disabled="uploading" @click="uploadPicker?.click()">{{ uploading?'上传中…':'上传游戏' }}</button><input ref="uploadPicker" hidden type="file" accept=".gam" multiple @change="uploadGames" /></header>

    <div class="library-tools"><button :disabled="!directory||listing||downloading" @click="listGames(directory.split('/').slice(0,-1).join('/'))">返回上级</button><span>{{ directory || '全部游戏' }}</span><input v-model="search" aria-label="搜索游戏" placeholder="搜索当前目录" /><button :disabled="listing||downloading" @click="listGames(directory)">刷新</button></div>
    <p class="library-path">服务器目录：{{ rootPath || 'data/gam4980' }}</p>
    <p v-if="uploadStatus" role="status">{{ uploadStatus }}</p>
    <p v-if="listing||downloading" role="status">{{ downloading?'正在下载游戏…':'正在读取游戏目录…' }}</p>
    <p v-if="libraryError" role="alert" class="gam-error">{{ libraryError }}</p>
    <div v-if="!listing" class="library-grid"><button v-for="item in filteredGames" :key="item.path" class="library-card" :disabled="downloading || (item.type==='file'&&!item.playable)" @click="selectGame(item)"><FolderOpened v-if="item.type==='dir'"/><VideoPlay v-else/><strong>{{ item.name }}</strong><small>{{ item.type==='dir'?'文件夹':item.playable?((item.size||0)/1024).toFixed(0)+' KB':'文件大小不支持' }}</small></button></div>
    <p v-if="!listing&&!libraryError&&!filteredGames.length" class="library-empty">{{ search?'没有找到匹配的游戏':'点击上传游戏，将 .gam 文件添加到游戏库' }}</p>
    <footer>游戏文件仅在本机运行 · 暂不支持声音 <a href="https://github.com/HelloClyde/BBK9588-gam4980" target="_blank" rel="noopener">原项目</a><a href="/gam4980/source.zip">核心源码</a><a href="/gam4980/COPYING" target="_blank">GPL-3.0</a></footer>
  </section>
  <section v-else class="gam-player gam-playing">
    <header class="gam-header"><button @click="backToLibrary">返回游戏库</button><div><small>经典掌机 · GAM4980</small><h1>{{ title }}</h1></div><button class="open-game" :disabled="loading" @click="picker?.click()"><FolderOpened />打开游戏</button><input ref="picker" hidden type="file" accept=".gam" @change="choose" /></header>
    <div class="gam-layout">
      <div class="gam-device"><div class="lcd-frame"><canvas ref="canvas" tabindex="0" width="159" height="96" aria-label="GAM4980 游戏画面" /><div v-if="!ready" class="lcd-placeholder"><strong>{{ loading?'启动中…':'GAM4980' }}</strong><span>{{ loading?'正在加载运行核心':'选择 .gam 文件，重温经典' }}</span></div></div>

      </div>
      <div class="gam-controls"><div class="dpad"><button v-for="button in controls" :key="button.key" :style="{gridArea:button.area}" :disabled="!playing" @pointerdown.prevent="press(button.key)">{{ button.label }}</button></div><div class="action-keys"><button :disabled="!playing" @pointerdown.prevent="press(0x2e)">退出</button><button class="confirm" :disabled="!playing" @pointerdown.prevent="press(0x2f)">确定</button></div><p>方向键移动 · Enter 确定 · Esc 返回</p></div>
    </div>
        <div class="gam-toolbar"><button :disabled="!ready" :aria-label="playing?'暂停':'继续'" @click="toggle"><VideoPause v-if="playing"/><VideoPlay v-else /></button><button :disabled="!ready" aria-label="重新启动" @click="file && load(file)"><RefreshRight /></button><button :disabled="!ready" aria-label="导出存档" @click="exportSave"><Download /></button><button :disabled="!ready" @click="savePicker?.click()">导入存档</button><input ref="savePicker" type="file" accept=".sav" hidden @change="importSave" /><select v-model="theme" aria-label="屏幕颜色" @change="worker?.postMessage({type:'theme',theme})"><option :value="0">灰白</option><option :value="1">经典绿</option><option :value="2">冰蓝</option><option :value="3">暖黄</option></select><button :aria-expanded="keyboard" @click="keyboard=!keyboard">键盘</button></div>
    <div v-if="keyboard" class="gam-keyboard"><button v-for="button in [...letters,...extra]" :key="button.key" :disabled="!playing" @pointerdown.prevent="press(button.key)">{{ button.label }}</button></div>
    <div class="gam-gamepad"><span :title="gamepadName" :class="{connected:gamepadName}">{{ gamepadName ? '手柄已连接' : '连接手柄后按任意键识别' }}</span><small>{{ gamepadIssue || '十字键 / 左摇杆移动 · A 确定 · B 返回 · Start 暂停/继续 · Select 菜单 · X 空格 · Y 帮助 · L/R 翻页' }}</small></div>
    <p class="gam-status" role="status">{{ status }}{{ ready&&!playing?' · 已暂停':'' }}</p><p v-if="error||syncError" class="gam-error" role="alert">{{ error||syncError }}</p>

  </section>
</template>

<style scoped>
.library-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.library-tools span{flex:1;overflow-wrap:anywhere}.library-tools input,.library-settings input{min-height:44px;border:1px solid var(--color-border);border-radius:12px;padding:10px 12px;background:var(--color-surface);color:var(--color-text);min-width:0}.library-settings{display:flex;align-items:end;gap:12px;margin-bottom:20px}.library-settings label{display:flex;flex:1;flex-direction:column;gap:8px}.library-path{color:var(--color-text-soft);font-size:12px;overflow-wrap:anywhere;margin:16px 0 24px}.library-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}.library-card{display:flex;align-items:flex-start;flex-direction:column;gap:12px;padding:22px;text-align:left;background:var(--color-card-gradient)}.library-card svg{width:34px;height:34px;color:#167c60}.library-card strong{overflow-wrap:anywhere}.library-card small{color:var(--color-text-soft)}.library-empty{text-align:center;padding:60px 10px;color:var(--color-text-soft)}

.gam-gamepad{display:flex;flex-direction:column;align-items:center;gap:6px;margin-top:22px;text-align:center;color:var(--color-text-soft);font-size:12px;overflow-wrap:anywhere}.gam-gamepad small{font-size:11px}.gam-gamepad .connected{color:#167c60}
.gam-player{min-height:100%;padding:24px;background:radial-gradient(ellipse at top right,#abc5b330,transparent 65%);color:var(--color-text)}
.gam-header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}.gam-header small{letter-spacing:2px;color:var(--color-text-soft)}h1{font-size:22px;margin:6px 0;max-width:60vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
button,select{font:inherit;color:inherit;border:1px solid var(--color-border);border-radius:13px;background:var(--color-surface);min-height:44px;padding:10px 16px;cursor:pointer}button:disabled{opacity:.4;cursor:default}button:focus-visible,select:focus-visible{outline:2px solid var(--color-accent);outline-offset:2px}button:active:not(:disabled){transform:translateY(1px)}button svg{width:22px;height:22px}.open-game{display:flex;align-items:center;gap:8px;white-space:nowrap;background:#167c60;color:#fff}
.gam-layout{display:flex;align-items:center;justify-content:center;gap:32px;max-width:1100px;margin:auto}.gam-device{flex:1;min-width:0;padding:20px;border-radius:28px;background:linear-gradient(145deg,#dce4de,#bac9c0);box-shadow:inset 0 1px 0 #fff,0 12px 32px #153f2315}.lcd-frame{position:relative;padding:16px;background:#34473e;border-radius:16px;box-shadow:inset 0 3px 8px #0005}canvas{display:block;width:100%;aspect-ratio:159/96;image-rendering:pixelated;background:#e5e5e5}.lcd-placeholder{position:absolute;inset:16px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#222;background:#e5e5e5}.lcd-placeholder strong{font-size:clamp(24px,4vw,42px);letter-spacing:4px}.lcd-placeholder span{font-size:13px}.gam-toolbar{display:flex;justify-content:center;align-items:center;gap:8px;margin-top:16px;flex-wrap:wrap;color:#30473c}.gam-toolbar button{display:flex;align-items:center;justify-content:center;padding:10px}
.gam-controls{flex:0 0 230px;text-align:center}.dpad{display:grid;grid-template-areas:'. up .' 'left . right' '. down .';grid-template-columns:repeat(3,64px);grid-template-rows:repeat(3,56px);gap:5px;justify-content:center}.dpad button,.action-keys button,.gam-keyboard button{touch-action:none;user-select:none}.dpad button{padding:8px;font-size:18px}.action-keys{display:flex;gap:16px;justify-content:center;margin-top:18px}.action-keys button{width:86px;height:54px;border-radius:28px}.confirm{background:#167c60;color:#fff}.gam-controls p,.gam-status{font-size:12px;color:var(--color-text-soft);margin-top:22px}.gam-keyboard{display:grid;grid-template-columns:repeat(auto-fit,minmax(52px,1fr));gap:8px;margin:22px auto;max-width:1000px}.gam-keyboard button{padding:8px}.gam-error{color:#c95043}.gam-status{text-align:center}footer{display:flex;justify-content:center;flex-wrap:wrap;gap:12px;font-size:11px;color:var(--color-text-soft);margin-top:24px}footer a{color:inherit}
@media(max-width:760px){.gam-player{padding:16px}.gam-layout{flex-direction:column;gap:20px}.gam-device{width:100%;max-width:580px}.gam-controls{flex:auto;width:100%;display:flex;align-items:center;justify-content:center;gap:28px}.gam-controls p{display:none}.dpad{grid-template-columns:repeat(3,50px);grid-template-rows:repeat(3,44px)}.action-keys{margin:0;flex-direction:column;gap:10px}}
/* Playback fits the app viewport; only the library is a scrolling page. */
.gam-playing{position:relative;height:100%;min-height:0;box-sizing:border-box;overflow:hidden;display:flex;flex-direction:column;gap:8px;padding:10px 14px}
.gam-playing .gam-header{flex:0 0 42px;min-height:0;margin:0;gap:10px}
.gam-playing .gam-header>div{flex:1;min-width:0}.gam-playing .gam-header small{display:none}.gam-playing h1{font-size:16px;margin:0;max-width:none}
.gam-playing .gam-header button{min-height:38px;padding:7px 10px;font-size:12px}
.gam-playing .gam-layout{flex:1 1 0;min-height:0;width:100%;max-width:none;margin:0;gap:12px;align-items:stretch;flex-direction:row}
.gam-playing .gam-device{flex:1 1 0;min-width:0;min-height:0;max-width:none;width:auto;padding:6px;border-radius:16px;display:flex;background:#dce4de}
.gam-playing .lcd-frame{flex:1;min-width:0;min-height:0;padding:4px;border-radius:11px;display:flex;background:#202b26}
.gam-playing canvas{width:100%;height:100%;min-height:0;aspect-ratio:auto;object-fit:contain;background:#202b26;border-radius:6px}
.gam-playing .lcd-placeholder{inset:4px}
.gam-playing .gam-controls{flex:0 0 166px;width:166px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
.gam-playing .dpad{grid-template-columns:repeat(3,48px);grid-template-rows:repeat(3,44px);gap:4px}
.gam-playing .dpad button{font-size:16px}.gam-playing .action-keys{flex-direction:row;gap:8px;margin:0}.gam-playing .action-keys button{width:72px;height:44px}
.gam-playing .gam-controls p{display:none}
.gam-playing .gam-toolbar{flex:0 0 auto;margin:0;flex-wrap:nowrap;gap:8px;padding:0;min-height:40px}
.gam-playing .gam-toolbar button,.gam-playing .gam-toolbar select{min-height:38px;height:38px;padding:6px 10px;font-size:12px}.gam-playing .gam-toolbar button svg{width:20px;height:20px}
.gam-playing .gam-gamepad{flex:0 0 16px;min-height:0;margin:0;font-size:11px}.gam-playing .gam-gamepad small,.gam-playing .gam-status{display:none}
.gam-playing .gam-error{position:absolute;bottom:66px;left:18px;right:18px;margin:0;padding:10px;border-radius:10px;background:var(--color-surface);font-size:12px;z-index:3}
.gam-playing .gam-keyboard{position:absolute;z-index:2;bottom:66px;left:14px;right:14px;max-height:45%;overflow:auto;scrollbar-width:none;margin:0;padding:12px;border-radius:16px;border:1px solid var(--color-border);background:var(--color-surface);box-shadow:0 -8px 24px #0002;grid-template-columns:repeat(auto-fit,minmax(44px,1fr));gap:6px}.gam-playing .gam-keyboard::-webkit-scrollbar{display:none}
@media(max-width:560px){.gam-playing{padding:8px;gap:6px}.gam-playing .gam-layout{flex-direction:column;gap:6px}.gam-playing .gam-controls{flex:0 0 112px;width:100%;flex-direction:row;gap:24px}.gam-playing .dpad{grid-template-columns:repeat(3,42px);grid-template-rows:repeat(3,34px);gap:3px}.gam-playing .dpad button{min-height:34px;padding:4px}.gam-playing .gam-toolbar{gap:4px}.gam-playing .gam-toolbar button,.gam-playing .gam-toolbar select{padding:5px;font-size:11px}}
@media(max-height:440px) and (min-width:561px){.gam-playing .gam-gamepad{display:none}.gam-playing .gam-controls{gap:8px}.gam-playing .dpad{grid-template-rows:repeat(3,38px)}.gam-playing .dpad button{min-height:38px}}
</style>
