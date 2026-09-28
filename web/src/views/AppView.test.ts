// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { defineComponent, h, onBeforeUnmount, Teleport } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import AppView from './AppView.vue';
import { backgroundNavigation, clearBackgroundNavigation, publishBackgroundNavigation } from '@/stores/backgroundNavigation';
import { backgroundApps } from '@/stores/backgroundApps';
import { clearBackgroundMusic } from '@/stores/backgroundMusic';
afterEach(() => { clearBackgroundMusic(); clearBackgroundNavigation(); });

it('retains only the QQ player across app navigation and disposes it on logout', async () => {
  const created = vi.fn(), stopped = vi.fn(), otherStopped = vi.fn();
  const Music = defineComponent({ name: 'QQMusicView', setup() {
    created(); onBeforeUnmount(stopped);
    return () => h(Teleport, { to: 'body' }, h('audio', { 'data-test': 'persistent-audio' }));
  } });
  const Other = defineComponent({ setup() { onBeforeUnmount(otherStopped); return () => h('div', 'Map'); } });
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/apps', component: AppView, children: [
      { path: 'qqmusic', component: Music }, { path: 'amap', component: Other }, { path: 'home', component: Other },
    ] }, { path: '/login', component: { render: () => h('div', 'Login') } },
  ] });
  await router.push('/apps/qqmusic'); await router.isReady();
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs: { 'el-icon': true } } });
  const audio = document.querySelector('[data-test=persistent-audio]')!;
  expect(audio.isConnected).toBe(true);
  await router.push('/apps/amap'); await flushPromises();
  expect(stopped).not.toHaveBeenCalled();
  expect(document.querySelector('[data-test=persistent-audio]')).toBe(audio);
  expect(audio.isConnected).toBe(true);
  await router.push('/apps/qqmusic'); await flushPromises();
  expect(document.querySelector('[data-test=persistent-audio]')).toBe(audio);
  expect(created).toHaveBeenCalledTimes(1);
  expect(otherStopped).toHaveBeenCalledTimes(1);
  await router.push('/login'); await flushPromises();
  expect(stopped).toHaveBeenCalledTimes(1);
  expect(audio.isConnected).toBe(false);
  wrapper.unmount();
});

it('retains active navigation, exposes floating controls and removes it on logout', async () => {
  const created = vi.fn(), stopped = vi.fn();
  const Navigation = defineComponent({ name: 'AmapAppView', setup() {
    created();
    publishBackgroundNavigation({ simulated: false, muted: false, arrow: '↰', instruction: '200 米后左转', road: '测试路', remaining: '2 公里', status: '实时导航中' }, { toggleVoice: () => { backgroundNavigation.muted = !backgroundNavigation.muted; }, stop: clearBackgroundNavigation });
    onBeforeUnmount(() => { stopped(); clearBackgroundNavigation(); });
    return () => h('div', 'Navigation');
  } });
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/apps', component: AppView, children: [{ path: 'amap', component: Navigation }, { path: 'home', component: { render: () => h('div') } }] },
    { path: '/login', component: { render: () => h('div') } },
  ] });
  await router.push('/apps/amap'); await router.isReady();
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs: { 'el-icon': true } } });
  await flushPromises(); expect(wrapper.find('[aria-label="后台导航"]').exists()).toBe(false);
  await router.push('/apps/home'); await flushPromises();
  expect(stopped).not.toHaveBeenCalled(); expect(backgroundApps.amap.running).toBe(true);
  expect(wrapper.find('[aria-label="后台导航"]').text()).toContain('200 米后左转');
  await wrapper.findAll('button').find(button => button.text() === '静音')!.trigger('click');
  expect(backgroundNavigation.muted).toBe(true);
  await wrapper.find('[aria-label="返回高德导航"]').trigger('click'); await flushPromises();
  expect(router.currentRoute.value.path).toBe('/apps/amap'); expect(created).toHaveBeenCalledTimes(1);
  await router.push('/login'); await flushPromises();
  expect(stopped).toHaveBeenCalledTimes(1); expect(backgroundApps.amap).toBeUndefined(); expect(backgroundNavigation.active).toBe(false);
  wrapper.unmount();
});

it('keeps music and navigation in separate caches across sidebar switches', async () => {
  const musicCreated = vi.fn(), mapCreated = vi.fn();
  const Music = defineComponent({ name: 'QQMusicView', setup() {
    musicCreated(); return () => h('div', { 'data-test': 'music-view' }, 'Music');
  } });
  const Map = defineComponent({ name: 'AmapAppView', setup() {
    mapCreated(); return () => h('div', { 'data-test': 'map-view' }, 'Map');
  } });
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/apps', component: AppView, children: [
      { path: 'amap', name: 'amap-app', component: Map },
      { path: 'qqmusic', name: 'qqmusic', component: Music },
      { path: 'debug', component: { render: () => h('div', 'Debug') } },
      { path: 'home', component: { render: () => h('div') } },
    ] },
  ] });
  await router.push('/apps/amap'); await router.isReady();
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs: { 'el-icon': true } } });
  try {
    for (const intermediate of ['/apps/debug', '/apps/home']) {
      await router.push(intermediate); await flushPromises();
      await wrapper.find('button[aria-label="QQ 音乐"]').trigger('click'); await flushPromises();
      expect(router.currentRoute.value.path).toBe('/apps/qqmusic');
      expect(wrapper.find('[data-test=music-view]').exists()).toBe(true);
      expect(wrapper.find('[data-test=map-view]').exists()).toBe(false);
      await router.push('/apps/amap'); await flushPromises();
      expect(wrapper.find('[data-test=map-view]').exists()).toBe(true);
      expect(wrapper.find('[data-test=music-view]').exists()).toBe(false);
    }
    expect(mapCreated).toHaveBeenCalledTimes(1);
    expect(musicCreated).toHaveBeenCalledTimes(1);
  } finally { wrapper.unmount(); }
});
