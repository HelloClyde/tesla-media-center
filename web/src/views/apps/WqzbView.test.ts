// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import WqzbView from './WqzbView.vue';

vi.mock('@/functions/wqzbStream', () => ({ getWqzbStream: vi.fn().mockResolvedValue('https://example.com/live.flv') }));
vi.mock('@/functions/useAudioChannel', async () => {
  const { ref } = await import('vue');
  return { useAudioChannel: () => ({ channelAudio: ref(null), startAudioChannel: vi.fn() }) };
});

afterEach(() => vi.unstubAllGlobals());

it('opens and closes a live room inside the content area without a Vue update error', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: URL) => ({
    ok: true,
    json: async () => ({ code: 200, data: url.pathname.includes('channel')
      ? [{ id: 53, channel_name: '推荐' }]
      : [{ id: 1, name: '正在热播', rooms: [{ chatroom_id: 123, room_title: '测试直播' }] }] }),
  })));
  vi.stubGlobal('Player', class {
    setLoadingDiv() {}
    setAudioBlockedCallback() {}
    play() { return { e: 0 }; }
    destroy() {}
  });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});

  const view = mount({ components: { WqzbView }, template: '<div class="main-view"><WqzbView /></div>' }, { attachTo: document.body });
  try {
    await flushPromises();
    const app = view.get('.wqzb-app').element as HTMLElement;
    app.scrollTop = 350;
    await view.get('button[aria-label="观看 测试直播"]').trigger('click');
    await flushPromises();
    expect(app.scrollTop).toBe(0);
    expect(view.get('.wqzb-player-backdrop').element.parentElement?.classList.contains('wqzb-app')).toBe(true);
    expect(view.text()).toContain('测试直播');
    await view.get('.wqzb-player-head button').trigger('click');
    await flushPromises();
    expect(view.find('.wqzb-player-backdrop').exists()).toBe(false);
    expect(app.scrollTop).toBe(350);
  } finally {
    view.unmount();
    vi.restoreAllMocks();
  }
});
