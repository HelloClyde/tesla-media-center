import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import axios from 'axios';
import L from 'leaflet';
import View from './AmapAppView.vue';
import { backgroundNavigation } from '@/stores/backgroundNavigation';
import { navigationEngine } from '@/functions/navigationEngine';
import type { AppRoute, Point } from './amapNavigation';
import { navigationSessionTestDb } from './navigationSessionTestDb';
import { loadNavigationSession } from './amapNavigationSession';

const gps = vi.hoisted(() => ({ point: [120.2, 30.28], listeners: new Map<string, (fix: any) => void>() }));
vi.mock('@/functions/navigationCoordinates', () => ({ browserNavigationPoint: (x: number, y: number) => [x, y] }));
vi.mock('@/stores/geoLocation', () => {
  const fix = () => ({ longitude: gps.point[0], latitude: gps.point[1], accuracy: 1, heading: 0, speed: 10,
    timestamp: Date.now(), source: 'gps', altitude: null, altitudeAccuracy: null });
  return { useGeoLocationStore: () => ({ getCurPosition: fix, init() {}, refresh() { gps.listeners.forEach(fn => fn(fix())); },
    addListener: (key: string, fn: (value: any) => void) => gps.listeners.set(key, fn), addErrorListener() {},
    removeListener: (key: string) => gps.listeners.delete(key) }) };
});
vi.mock('@/functions/localSpeech', async () => {
  const { reactive } = await import('vue');
  return { localSpeechState: reactive({}), prepareLocalSpeech: async () => {},
    preloadLocalSpeech: async () => {}, cancelLocalSpeechPreload() {}, speakLocal: async () => true, stopLocalSpeech() {} };
});
vi.mock('./AmapNavigation3D.vue', () => ({ default: { template: '<div class="test-3d"></div>' } }));
vi.mock('./amapVectorMap', () => ({ attachAppMap: () => ({ setFollowing() {}, setActive() {}, setRoute() {},
  setAppearance() {}, retry() {}, releaseMemory() {}, dispose() {} }) }));

let view: VueWrapper | undefined;
let calls: { url: string; payload: any }[];
let routeReply: ((origin: Point) => any) | undefined;
let switchReply: ((payload: any) => any) | undefined;
const navigationDb = navigationSessionTestDb();
const lastCall = (url: string) => calls.filter(call => call.url === url).slice(-1)[0];
const end: Point = [120.24, 30.32];
function routesFrom(origin: Point): AppRoute[] {
  return [0, 1, 2].map(id => ({ id, path: [origin, [120.2, 30.285], [120.22 + id * .01, 30.30], end],
    steps: [{ start: 0, end: 3, road: `测试道路 ${id}`, maneuver: 'straight' }], breaks: [], distance: 6000,
    duration: 1200 + id * 300, tolls: id * 5, tollCurrency: 'CNY', labels: [] }));
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'performance'] });
  gps.point = [120.2, 30.28]; gps.listeners.clear(); calls = []; routeReply = undefined; switchReply = undefined;
  navigationEngine.value = 'browser';
  localStorage.clear();
  navigationDb.reset(); vi.stubGlobal('indexedDB', navigationDb.indexedDB);
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('requestAnimationFrame', () => 1); vi.stubGlobal('cancelAnimationFrame', () => {});
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { watchPosition: vi.fn(() => 10), clearWatch: vi.fn() } });
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
  Object.assign(L.Browser, { svg: true });
  vi.spyOn(axios, 'get').mockResolvedValue({ data: { status: 'ok', data: { places: [{ id: 'test', name: '测试终点', location: end }] } } });
  vi.spyOn(axios, 'post').mockImplementation(async (url, payload) => {
    calls.push({ url, payload });
    if (url === '/api/amap-app/route') return routeReply ? routeReply((payload as any).origin)
      : { data: { status: 'ok', data: { state: 'ready', routes: routesFrom((payload as any).origin), routeToken: 'initial' } } };
    if (url === '/api/amap-app/switch-road' && switchReply) return switchReply(payload);
    return { data: { status: 'ok', data: { state: 'unavailable' } } };
  });
});
afterEach(() => { view?.unmount(); view = undefined; document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

async function navigate(live = false) {
  view = mount(View, { attachTo: document.body });
  await flushPromises();
  await view.get('.place-select').trigger('click');
  await flushPromises();
  const start = view.findAll('button').find(button => button.text() === (live ? '开始导航' : '模拟导航'))!;
  await start.trigger('click'); await flushPromises();
  await vi.advanceTimersByTimeAsync(4000); await flushPromises();
  expect(backgroundNavigation.simulated).toBe(!live);
  return view;
}

async function correctRoad(wrapper: VueWrapper, target: string) {
  await wrapper.get(`button[aria-label="切换至${target}"]`).trigger('click');
  await flushPromises();
}

async function remountNavigation() {
  view!.unmount(); view = undefined;
  await loadNavigationSession(); // Wait for the pagehide/unmount checkpoint transaction.
  view = mount(View, {attachTo:document.body}); await flushPromises();
  return view;
}

it('resumes simulated progress, 3D and voice settings after a page reload without replanning', async () => {
  const wrapper = await navigate();
  await wrapper.get('button[aria-label="切换为 3D 地图"]').trigger('click');
  await wrapper.findAll('button').find(button => button.text() === '关闭语音')!.trigger('click');
  await flushPromises();
  const before = (await loadNavigationSession())!;
  expect(before.checkpoint.progress).toBeGreaterThan(0);
  const plans = calls.filter(call => call.url === '/api/amap-app/route').length;
  const restored = await remountNavigation();
  expect(restored.find('.test-3d').exists()).toBe(true);
  expect(backgroundNavigation.active).toBe(true);
  expect(backgroundNavigation.simulated).toBe(true);
  expect(backgroundNavigation.muted).toBe(true);
  expect((await loadNavigationSession())!.checkpoint.progress).toBeCloseTo(before.checkpoint.progress);
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(plans);
  await vi.advanceTimersByTimeAsync(1500); await flushPromises();
  expect((await loadNavigationSession())!.checkpoint.progress).toBeGreaterThan(before.checkpoint.progress);
});

it('restores the selected native route and reacquires fresh GPS rather than replaying the saved location', async () => {
  const wrapper = await navigate(true);
  // Switch within the same native session without touching GPS tracking.
  await wrapper.get('.turn-card').trigger('click'); await flushPromises();
  await wrapper.get('.navigation-overview-heading button').trigger('click'); await flushPromises();
  gps.point = [120.2,30.281];
  gps.listeners.forEach(fn => fn({longitude:120.2,latitude:30.281,accuracy:1,heading:0,speed:10,
    timestamp:Date.now(),source:'gps'}));
  await flushPromises();
  await vi.advanceTimersByTimeAsync(1200); await flushPromises();
  const before = (await loadNavigationSession())!;
  expect(before.checkpoint.progress).toBeGreaterThan(0);
  gps.point = [120.2,30.282];
  const plans = calls.filter(call => call.url === '/api/amap-app/route').length;
  const restored = await remountNavigation();
  expect(restored.find('.turn-card').exists()).toBe(true);
  expect(backgroundNavigation.active).toBe(true);
  expect(backgroundNavigation.simulated).toBe(false);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({routeToken:before.route.token,routeIndex:before.checkpoint.selected});
  expect((await loadNavigationSession())!.checkpoint.progress).toBeGreaterThan(before.checkpoint.progress);
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(plans);
});

it('remembers an alternative native route index when that route was selected before starting', async () => {
  view = mount(View, {attachTo:document.body}); await flushPromises();
  await view.get('.place-select').trigger('click'); await flushPromises();
  await view.findAll('.route-options button')[2].trigger('click');
  await view.findAll('button').find(button => button.text() === '开始导航')!.trigger('click'); await flushPromises();
  await remountNavigation();
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({routeToken:'initial',routeIndex:2});
  expect(backgroundNavigation.road).toContain('测试道路 2');
});

it('clears the saved trip on exit so a later refresh only follows the car', async () => {
  const wrapper = await navigate();
  expect(await loadNavigationSession()).toBeDefined();
  await wrapper.findAll('button').find(button => button.text() === '退出导航')!.trigger('click'); await flushPromises();
  expect(await loadNavigationSession()).toBeUndefined();
  const restored = await remountNavigation();
  expect(backgroundNavigation.active).toBe(false);
  expect(restored.find('.turn-card').exists()).toBe(false);
  expect(restored.find('.route-options').exists()).toBe(false);
});

it('refreshes from the moving car, keeps the running session, and switches using the native index', async () => {
  const wrapper = await navigate();
  routeReply = origin => {
    const fresh = routesFrom(origin);
    fresh[0].duration = 600;
    return { data: { status: 'ok', data: { state: 'ready', routes: [fresh[2], fresh[0], fresh[1]], routeToken: 'refreshed' } } };
  };
  const before = calls.filter(call => call.url === '/api/amap-app/route').length;
  await wrapper.get('button[aria-label="切换为 3D 地图"]').trigger('click'); await flushPromises();
  expect(wrapper.find('.test-3d').exists()).toBe(true);
  await wrapper.get('.turn-card').trigger('click'); await flushPromises();
  expect(wrapper.find('.test-3d').exists()).toBe(false);
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(before + 1);
  const requestedOrigin = lastCall('/api/amap-app/route').payload.origin;
  expect(requestedOrigin[1]).toBeGreaterThan(30.28);
  const cards = wrapper.findAll('.navigation-route-options button');
  expect(cards).toHaveLength(3);
  expect(cards[0].text()).toContain('当前路线');
  expect(cards[0].text()).toContain('约 10 分钟');
  expect(backgroundNavigation.active).toBe(true);
  expect(lastCall('/api/amap-app/navigation-events').payload.routeToken).toBe('initial');
  const colors = Array.from(wrapper.element.querySelectorAll('.leaflet-overlay-pane path')).map(path => path.getAttribute('stroke'));
  expect(colors.filter(color => color === '#929ba6')).toHaveLength(2);
  expect(colors).toContain('#1688ef');
  await wrapper.get('button[aria-label="缩小"]').trigger('click'); await flushPromises();
  expect(wrapper.findAll('.navigation-route-options button')).toHaveLength(3);
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(before + 1);
  await cards[2].trigger('click'); await flushPromises();
  expect(wrapper.find('.navigation-route-options').exists()).toBe(false);
  expect(wrapper.find('.test-3d').exists()).toBe(true);
  expect(wrapper.text()).toContain('模拟导航');
  expect(lastCall('/api/amap-app/navigation-events').payload)
    .toEqual({ routeToken: 'refreshed', routeIndex: 2 });
  await vi.advanceTimersByTimeAsync(500); await flushPromises();
  expect(backgroundNavigation.active).toBe(true);
  expect(backgroundNavigation.simulated).toBe(true);
});

it('ignores a refresh response after returning to guidance and preserves navigation on refresh failure', async () => {
  const wrapper = await navigate();
  let resolveReply!: (value: any) => void;
  routeReply = () => new Promise(resolve => { resolveReply = resolve; });
  await wrapper.get('.turn-card').trigger('keydown', { key: 'Enter' }); await flushPromises();
  expect(wrapper.text()).toContain('刷新中');
  await wrapper.get('.navigation-overview-heading button').trigger('click'); await flushPromises();
  resolveReply({ data: { status: 'ok', data: { state: 'ready', routes: routesFrom(gps.point as Point), routeToken: 'too-late' } } });
  await flushPromises();
  expect(wrapper.find('.navigation-route-options').exists()).toBe(false);
  expect(calls.some(call => call.payload?.routeToken === 'too-late')).toBe(false);
  routeReply = () => Promise.reject(new Error('测试刷新失败'));
  await wrapper.get('.turn-card').trigger('click'); await flushPromises();
  expect(wrapper.text()).toContain('测试刷新失败');
  expect(wrapper.findAll('.navigation-route-options button')).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1000); await flushPromises();
  expect(backgroundNavigation.active).toBe(true);
  await wrapper.get('.navigation-overview-heading button').trigger('click'); await flushPromises();
  expect(wrapper.find('.turn-card').exists()).toBe(true);
  expect(wrapper.text()).toContain('剩余');
});

it('preserves live GPS tracking and seeds the fusion engine after selecting an alternative', async () => {
  navigationEngine.value = 'route-fusion';
  const wrapper = await navigate(true);
  gps.point = [120.2, 30.281];
  gps.listeners.forEach(fn => fn({ longitude: 120.2, latitude: 30.281, accuracy: 1, heading: 0,
    speed: 10, timestamp: Date.now(), source: 'gps', altitude: null, altitudeAccuracy: null }));
  await flushPromises();
  routeReply = origin => ({ data: { status: 'ok', data: { state: 'ready', routes: routesFrom(origin), routeToken: 'live-fresh' } } });
  const clears = vi.mocked(navigator.geolocation.clearWatch).mock.calls.length;
  await wrapper.get('.turn-card').trigger('click'); await flushPromises();
  await wrapper.findAll('.navigation-route-options button')[1].trigger('click'); await flushPromises();
  expect(vi.mocked(navigator.geolocation.clearWatch).mock.calls).toHaveLength(clears);
  expect(gps.listeners.has('amap-navigation')).toBe(true);
  expect(backgroundNavigation.active).toBe(true);
  expect(backgroundNavigation.simulated).toBe(false);
  expect(lastCall('/api/amap-app/navigation-events').payload)
    .toEqual({ routeToken: 'live-fresh', routeIndex: 1 });
  await vi.advanceTimersByTimeAsync(500); await flushPromises();
  expect(wrapper.find('.turn-card').exists()).toBe(true);
  expect(wrapper.text()).toContain('路线融合');
});

it('does not restore route choices when a pending refresh completes after exiting navigation', async () => {
  const wrapper = await navigate();
  let resolveReply!: (value: any) => void;
  routeReply = () => new Promise(resolve => { resolveReply = resolve; });
  await wrapper.get('.turn-card').trigger('click'); await flushPromises();
  await wrapper.findAll('button').find(button => button.text() === '退出导航')!.trigger('click'); await flushPromises();
  resolveReply({ data: { status: 'ok', data: { state: 'ready', routes: routesFrom(gps.point as Point), routeToken: 'after-exit' } } });
  await flushPromises();
  expect(wrapper.find('.route-options').exists()).toBe(false);
  expect(backgroundNavigation.active).toBe(false);
  expect(calls.some(call => call.payload?.routeToken === 'after-exit')).toBe(false);
});

it('switches to a tunnel and back to the surface using the latest vehicle position without stopping GPS', async () => {
  const layeredRoutes = (origin: Point) => {
    const ground = routesFrom(origin)[0]; ground.steps[0].road = '环城路';
    ground.roadLinks = [{ start: 0, end: 3, road: '环城路', id: '1', linkType: 0 }];
    const tunnel = { ...ground, id: 1, steps: [{ ...ground.steps[0], road: '环城隧道' }],
      roadLinks: [{ start: 0, end: 3, road: '环城隧道', id: '2', linkType: 2 }] };
    return [ground, tunnel];
  };
  // The initial session has no tunnel candidate, so exercise the request race.
  routeReply = origin => ({ data: { status: 'ok', data: { state: 'ready', routes: layeredRoutes(origin).slice(0, 1), routeToken: 'surface' } } });
  const wrapper = await navigate(true);
  const clears = vi.mocked(navigator.geolocation.clearWatch).mock.calls.length;
  expect(wrapper.find('.road-switch').exists()).toBe(false);
  expect(wrapper.findAll('.map-controls .road-switch-direct').map(button => button.text())).toEqual(['高架', '隧道']);
  let resolveReply!: (value: any) => void;
  routeReply = () => new Promise(resolve => { resolveReply = resolve; });
  await correctRoad(wrapper, '隧道');
  const requested = lastCall('/api/amap-app/route').payload.origin as Point;
  gps.point = [120.2, 30.281];
  gps.listeners.forEach(fn => fn({ longitude: 120.2, latitude: 30.281, accuracy: 1, heading: 0,
    speed: 10, timestamp: Date.now(), source: 'gps' }));
  await flushPromises();
  resolveReply({ data: { status: 'ok', data: { state: 'ready', routes: layeredRoutes(requested), routeToken: 'tunnel' } } });
  await flushPromises();
  expect(wrapper.text()).toContain('已切换至隧道');
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'tunnel', routeIndex: 1 });
  expect(wrapper.text()).toContain('环城隧道');
  routeReply = origin => ({ data: { status: 'ok', data: { state: 'ready', routes: layeredRoutes(origin), routeToken: 'surface-again' } } });
  const requests = calls.filter(call => call.url === '/api/amap-app/route').length;
  expect(wrapper.findAll('.road-switch-direct').map(button => button.text())).toEqual(['地面']);
  await correctRoad(wrapper, '地面');
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(requests);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'tunnel', routeIndex: 0 });
  expect(wrapper.text()).toContain('已切换至地面');
  expect(vi.mocked(navigator.geolocation.clearWatch).mock.calls).toHaveLength(clears);
  expect(backgroundNavigation.active).toBe(true);
});

it('corrects to a known same-name native side link without a network replan or changing its session', async () => {
  routeReply = origin => {
    const alternatives = routesFrom(origin);
    alternatives.forEach((route, index) => {
      route.steps[0].road = '环城路';
      route.roadLinks = [{ start: 0, end: 3, road: '环城路',
        id: String(9007199254740992n + BigInt(index)), roadProperty: index === 0 ? 1 : 7 }];
    });
    return { data: { status: 'ok', data: { state: 'ready', routes: alternatives, routeToken: 'native-links' } } };
  };
  const wrapper = await navigate(true);
  const requests = calls.filter(call => call.url === '/api/amap-app/route').length;
  const clears = vi.mocked(navigator.geolocation.clearWatch).mock.calls.length;
  routeReply = () => Promise.reject(new Error('must not replan a known candidate'));
  expect(wrapper.findAll('.road-switch-direct').map(button => button.text())).toEqual(['辅路']);
  await correctRoad(wrapper, '辅路');
  expect(wrapper.findAll('.road-switch-direct').map(button => button.text())).toEqual(['主路']);
  expect(wrapper.text()).toContain('已切换至辅路');
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(requests);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'native-links', routeIndex: 1 });
  expect(vi.mocked(navigator.geolocation.clearWatch).mock.calls).toHaveLength(clears);
  await vi.advanceTimersByTimeAsync(1000); await flushPromises();
  expect(backgroundNavigation.active).toBe(true);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'native-links', routeIndex: 1 });
});

it('continues the existing navigation when there is no identifiable nearby tunnel route', async () => {
  routeReply = origin => {
    const source = routesFrom(origin)[0];
    source.roadLinks = [{ start: 0, end: 3, road: '环城路', id: '1', linkType: 0 }];
    return { data: { status: 'ok', data: { state: 'ready', routes: [source], routeToken: 'initial' } } };
  };
  const wrapper = await navigate(true);
  routeReply = origin => ({ data: { status: 'ok', data: { state: 'ready', routes: routesFrom(origin), routeToken: 'no-tunnel' } } });
  await correctRoad(wrapper, '隧道');
  expect(wrapper.text()).toContain('附近没有可确认的隧道路线');
  expect(lastCall('/api/amap-app/navigation-events').payload.routeToken).toBe('initial');
  expect(backgroundNavigation.active).toBe(true);
});

it('uses native old-link constrained replanning and preserves the selected native index after the car moves', async () => {
  routeReply = origin => {
    const source = routesFrom(origin)[0];
    source.roadLinks = [{ start: 0, end: 3, road: '环城路', id: '9007199254740993', roadProperty: 7 }];
    return { data: { status: 'ok', data: { state: 'ready', routes: [source], routeToken: 'side-session' } } };
  };
  const wrapper = await navigate(true);
  const requests = calls.filter(call => call.url === '/api/amap-app/route').length;
  let resolveReply!: (value: any) => void;
  switchReply = () => new Promise(resolve => { resolveReply = resolve; });
  await correctRoad(wrapper, '主路');
  const payload = lastCall('/api/amap-app/switch-road').payload;
  expect(payload).toMatchObject({ routeToken: 'side-session', routeIndex: 0, linkId: '9007199254740993',
    linkStart: 0, point: [120.2, 30.28], accuracy: 1, speed: 10, heading: 0 });
  gps.point = [120.2, 30.281];
  gps.listeners.forEach(fn => fn({ longitude: 120.2, latitude: 30.281, accuracy: 1, heading: 0,
    speed: 10, timestamp: Date.now(), source: 'gps' }));
  await flushPromises();
  const candidates = routesFrom(payload.point);
  candidates[0].roadLinks = [{ start: 0, end: 3, road: '主路', id: payload.linkId, roadProperty: 1 }];
  candidates[1].roadLinks = [{ start: 0, end: 3, road: '环城路', id: '9007199254740992', roadProperty: 1 }];
  resolveReply({ data: { status: 'ok', data: { state: 'ready', routes: candidates, routeToken: 'corrected' } } });
  await flushPromises();
  expect(wrapper.text()).toContain('已切换至主路');
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(requests);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'corrected', routeIndex: 1 });
  await vi.advanceTimersByTimeAsync(3000); await flushPromises();
  expect(backgroundNavigation.active).toBe(true);
  expect(lastCall('/api/amap-app/traffic-signals').payload.position[1]).toBeCloseTo(30.281, 6);
});

it('preserves the running native session when old-link exclusion leaves no bindable start road', async () => {
  routeReply = origin => {
    const source = routesFrom(origin)[0];
    source.roadLinks = [{ start: 0, end: 3, road: '环城路', id: '1', roadProperty: 7 }];
    return { data: { status: 'ok', data: { state: 'ready', routes: [source], routeToken: 'side-session' } } };
  };
  const wrapper = await navigate(true);
  const requests = calls.filter(call => call.url === '/api/amap-app/route').length;
  switchReply = () => ({ data: { status: 'ok', data: { state: 'absent' } } });
  await correctRoad(wrapper, '主路');
  expect(wrapper.text()).toContain('附近没有可确认的主路路线');
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(requests);
  expect(lastCall('/api/amap-app/navigation-events').payload.routeToken).toBe('side-session');
  expect(backgroundNavigation.active).toBe(true);
});

it('queries native layer alternatives without excluding the overlapping surface road and preserves live navigation', async () => {
  routeReply = origin => {
    const source = routesFrom(origin)[0];
    source.steps[0].road = '文一西路隧道';
    source.roadLinks = [{ start: 0, end: 3, road: '文一西路隧道', id: '11', linkType: 2 }];
    return { data: { status: 'ok', data: { state: 'ready', routes: [source], routeToken: 'west-tunnel' } } };
  };
  const wrapper = await navigate(true);
  const clears = vi.mocked(navigator.geolocation.clearWatch).mock.calls.length;
  let resolveReply!: (value: any) => void;
  routeReply = () => new Promise(resolve => { resolveReply = resolve; });
  switchReply = () => { throw new Error('must not geometrically exclude an overlapping layer'); };
  await correctRoad(wrapper, '地面');
  expect(calls.some(call => call.url === '/api/amap-app/switch-road')).toBe(false);
  const request = lastCall('/api/amap-app/route').payload;
  expect(request).toEqual({ origin: [120.2, 30.28], destination: end });
  gps.point = [120.2, 30.281];
  gps.listeners.forEach(fn => fn({ longitude: 120.2, latitude: 30.281, accuracy: 1, heading: 0,
    speed: 10, timestamp: Date.now(), source: 'gps' }));
  await flushPromises();
  const alternatives = routesFrom(request.origin);
  // Reject a duplicate of the current link even when its DTO claims surface.
  alternatives[0].roadLinks = [{ start: 0, end: 3, road: '', id: '11', linkType: 0 }];
  alternatives[1].roadLinks = [{ start: 0, end: 3, road: '', id: '12', linkType: 0 }];
  alternatives[2].roadLinks = [{ start: 0, end: 3, road: '', id: '13', linkType: 2 }];
  resolveReply({ data: { status: 'ok', data: { state: 'ready', routes: alternatives, routeToken: 'west-layers' } } });
  await flushPromises();
  expect(wrapper.text()).toContain('已切换至地面');
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'west-layers', routeIndex: 1 });
  expect(vi.mocked(navigator.geolocation.clearWatch).mock.calls).toHaveLength(clears);
  expect(backgroundNavigation.simulated).toBe(false);
  const requests = calls.filter(call => call.url === '/api/amap-app/route').length;
  await correctRoad(wrapper, '隧道');
  expect(wrapper.text()).toContain('已切换至隧道');
  expect(calls.filter(call => call.url === '/api/amap-app/route')).toHaveLength(requests);
  expect(lastCall('/api/amap-app/navigation-events').payload).toEqual({ routeToken: 'west-layers', routeIndex: 2 });
  await vi.advanceTimersByTimeAsync(3000); await flushPromises();
  expect(backgroundNavigation.active).toBe(true);
  expect(lastCall('/api/amap-app/traffic-signals').payload.position[1]).toBeCloseTo(30.281, 6);
});
