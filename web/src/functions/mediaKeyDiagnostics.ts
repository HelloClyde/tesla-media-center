import { reactive } from 'vue';
export const mediaActionNames: Record<string,string> = { play:'播放', pause:'暂停', previoustrack:'上一首', nexttrack:'下一首', seekto:'跳转进度' };
export const mediaKeyDiagnostics = reactive({
  supported: typeof navigator !== 'undefined' && 'mediaSession' in navigator,
  registrations: {} as Record<string,string>,
  events: [] as { id:number; time:string; source:string; message:string }[],
});
let sequence=0;
export function logMediaKey(source:string,message:string) {
  mediaKeyDiagnostics.events.unshift({id:++sequence,time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),source,message});
  mediaKeyDiagnostics.events.splice(100);
}
type Handler = (details: MediaSessionActionDetails) => void | Promise<void>;
const testers = new Map<MediaSessionAction,Handler>();
export function testMediaAction(action: MediaSessionAction) {
  const handler=testers.get(action);
  if(handler)void handler({action});
  else logMediaKey('页面测试','QQ 音乐尚未注册此操作，请先打开 QQ 音乐播放歌曲');
}
export function registerMusicMediaControls(session:MediaSession, handlers:Partial<Record<MediaSessionAction,Handler>>) {
  const installed:MediaSessionAction[]=[];
  for(const [key,handler] of Object.entries(handlers)) {
    const action=key as MediaSessionAction;
    const invoke=async(source:string,details:MediaSessionActionDetails)=>{
      logMediaKey(source,`收到${mediaActionNames[action] || action}指令`);
      try { await handler!(details); logMediaKey(source,`${mediaActionNames[action] || action}处理结束；是否切歌请看歌曲和播放状态记录`); }
      catch(error) { logMediaKey(source,`处理失败：${error instanceof Error ? error.message : String(error)}`); }
    };
    try {
      session.setActionHandler(action, details=>{void invoke('系统媒体指令',details);});
      mediaKeyDiagnostics.registrations[action]='已注册'; installed.push(action);
      testers.set(action,details=>invoke('页面测试（非实体按键）',details));
    } catch(error) {
      mediaKeyDiagnostics.registrations[action]='注册失败';
      logMediaKey('注册',`${mediaActionNames[action]}：${error instanceof Error ? error.name : '不支持'}`);
    }
  }
  return ()=>{for(const action of installed){try{session.setActionHandler(action,null);}catch{}testers.delete(action);mediaKeyDiagnostics.registrations[action]='已解除';}};
}
