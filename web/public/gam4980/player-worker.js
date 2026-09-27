/* TMC GAM4980 browser host, GPL-3.0; core provenance: source.zip. */
let core, timer, running=false, last=0, phase=0, saveAt=0, loaded=false;
function snapshot(force=false) {
  if (!loaded || (!force && !core.gam4980_save_dirty())) return;
  const bytes=new Uint8Array(core.memory.buffer,core.gam4980_save_data(),0x14000).slice();
  postMessage({type:'save',bytes},[bytes.buffer]); core.gam4980_save_mark_clean();
}
function paint() {
  const ptr=core.gam4980_framebuffer();
  const frame=new Uint16Array(core.memory.buffer,ptr,160*96).slice();
  postMessage({type:'frame',frame},[frame.buffer]);
}
function stop(){running=false;clearInterval(timer);timer=undefined;snapshot(true);}
function start(){
  if(!loaded || running)return;
  running=true;last=performance.now();phase=0;saveAt=last;
  timer=setInterval(()=>{try{
    const now=performance.now();phase+=Math.min(now-last,100);last=now;
    let steps=0;while(phase>=1000/60 && steps<6){core.gam4980_run_frame();phase-=1000/60;steps++;}
    if(steps)paint();
    if(now-saveAt>1000){snapshot();saveAt=now;}
    if(core.gam4980_shutdown_requested()){stop();postMessage({type:'stopped'});}
  }catch(e){stop();postMessage({type:'error',message:'模拟核心运行失败，请重新打开游戏'});}},16);
}
let chain=Promise.resolve();
onmessage=({data})=>{chain=chain.then(async()=>{
  if(data.type==='load'){
    stop();loaded=false;
    const [wasm,r8,re]=await Promise.all(['core.wasm','8.BIN','E.BIN'].map(async f=>{const r=await fetch('/gam4980/'+f);if(!r.ok)throw Error('运行资源加载失败');return r.arrayBuffer();}));
    if(r8.byteLength!==0x200000||re.byteLength!==0x200000)throw Error('运行资源长度错误');
    core=(await WebAssembly.instantiate(wasm,{})).instance.exports;
    new Uint8Array(core.memory.buffer,core.web_rom8(),r8.byteLength).set(new Uint8Array(r8));
    new Uint8Array(core.memory.buffer,core.web_rome(),re.byteLength).set(new Uint8Array(re));
    if(core.web_init()<=0)throw Error('模拟器初始化失败');
    if(!(data.game instanceof ArrayBuffer)||data.game.byteLength<0x46||data.game.byteLength>0x1e0000)throw Error('GAM 文件大小不正确');
    new Uint8Array(core.memory.buffer,core.gam4980_game_storage(),data.game.byteLength).set(new Uint8Array(data.game));
    if(core.web_load(data.game.byteLength)<=0)throw Error('无法读取 GAM 游戏');
    if(data.save?.length===0x14000)new Uint8Array(core.memory.buffer,core.gam4980_save_data(),0x14000).set(data.save);
    core.gam4980_set_lcd_theme(data.theme||0);loaded=true;paint();postMessage({type:'ready'});
  }else if(data.type==='retire'){stop();postMessage({type:'retired'});}
  else if(data.type==='play')start();
  else if(data.type==='pause')stop();
  else if(data.type==='key' && loaded && running && Number.isInteger(data.key) && data.key>=0 && data.key<=0x3b)core.gam4980_key_down(data.key);
  else if(data.type==='theme'&&loaded){core.gam4980_set_lcd_theme(data.theme);paint();}
  else if(data.type==='save')snapshot(true);
}).catch(e=>{stop();postMessage({type:'error',message:e.message||'播放器加载失败'});});};
