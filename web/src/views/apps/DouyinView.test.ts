// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { ref } from 'vue';
import DouyinView from './DouyinView.vue';
vi.mock('@/functions/useAudioChannel', () => ({ useAudioChannel: () => ({
  channelAudio: ref(null), startAudioChannel: vi.fn(), restoreAudioChannel: vi.fn(),
}) }));
let view: VueWrapper | undefined;
const players: FakePlayer[] = [], fetchMock = vi.fn();
const vid = '7674149236469451482';
const clip = { vid, title: '公开短视频', pageUrl: `https://www.douyin.com/video/${vid}`, cover: '' };
const response = (data: unknown) => ({ ok: true, json: async () => ({ status: 'ok', data }) });
class FakePlayer {
  destroy = vi.fn(); play = vi.fn(() => ({ e: 0 })); pause = vi.fn(); resume = vi.fn();
  setLoadingDiv = vi.fn(); setTrack = vi.fn(); setFinishCallback = vi.fn((callback: () => void) => { this.finish = callback; }); setTimeCallback = vi.fn();
  finish: (() => void) | undefined;
  getState = () => 1;
  constructor() { players.push(this); }
}
beforeEach(() => {
  players.length = 0; localStorage.clear(); fetchMock.mockReset();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.stubGlobal('Player', FakePlayer); vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.includes('/source')) {
      const requested = JSON.parse(String(options?.body)).url as string;
      const requestedVid = requested.match(/\d{15,22}/)?.[0] || vid;
      return response({ ...clip, vid: requestedVid, pageUrl: `https://www.douyin.com/video/${requestedVid}`,
        url: '/api/douyin/media/token', urls: ['https://v5.zjcdn.com/test.mp4?secret=temporary'] });
    }
    return response({ items: [clip, { ...clip, vid: '7674149236469451483', pageUrl: 'https://www.douyin.com/video/7674149236469451483' }] });
  });
});
afterEach(() => { view?.unmount(); view = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks(); });
async function openFirst() {
  view = mount(DouyinView); await flushPromises();

}
it('automatically opens the first video with WASM and persists only public metadata', async () => {
  await openFirst(); expect(players[0].play).toHaveBeenCalledOnce();
  expect((players[0] as any).chunkSize).toBe(1024 * 1024);
  expect((players[0] as any).maxAheadSeconds).toBe(24);
  expect(players[0].play.mock.calls[0]).toEqual(['/api/douyin/media/token', expect.anything(), expect.any(Function),
    524288, false, undefined, ['/api/douyin/media/token']]);
  expect(view!.find('video').exists()).toBe(false);
  expect(localStorage.getItem('tmc.douyin.recent.v1')).not.toMatch(/token|secret/);
});
it('destroys the previous player on next video, close and unmount', async () => {
  await openFirst();
  await view!.findAll('button').find(b => b.text() === '下一条')!.trigger('click'); await flushPromises();
  expect(players[0].destroy).toHaveBeenCalledOnce();
  view!.unmount(); view = undefined;
  expect(players[1].destroy).toHaveBeenCalledOnce();
});
it('switches videos with vertical swipes on the whole video surface', async () => {
  await openFirst();
  const screen = view!.find('.screen');
  await screen.trigger('touchstart', { touches: [{ clientX: 100, clientY: 280 }] });
  await screen.trigger('touchend', { changedTouches: [{ clientX: 103, clientY: 150 }] });
  await flushPromises();
  expect(players).toHaveLength(2);
  expect(players[0].destroy).toHaveBeenCalledOnce();
  await screen.trigger('touchstart', { touches: [{ clientX: 100, clientY: 150 }] });
  await screen.trigger('touchend', { changedTouches: [{ clientX: 103, clientY: 280 }] });
  await flushPromises();
  expect(players).toHaveLength(3);
});
it('enables auto-next by default and stops at the end of the queue', async () => {
  await openFirst();
  const option = view!.find('.auto-next input');
  expect((option.element as HTMLInputElement).checked).toBe(true);
  players[0].finish?.(); await flushPromises();
  expect(players).toHaveLength(2);
  players[1].finish?.(); await flushPromises();
  expect(players).toHaveLength(2);
});
it('respects a saved disabled choice and persists re-enabling auto-next', async () => {
  localStorage.setItem('tmc.douyin.auto-next.v1', 'false');
  await openFirst();
  const option = view!.find('.auto-next input');
  expect((option.element as HTMLInputElement).checked).toBe(false);
  players[0].finish?.(); await flushPromises();
  expect(players).toHaveLength(1);
  await option.setValue(true);
  expect(localStorage.getItem('tmc.douyin.auto-next.v1')).toBe('true');
  players[0].finish?.(); await flushPromises();
  expect(players).toHaveLength(2);
});
it('aborts outstanding playback and ignores source responses after exit', async () => {
  let resolve!: (value: unknown) => void;
  fetchMock.mockImplementation((url: string) => url.includes('/source') ? new Promise(done => { resolve = done; }) : Promise.resolve(response({ items: [clip] })));
  await openFirst(); const signal = fetchMock.mock.calls.find(([url]) => url.includes('/source'))![1].signal;
  view!.unmount(); view = undefined; resolve(response({ ...clip, urls: [], url: 'unused' })); await flushPromises();
  expect(signal.aborted).toBe(true); expect(players).toHaveLength(0);
});
it('reports restrictions without a fake playable result', async () => {
  fetchMock.mockImplementation(async (url: string) => url.includes('/source')
    ? { ok: false, json: async () => ({ status: 'unavailable', message: '需要官方验证' }) } : response({ items: [clip] }));
  await openFirst(); expect(view!.text()).toContain('需要官方验证'); expect(players).toHaveLength(0);
});
it('shows a search login restriction and keeps the current video queue', async () => {
  const normalFetch = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation((url: string, options?: RequestInit) => url.includes('/search')
    ? Promise.resolve({ ok: false, json: async () => ({ status: 'unavailable', message: '抖音搜索需要登录，请扫码登录后重试' }) })
    : normalFetch(url, options));
  await openFirst();
  await view!.find('input[aria-label="搜索抖音视频"]').setValue('特斯拉');
  await view!.find('form.search').trigger('submit'); await flushPromises();
  expect(view!.find('.catalog-error').text()).toContain('抖音搜索需要登录');
  expect(view!.find('.details .eyebrow').text()).toBe('1 / 2');
  expect(view!.findAll('button').find(b => b.text() === '下一条')!.attributes('disabled')).toBeUndefined();
});

it('keeps comments and the video queue on the right without a landing grid', async () => {
  await openFirst();
  expect(view!.find('.stage canvas').exists()).toBe(true);
  expect(view!.find('.side .comments').exists()).toBe(true);
  expect(view!.text()).not.toContain('发现精彩');
  expect(view!.find('.catalog').exists()).toBe(false);
  await view!.findAll('button').find(b => b.text() === '视频列表')!.trigger('click');
  expect(view!.find('.side .catalog').exists()).toBe(true);
  expect(players).toHaveLength(1);
});
