// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import BackgroundAppDock from './BackgroundAppDock.vue';
import { backgroundMusic as music, musicCommands, clearBackgroundMusic } from '@/stores/backgroundMusic';
import { publishBackgroundNavigation, clearBackgroundNavigation } from '@/stores/backgroundNavigation';
afterEach(() => { clearBackgroundMusic(); clearBackgroundNavigation(); });
it('uses one entry and shows music and navigation together with independent controls', async () => {
  const next = vi.fn(), stop = vi.fn(); musicCommands.next = next;
  Object.assign(music, { song: { title: '测试歌曲', singer: '歌手', cover: '' }, playing: true, nextDisabled: false });
  publishBackgroundNavigation({ simulated: false, muted: false, arrow: '↑', instruction: '200 米后左转', road: '测试路', remaining: '2 公里', status: '' }, { stop });
  const router = createRouter({ history: createMemoryHistory(), routes: ['/apps/home', '/apps/amap', '/apps/qqmusic'].map(path => ({ path, component: { template: '<div />' } })) });
  await router.push('/apps/home'); await router.isReady();
  const view = mount(BackgroundAppDock, { global: { plugins: [router], stubs: { teleport: true } } });
  try {
    expect(view.findAll('.background-slot')).toHaveLength(1);
    expect(view.get('.count-badge').text()).toBe('2');
    await view.get('[aria-label="后台应用列表"]').trigger('click'); await flushPromises();
    expect(view.findAll('.task-card')).toHaveLength(2);
    await view.get('[aria-label="下一首"]').trigger('click'); expect(next).toHaveBeenCalledOnce(); expect(stop).not.toHaveBeenCalled();
    expect(view.get('[aria-label="后台应用面板"]').text()).toContain('200 米后左转');
    await view.findAll('button').find(button => button.text() === '打开播放器')!.trigger('click'); await flushPromises();
    expect(router.currentRoute.value.path).toBe('/apps/qqmusic'); expect(view.find('.dock-panel').exists()).toBe(false);
    clearBackgroundMusic(); await flushPromises(); expect(view.findAll('.background-slot')).toHaveLength(1);
    await view.get('[aria-label="后台应用列表"]').trigger('click'); await flushPromises(); expect(view.findAll('.task-card')).toHaveLength(1);
    await view.findAll('button').find(button => button.text() === '打开导航')!.trigger('click'); await flushPromises();
    expect(router.currentRoute.value.path).toBe('/apps/amap');
    clearBackgroundNavigation(); await flushPromises(); expect(view.findAll('.background-slot')).toHaveLength(1);
  } finally { view.unmount(); }
});
