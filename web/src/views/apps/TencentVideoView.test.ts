// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { ref } from 'vue';
import TencentVideoView from './TencentVideoView.vue';
vi.mock('@/functions/useAudioChannel', () => ({ useAudioChannel: () => ({
  channelAudio: ref(null), startAudioChannel: vi.fn(), restoreAudioChannel: vi.fn(),
}) }));
let view: VueWrapper | undefined;
let player: any;
const fetchMock = vi.fn();
const response = (data: unknown) => ({ ok: true, json: async () => ({ status: 'ok', data }) });
const item = (id: string, title = id) => ({ id, vid: id, title, cover: '', subtitle: '', kind: '视频', episodes: [] });
class FakePlayer {
  destroy = vi.fn(); play = vi.fn(() => ({ e: 0 }));
  setLoadingDiv = vi.fn(); setTrack = vi.fn(); setFinishCallback = vi.fn(); setTimeCallback = vi.fn();
  getState = () => 1; pause = vi.fn();
  constructor() { player = this; }
}
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  localStorage.clear(); fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('Player', FakePlayer);
  fetchMock.mockImplementation(async (url: string) => url.includes('/home?') ? response({ items: [], nextCursor: null }) : response({
    vid: 'q326831cny0', title: 'Public video', url: '/api/tencent-video/media/token',
    urls: ['https://omex.tc.qq.com/video.mp4?vkey=temporary'],
    pageUrl: 'https://v.qq.com/x/page/q326831cny0.html', duration: 215,
  }));
});
afterEach(() => { view?.unmount(); view = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks(); });
async function submit() {
  view = mount(TencentVideoView);
  await view.get('input#tencent-link').setValue('q326831cny0');
  await view.get('details form').trigger('submit'); await flushPromises();
}
it('passes CDN sources before the relay to WASM and saves only public metadata', async () => {
  await submit();
  expect(player.play).toHaveBeenCalledWith('/api/tencent-video/media/token', expect.anything(), expect.any(Function), 524288, false, undefined,
    ['https://omex.tc.qq.com/video.mp4?vkey=temporary', '/api/tencent-video/media/token']);
  expect(localStorage.getItem('tmc.tencent-video.recent.v1')).not.toContain('vkey');
  expect(localStorage.getItem('tmc.tencent-video.recent.v1')).not.toContain('token');
  await view!.findAll('button').find(b => b.text() === '关闭播放器')!.trigger('click');
  expect(player.destroy).toHaveBeenCalledOnce();
  expect(view!.find('canvas').exists()).toBe(false);
});
it('does not start a late source response after unmount', async () => {
  let resolve!: (value: unknown) => void;
  fetchMock.mockImplementation((url: string) => url.includes('/home?') ? Promise.resolve(response({ items: [] })) : new Promise(done => { resolve = done; }));
  await submit();
  const signal = fetchMock.mock.calls.find(([url]) => url.includes('/source'))![1].signal;
  view!.unmount(); view = undefined;
  resolve({ ok: true, json: async () => ({ status: 'ok', data: {} }) });
  await flushPromises(); expect(signal.aborted).toBe(true);
});
it('shows the failing video and retries with only the byte relay', async () => {
  await submit();
  const failedPlayer = player;
  failedPlayer.play.mock.calls[0][2]({ error: -1, status: 502, message: '读取视频信息失败，服务端转接：HTTP 502' });
  await flushPromises();
  expect(view!.get('[role="alert"]').text()).toContain('HTTP 502');
  expect(view!.get('[role="alert"]').text()).toContain('q326831cny0');
  expect(failedPlayer.destroy).toHaveBeenCalledOnce();
  await view!.findAll('button').find(b => b.text() === '仅用转接重试')!.trigger('click'); await flushPromises();
  expect(player.play.mock.calls[0][6]).toEqual(['/api/tencent-video/media/token']);
});
it('shows source restrictions without creating a player', async () => {
  fetchMock.mockImplementation(async (url: string) => url.includes('/home?') ? response({ items: [] }) : { ok: false, json: async () => ({ message: '加密视频暂不支持' }) });
  await submit(); expect(view!.get('[role="alert"]').text()).toContain('加密视频暂不支持');
  expect(view!.find('canvas').exists()).toBe(false);
});

it('loads real catalog cards by default and opens a video without entering a link', async () => {
  const original = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation((url: string) => url.includes('/home?') ? Promise.resolve(response({ items: [item('q326831cny0', '首页视频')] })) : original(url));
  view = mount(TencentVideoView); await flushPromises();
  await view.get('.catalog-card').trigger('click'); await flushPromises();
  expect(JSON.parse(fetchMock.mock.calls.find(([url]) => url.includes('/source'))![1].body)).toEqual({ url: 'q326831cny0' });
  expect(player.play).toHaveBeenCalledOnce();
});

it('cancels stale searches, keeps the latest query and deduplicates pagination', async () => {
  let resolveOld!: (value: unknown) => void;
  fetchMock.mockImplementation((url: string) => {
    if (url.includes('/home?')) return Promise.resolve(response({ items: [] }));
    if (url.includes('q=old')) return new Promise(resolve => { resolveOld = resolve; });
    return Promise.resolve(response({ items: [item('q326831cny0', '新结果')], nextPage: url.includes('page=0') ? 1 : null }));
  });
  view = mount(TencentVideoView); await flushPromises();
  await view.get('#tencent-search').setValue('old'); await view.get('.search-form').trigger('submit');
  const oldSignal = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][1].signal;
  await view.get('#tencent-search').setValue('new'); await view.get('.search-form').trigger('submit'); await flushPromises();
  expect(oldSignal.aborted).toBe(true);
  resolveOld(response({ items: [item('o3013za7cse', '旧结果')] })); await flushPromises();
  expect(view.text()).not.toContain('旧结果');
  await view.findAll('button').find(b => b.text() === '加载更多')!.trigger('click'); await flushPromises();
  expect(view.findAll('.catalog-card')).toHaveLength(1);
  expect(fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]).toContain('q=new&page=1');
  expect(view.text()).not.toContain('加载更多');
});
