// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest';
import { registerMusicMediaControls, testMediaAction, mediaKeyDiagnostics, logMediaKey } from './mediaKeyDiagnostics';
beforeEach(()=>{mediaKeyDiagnostics.events.splice(0);mediaKeyDiagnostics.registrations={};});
it('records hardware dispatch separately from page tests and preserves the async music handler', async()=>{
  const callbacks=new Map<string,MediaSessionActionHandler|null>();
  const session={setActionHandler:vi.fn((action:string,handler:MediaSessionActionHandler|null)=>callbacks.set(action,handler))} as unknown as MediaSession;
  let finish!:()=>void;
  const next=vi.fn(()=>new Promise<void>(resolve=>{finish=resolve;}));
  const cleanup=registerMusicMediaControls(session,{nexttrack:next});
  callbacks.get('nexttrack')!({action:'nexttrack'});
  expect(next).toHaveBeenCalledOnce();
  expect(mediaKeyDiagnostics.events[0].source).toBe('系统媒体指令');
  expect(mediaKeyDiagnostics.events.some(e=>e.message.includes('处理结束'))).toBe(false);
  finish();await Promise.resolve();await Promise.resolve();
  expect(mediaKeyDiagnostics.events[0].message).toContain('处理结束');
  testMediaAction('nexttrack');
  expect(mediaKeyDiagnostics.events[0].source).toBe('页面测试（非实体按键）');
  expect(next).toHaveBeenCalledTimes(2);finish();await Promise.resolve();
  cleanup();expect(callbacks.get('nexttrack')).toBeNull();
  expect(mediaKeyDiagnostics.registrations.nexttrack).toBe('已解除');
});
it('records unsupported actions and handler errors without leaking rejections',async()=>{
  let callback:MediaSessionActionHandler;
  const session={setActionHandler:(action:string,handler:MediaSessionActionHandler)=>{if(action==='previoustrack')throw new Error('Unsupported');callback=handler;}} as unknown as MediaSession;
  const cleanup=registerMusicMediaControls(session,{previoustrack:()=>{},nexttrack:async()=>{throw new Error('playback failed');}});
  expect(mediaKeyDiagnostics.registrations.previoustrack).toBe('注册失败');
  callback!({action:'nexttrack'});await Promise.resolve();await Promise.resolve();
  expect(mediaKeyDiagnostics.events[0].message).toContain('playback failed');cleanup();
});
it('keeps a bounded in-memory log',()=>{for(let i=0;i<130;i++)logMediaKey('test',String(i));expect(mediaKeyDiagnostics.events).toHaveLength(100);expect(mediaKeyDiagnostics.events[0].message).toBe('129');});
