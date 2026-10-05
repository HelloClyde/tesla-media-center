import { afterEach, expect, it, vi } from 'vitest';
import type { AppRoute } from './amapNavigation';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
import { createTeslaMapGround } from './teslaMapGround';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); post.mockReset(); });

it('requests compact BMD for 3D roads and buildings', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  class FakeWorker {
    onmessage?: (event: any) => void;
    onerror?: () => void;
    constructor() { queueMicrotask(() => this.onmessage?.({data:{ready:true}})); }
    postMessage(input: any) { queueMicrotask(() => this.onmessage?.({data:{tiles:input.tiles}})); }
    terminate() {}
  }
  vi.stubGlobal('Worker', FakeWorker);
  post.mockImplementation(async (_url: string, batch: {level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>({
      level:batch.level,x,y,collection:{features:[]},buildings:[],surfaces:[],
    }))}},
  }));
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(100);
  expect(post.mock.calls.some(call => call[0] === '/api/amap-app/map/bmd' && call[1].level === 14)).toBe(true);
  expect(post.mock.calls.some(call => call[0] === '/api/amap-app/map/bmd' && call[1].level === 15)).toBe(true);
  ground.dispose();
});

it.each(['missing', 'blocked'])('keeps compact BMD when the module Worker is %s', async mode => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  vi.stubGlobal('Worker', mode === 'missing' ? undefined : class {
    constructor() { throw new Error('module Worker blocked'); }
  });
  post.mockImplementation(async (_url: string, batch: {level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>({
      level:batch.level,x,y,collection:{features:[]},buildings:[],surfaces:[],
    }))}},
  }));
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(100);
  expect(post.mock.calls.some(call=>call[0]==='/api/amap-app/map/bmd' && call[1].level===14)).toBe(true);
  expect(post.mock.calls.some(call=>call[0]==='/api/amap-app/map')).toBe(false);
  ground.dispose();
});

it('decodes the retained BMD locally when a module Worker fails before it is ready', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  class StartupFailedWorker {
    onerror?: () => void;
    constructor() { queueMicrotask(() => this.onerror?.()); }
    terminate() {}
  }
  vi.stubGlobal('Worker', StartupFailedWorker);
  post.mockImplementation(async (_url:string, batch:{level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>({
      level:batch.level,x,y,collection:{features:[]},buildings:[],surfaces:[],
    }))}},
  }));
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(100);
  expect(post.mock.calls.some(call=>call[0]==='/api/amap-app/map/bmd' && call[1].level===14)).toBe(true);
  expect(post.mock.calls.some(call=>call[0]==='/api/amap-app/map')).toBe(false);
  ground.dispose();
});

it('shows the navigation ground before distant background levels complete', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  post.mockImplementation((_url: string, batch: { level: number; tiles: number[][] }) => {
    if (batch.level < 14) return new Promise(() => {});
    return Promise.resolve({ status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]) => ({
      level: batch.level, x, y, collection: { features: [] }, buildings: [],
      surfaces: batch.level === 14 ? [{ minZoom: 0, maxZoom: 20,
        paints: { day: [{ minZoom: 0, maxZoom: 20, color: '#fff' }] },
        rings: [[[120, 30], [120.001, 30], [120, 30.001]]] }] : [],
    })) } } });
  });
  const report = vi.fn();
  const ground = createTeslaMapGround(report);
  ground.update([120.1, 30.2], -180, 0);
  await vi.advanceTimersByTimeAsync(100);
  expect(post.mock.calls.filter(call => call[1].layer !== 'lanes').slice(0, 3).map(call => call[1].level)).toEqual([14, 15, 3]);
  expect(post.mock.calls.some(call => call[1].layer === 'lanes')).toBe(false);
  expect(ground.group.visible).toBe(true);
  expect(report).toHaveBeenCalledWith('App 道路与建筑已显示 · 正在补充地表…', true);
  ground.dispose();
});

it('paints broad App surfaces beneath detailed navigation surfaces', async () => {
  vi.useFakeTimers();
  const fills: string[] = [];
  const context = {
    fillStyle: '', fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() { fills.push(this.fillStyle); }, stroke() {}, strokeText() {}, fillText() {},
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as any);
  post.mockImplementation(async (_url: string, batch: { level: number; tiles: number[][] }) => ({
    status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]) => ({
      level: batch.level, x, y, collection: { features: [] }, buildings: [],
      surfaces: batch.level === 15 ? [] : [{ minZoom: 0, maxZoom: 20,
        paints: { day: [{ minZoom: 0, maxZoom: 20, color: batch.level === 14 ? '#1144aa' : '#aa4411' }] },
        rings: [[[120, 30], [120.001, 30], [120, 30.001]]] }],
    })) } } }));
  const ground = createTeslaMapGround(vi.fn());
  ground.update([120.1, 30.2], -180, 0);
  await vi.advanceTimersByTimeAsync(100);
  expect(fills[fills.length - 1]).toBe('#1144aa');
  ground.dispose();
});

it('does not retry unavailable map tiles after login expires', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as any);
  post.mockResolvedValue({status:200,data:{status:'need_login'}});
  const report=vi.fn();
  const ground=createTeslaMapGround(report);
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(31000);
  ground.update([120.101,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(31000);
  expect(post).toHaveBeenCalledTimes(1);
  expect(report).toHaveBeenCalledWith('TMC 登录已失效，请登录后重试地图',false);
  ground.dispose();
});

it('keeps compact BMD enabled after a temporary 3D map gateway failure', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as any);
  vi.stubGlobal('Worker', class {});
  post.mockRejectedValue({response:{status:502}});
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  ground.retry();
  await vi.advanceTimersByTimeAsync(10);
  expect(post.mock.calls.map(call=>call[0])).toEqual([
    '/api/amap-app/map/bmd', '/api/amap-app/map/bmd',
  ]);
  ground.dispose();
});

it('does not permanently fall back to JSON when the BMD worker fails once', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as any);
  class FailedWorker {
    onmessage?: (event: any) => void;
    onerror?: () => void;
    constructor() { queueMicrotask(() => this.onmessage?.({data:{ready:true}})); }
    postMessage() { queueMicrotask(() => this.onerror?.()); }
    terminate() {}
  }
  vi.stubGlobal('Worker', FailedWorker);
  post.mockImplementation(async (_url:string,batch:{level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>({level:batch.level,x,y}))}},
  }));
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(post.mock.calls.map(call=>call[0])).toEqual(['/api/amap-app/map/bmd']);
  ground.retry();
  await vi.advanceTimersByTimeAsync(10);
  expect(post.mock.calls.slice(0,2).map(call=>call[0])).toEqual([
    '/api/amap-app/map/bmd', '/api/amap-app/map/bmd',
  ]);
  expect(post.mock.calls[2][0]).toBe('/api/amap-app/map');
  ground.dispose();
});

it('loads the visible 3D ground before warming decoded route roads and buildings', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  post.mockImplementation(async (url: string, batch: { level: number; tiles: number[][] }, options?: {headers?:{Accept?:string}}) =>
    url.endsWith('/prefetch') && !options?.headers?.Accept
      ? { status: 204, data: '' }
      : { status: 200, data: { status: 'ok', data: { tiles: batch.tiles.map(([x, y]) => ({
          level: batch.level, x, y, collection: { features: [] }, buildings: [],
          surfaces: [{ minZoom: 0, maxZoom: 20, paints: { day: [{ minZoom: 0, maxZoom: 20, color: '#fff' }] },
            rings: [[[120, 30], [120.001, 30], [120, 30.001]]] }],
        })) } } });
  const report = vi.fn();
  const ground = createTeslaMapGround(report);
  const route: AppRoute = { id: 1, path: [[120.1, 30.2], [120.2, 30.2]],
    breaks: [], steps: [], distance: 10000, labels: [] };
  ground.setRoute(route);
  ground.update([120.1, 30.2], -180, 0);
  await vi.advanceTimersByTimeAsync(500);
  const visibleCount = post.mock.calls.length;
  expect(post.mock.calls.slice(0, visibleCount).some(call => call[1].level === 15)).toBe(true);
  await vi.advanceTimersByTimeAsync(20000);
  const background = post.mock.calls.slice(visibleCount);
  expect(background.length).toBeGreaterThan(0);
  expect(background.every(call => call[1].tiles.length === 1)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map/bmd/prefetch' && call[1].level === 14 && call[2]?.headers?.Accept)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map/bmd/prefetch' && call[1].level === 15 && call[2]?.headers?.Accept)).toBe(true);
  expect(background.some(call => call[0] === '/api/amap-app/map/bmd/prefetch')).toBe(true);
  const buildingDownloads = background.filter(call => call[0] === '/api/amap-app/map/bmd/prefetch' && call[1].level === 15 && call[2]?.headers?.Accept);
  const prefetchedBuilding = buildingDownloads[buildingDownloads.length - 1][1].tiles[0];
  const [x, y] = prefetchedBuilding;
  const target: [number, number] = [(x + .5) / 2 ** 15 * 360 - 180, 90 - (y + .5) / 2 ** 15 * 180];
  const beforeMove = post.mock.calls.length;
  const beforeReports = report.mock.calls.length;
  ground.update(target, -180, 0);
  await vi.advanceTimersByTimeAsync(500);
  expect(report.mock.calls.length).toBeGreaterThan(beforeReports);
  expect(post.mock.calls.slice(beforeMove).filter(call => call[0] === '/api/amap-app/map/bmd' && call[1].level === 15 && call[1].layer !== 'lanes')
    .every(call => !call[1].tiles.some(([tx, ty]: number[]) => tx === x && ty === y))).toBe(true);
  ground.dispose();
});

it('keeps the current App map visible while the next patch is still loading', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  let hold = false;
  post.mockImplementation((_url: string, batch: { level: number; tiles: number[][] }) => {
    if (hold) return new Promise(() => {});
    return Promise.resolve({status: 200, data: {status: 'ok', data: {tiles: batch.tiles.map(([x,y]) => ({
      level: batch.level, x, y, collection: {features: []},
      surfaces: [{minZoom: 0, maxZoom: 20, paints: {day: [{minZoom: 0, maxZoom: 20, color: '#fff'}]},
        rings: [[[120,30],[120.001,30],[120,30.001]]]}],
    }))}}});
  });
  const ground = createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(ground.group.visible).toBe(true);
  hold = true;
  ground.update([120.103,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(ground.group.visible).toBe(true);
  ground.dispose();
});

it('finishes a moving car map request before recentering on the latest position', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  let hold = false, release: (() => void) | undefined;
  const reply = (batch: {level:number;tiles:number[][]}) => ({status:200,data:{status:'ok',data:{
    tiles:batch.tiles.map(([x,y])=>({level:batch.level,x,y,collection:{features:[]},buildings:[],
      surfaces:batch.level===14?[{minZoom:0,maxZoom:20,paints:{day:[{minZoom:0,maxZoom:20,color:'#fff'}]},
        rings:[[[120,30],[120.001,30],[120,30.001]]]}]:[],
    })),
  }}});
  post.mockImplementation((_url:string,batch:{level:number;tiles:number[][]}) =>
    hold && batch.level===14 && !release
      ? new Promise(resolve => { release=()=>resolve(reply(batch)); }) : Promise.resolve(reply(batch)));
  const report=vi.fn(), ground=createTeslaMapGround(report);
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(100);
  expect(ground.group.visible).toBe(true);
  hold=true;
  ground.update([120.13,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(release).toBeDefined();
  const pending=post.mock.calls.filter((call:any[])=>call[1].level===14).slice(-1)[0];
  const calls=post.mock.calls.length;
  ground.update([120.1315,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(post).toHaveBeenCalledTimes(calls);
  expect(pending[2].signal.aborted).toBe(false);
  const reports=report.mock.calls.filter(call=>call[0]==='正在加载混合地图…').length;
  release!();
  await vi.advanceTimersByTimeAsync(100);
  expect(report.mock.calls.filter(call=>call[0]==='正在加载混合地图…').length).toBeGreaterThan(reports);
  ground.dispose();
});

it('lifts the navigation ribbon onto an App elevated road with matching direction', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  post.mockImplementation(async (_url: string, batch: {layer?:string;level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>({
      level:batch.level,x,y,
      ...(batch.layer==='lanes' ? {laneBoundaries:[
        [[120.1005,30.2],[120.1007,30.2]],
        [[120.1005,30.1999],[120.1005,30.2001]],
      ]} : {}),
      collection:{features:[{geometry:{type:'LineString',coordinates:[[120.1,30.2],[120.101,30.2],[120.102,30.2]]},
        properties:{levelMarkers:[[0,1],[2,-1]]}}]},
      surfaces:[{minZoom:0,maxZoom:20,paints:{day:[{minZoom:0,maxZoom:20,color:'#fff'}]},
        rings:[[[120,30],[120.001,30],[120,30.001]]]}],
    }))}}}));
  const ground=createTeslaMapGround(vi.fn());
  ground.setRoute({id:1,path:[[120.1,30.2],[120.102,30.2]],steps:[{start:0,end:1,road:'测试路'}],
    breaks:[],distance:190,labels:[]},0,true);
  ground.update([120.101,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(ground.roadHeight([120.1005,30.2],[1,0])).toBeGreaterThan(3);
  expect(ground.roadHeight([120.1005,30.2],[0,1])).toBe(0);
  const lanes=ground.group.children.find(child=>child.name==='AppLaneBoundaries') as any;
  expect(lanes?.userData.segmentCount).toBe(1);
  const positions=lanes.geometry.getAttribute('position');
  for(let i=0;i<6;i++) expect(positions.getY(i)).toBeGreaterThan(3);
  ground.dispose();
});

it('keeps preview roads clean and loads LNDS only during navigation', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  post.mockImplementation(async (_url: string, batch: {layer?:string;level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>batch.layer==='lanes'
      ? {level:15,x,y,laneBoundaries:[[[120.1,30.2],[120.1002,30.2]]]}
      : {level:batch.level,x,y,collection:{features:[]},surfaces:[{minZoom:0,maxZoom:20,
        paints:{day:[{minZoom:0,maxZoom:20,color:'#fff'}]},
        rings:[[[120,30],[120.001,30],[120,30.001]]]}]})}}}));
  const ground=createTeslaMapGround(vi.fn());
  ground.update([120.1,30.2],-180,0);
  await vi.advanceTimersByTimeAsync(10);
  expect(ground.group.visible).toBe(true);
  expect(ground.group.children.some(child=>child.name==='AppLaneBoundaries')).toBe(false);
  expect(post.mock.calls.some(call=>call[1].layer==='lanes')).toBe(false);
  ground.setRoute({id:1,path:[[120.1,30.2],[120.1002,30.2]],steps:[{start:0,end:1,road:'测试路'}],
    breaks:[],distance:20,labels:[]},0,true);
  await vi.advanceTimersByTimeAsync(10);
  expect(ground.group.children.some(child=>child.name==='AppLaneBoundaries')).toBe(true);
  expect(post.mock.calls.some(call=>call[1].layer==='lanes')).toBe(true);
  ground.setRoute(undefined,0,false);
  expect(ground.group.children.some(child=>child.name==='AppLaneBoundaries')).toBe(false);
  ground.dispose();
});

it('loads all visible LNDS tiles one at a time across a tile corner', async () => {
  vi.useFakeTimers();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {},
    fill() {}, stroke() {}, strokeText() {}, fillText() {},
  } as any);
  const n=2**15;
  const corner: [number,number]=[-180+26979*360/n,90-9119*180/n];
  post.mockImplementation(async (_url: string, batch: {layer?:string;level:number;tiles:number[][]}) => ({
    status:200,data:{status:'ok',data:{tiles:batch.tiles.map(([x,y])=>batch.layer==='lanes'
      ? {level:15,x,y,laneBoundaries:[[[corner[0]+(x-26979)*.0001,corner[1]+(y-9119)*.0001],
        [corner[0]+(x-26979)*.0001+.00005,corner[1]+(y-9119)*.0001]]]}
      : {level:batch.level,x,y,collection:{features:[]},surfaces:[{minZoom:0,maxZoom:20,
        paints:{day:[{minZoom:0,maxZoom:20,color:'#fff'}]},
        rings:[[[corner[0],corner[1]],[corner[0]+.001,corner[1]],[corner[0],corner[1]+.001]]]}]})}}}));
  const ground=createTeslaMapGround(vi.fn());
  ground.setRoute({id:1,path:[[corner[0]-.0002,corner[1]],[corner[0]+.0002,corner[1]]],
    steps:[{start:0,end:1,road:'测试路'}],breaks:[],distance:40,labels:[]},0,true);
  ground.update(corner,-180,0);
  await vi.advanceTimersByTimeAsync(100);
  const requests=post.mock.calls.filter(call=>call[1].layer==='lanes');
  expect(requests).toHaveLength(4);
  expect(requests.every(call=>call[1].tiles.length===1)).toBe(true);
  const mesh=ground.group.children.find(child=>child.name==='AppLaneBoundaries');
  expect(mesh?.userData.segmentCount).toBe(4);
  ground.dispose();
});
