// @vitest-environment node
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {expect,it,vi} from 'vitest';
function player() {
 const c=vm.createContext({Logger:class{logInfo(){}},Worker:class{},URL,console,Uint8Array,DataView,kProtoHttp:0,kOpenDecoderReq:7});
 vm.runInContext(readFileSync(new URL('../../public/player.js',import.meta.url),'utf8'),c);
 const p=vm.runInContext('new Player()',c);
 Object.assign(p,{mp4HeaderProbe:{offset:0,header:[],active:true,identified:false},fileInfo:{size:265703415,offset:0},reportPlayError:vi.fn(),downloadOneChunk:vi.fn(),decodeWorker:{postMessage:vi.fn()}});
 return p;
}
function box(b:Uint8Array,offset:number,size:number,type:string){new DataView(b.buffer).setUint32(offset,size);b.set([...type].map(c=>c.charCodeAt(0)),offset+4);}
it('waits for the complete 631825-byte moov before opening the failing Douyin sample',()=>{
 const p=player(),b=new Uint8Array(524288);box(b,0,32,'ftyp');box(b,32,631825,'moov');
 expect(p.inspectMp4Header(b.buffer,0)).toBe(true);p.fileInfo.offset=b.length;p.onFileDataUnderDecoderIdle();
 expect(p.decodeWorker.postMessage).not.toHaveBeenCalled();expect(p.waitHeaderLength).toBe(631857);
 p.fileInfo.offset=1048576;p.onFileDataUnderDecoderIdle();expect(p.decodeWorker.postMessage).toHaveBeenCalledWith({t:7});
});
it('handles a moov header split across byte ranges',()=>{
 const p=player(),b=new Uint8Array(524288);box(b,0,8,'ftyp');box(b,8,524275,'free');
 const h=new Uint8Array(8);box(h,0,100000,'moov');b.set(h.slice(0,5),524283);
 p.inspectMp4Header(b.buffer,0);expect(p.waitHeaderLength).toBeGreaterThan(524288);
 p.inspectMp4Header(h.slice(5).buffer,524288);expect(p.waitHeaderLength).toBe(624283);
});
it('handles extended-size atoms and rejects unbounded headers',()=>{
 const p=player(),b=new Uint8Array(48);box(b,0,32,'ftyp');box(b,32,1,'moov');new DataView(b.buffer).setUint32(44,700000);
 p.inspectMp4Header(b.buffer,0);expect(p.waitHeaderLength).toBe(700032);
 const other=player();box(b,32,20*1024*1024,'moov');expect(other.inspectMp4Header(b.buffer,0)).toBe(false);expect(other.reportPlayError).toHaveBeenCalledOnce();
});
it('leaves non-MP4 input and ordinary short headers unchanged',()=>{
 const p=player();p.inspectMp4Header(new Uint8Array(16).buffer,0);expect(p.waitHeaderLength).toBe(524288);expect(p.reportPlayError).not.toHaveBeenCalled();
 const other=player(),b=new Uint8Array(48);box(b,0,32,'ftyp');box(b,32,100,'moov');other.inspectMp4Header(b.buffer,0);expect(other.waitHeaderLength).toBe(524288);
});
it('does not open when the next box header starts exactly at the chunk boundary',()=>{
 const p=player(),b=new Uint8Array(524288);box(b,0,32,'ftyp');box(b,32,524256,'free');
 p.inspectMp4Header(b.buffer,0);p.fileInfo.offset=b.length;p.onFileDataUnderDecoderIdle();
 expect(p.decodeWorker.postMessage).not.toHaveBeenCalled();
 const h=new Uint8Array(8);box(h,0,100000,'moov');p.inspectMp4Header(h.buffer,524288);expect(p.waitHeaderLength).toBe(624288);
});
