// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { ref } from 'vue';
import BvPlayer from './BvPlayer.vue';

const mocks = vi.hoisted(() => ({ get: vi.fn(), create: vi.fn() }));
vi.mock('@/functions/requests', () => ({ get: mocks.get, post: vi.fn() }));
vi.mock('@/functions/biliDirect', () => ({ createDirectSource: mocks.create }));
vi.mock('@/functions/useAudioChannel', () => ({ useAudioChannel: () => ({
  channelAudio: ref(null), startAudioChannel: vi.fn(), restoreAudioChannel: vi.fn(),
}) }));

let wrapper: VueWrapper | undefined;
let player: FakePlayer;
class FakePlayer {
  logger = { logInfo: vi.fn() };
  play = vi.fn(); stop = vi.fn(); destroy = vi.fn();
  getState = () => 0;
  setLoadingDiv = vi.fn(); setFinishCallback = vi.fn(); setTimeCallback = vi.fn(); setTrack = vi.fn();
  showLoading = vi.fn(); hideLoading = vi.fn(); formatTime = () => '00:00:00';
  duration = 90000; displayDuration = '00:01:30';
  constructor() { player = this; }
}

function fakeSource(startMs = 0) {
  return { startMs, duration: 90000, cancel: vi.fn() };
}
function open() {
  wrapper = mount(BvPlayer, { props: { type: 'bv', id: 'BVtest' }, global: { stubs: {
    ElButton: { template: '<button><slot /></button>' }, ElIcon: true, VideoPlay: true,
    ElPopover: { template: '<div><slot name="reference"/><slot/></div>' },
    ElSwitch: true, ElRow: { template: '<div><slot/></div>' },
    ElCol: { template: '<div><slot/></div>' }, ElText: { template: '<span><slot/></span>' },
  } } });
  return wrapper;
}

beforeEach(() => {
  mocks.get.mockReset(); mocks.create.mockReset();
  vi.stubGlobal('Player', FakePlayer);
  vi.spyOn(console, 'info').mockImplementation(() => {});
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/api/config') return {};
    if (url.includes('/video/')) return { title: 'Test', epList: [{ bvid: 'BVtest', cid: 1, title: 'Episode' }] };
    if (url.includes('/dm/')) return { dm: [] };
    return {};
  });
  mocks.create.mockImplementation(async (_manifest, startMs) => fakeSource(startMs));
});
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined;
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

it('defaults to the source API without invoking server media or info endpoints', async () => {
  open(); await flushPromises();
  expect(mocks.get).toHaveBeenCalledWith('/api/bilibili/bv/BVtest/1/source?transport=relay', expect.any(String));
  expect(player.play).toHaveBeenCalledTimes(1);
  expect(player.play.mock.calls[0][0]).toBe('stream://browser-dash');
  expect(player.play.mock.calls[0][5]).toMatchObject({ startMs: 0 });
  expect(mocks.get.mock.calls.some(([url]) => url.endsWith('/info'))).toBe(false);
});

it('retries relay failures using browser processing without invoking legacy FFmpeg', async () => {
  mocks.create.mockRejectedValueOnce(new Error('CDN unavailable'));
  const view = open(); await flushPromises();
  expect(view.get('[role="alert"]').text()).toContain('CDN unavailable');
  await view.findAll('button').find(b => b.text() === '重试')!.trigger('click');
  await flushPromises();
  expect(player.play.mock.calls[0][0]).toBe('stream://browser-dash');
  expect(player.play.mock.calls[0][5]).toMatchObject({ startMs: 0 });
  expect(mocks.get.mock.calls.some(([url]) => url.endsWith('/info'))).toBe(false);
});

it('cancels a superseded request and ignores its late result when seeking', async () => {
  const pending: { resolve: (source: ReturnType<typeof fakeSource>) => void; controller: AbortController }[] = [];
  mocks.create.mockImplementation((_manifest, _startMs, controller) => new Promise(resolve => pending.push({ resolve, controller })));
  const view = open(); await flushPromises();
  await view.get('input[type="range"]').setValue('60000');
  await flushPromises();
  expect(pending.length).toBe(2);
  expect(pending[0].controller.signal.aborted).toBe(true);
  const latest = fakeSource(60000), stale = fakeSource(0);
  pending[1].resolve(latest); await flushPromises();
  pending[0].resolve(stale); await flushPromises();
  expect(player.play).toHaveBeenCalledTimes(1);
  expect(player.play.mock.calls[0][5]).toBe(latest);
  expect(stale.cancel).toHaveBeenCalled();
});

it('aborts loading and destroys workers on unmount without starting late playback', async () => {
  let resolve!: (source: ReturnType<typeof fakeSource>) => void;
  let controller!: AbortController;
  mocks.create.mockImplementation((_manifest, _startMs, current) => {
    controller = current;
    return new Promise(done => { resolve = done; });
  });
  open(); await flushPromises();
  wrapper!.unmount(); wrapper = undefined;
  const source = fakeSource(); resolve(source); await flushPromises();
  expect(controller.signal.aborted).toBe(true);
  expect(source.cancel).toHaveBeenCalled();
  expect(player.destroy).toHaveBeenCalled();
  expect(player.play).not.toHaveBeenCalled();
});

it('stops immediately on return even before the parent unmounts it', async () => {
  const view = open(); await flushPromises();
  const controller = mocks.create.mock.calls[0][2] as AbortController;
  await view.get('[aria-label="返回视频列表"]').trigger('click');
  expect(controller.signal.aborted).toBe(true);
  expect(player.destroy).toHaveBeenCalledTimes(1);
  await view.get('input[type="range"]').setValue('60000');
  await flushPromises();
  expect(player.play).toHaveBeenCalledTimes(1);
  view.unmount(); wrapper = undefined;
  expect(player.destroy).toHaveBeenCalledTimes(1);
});
