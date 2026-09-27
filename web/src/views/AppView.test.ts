// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { defineComponent, h, onBeforeUnmount } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import AppView from './AppView.vue';
import { clearBackgroundMusic } from '@/stores/backgroundMusic';
afterEach(clearBackgroundMusic);

it('retains only the QQ player across app navigation and disposes it on logout', async () => {
  const created = vi.fn(), stopped = vi.fn(), otherStopped = vi.fn();
  const Music = defineComponent({ name: 'QQMusicView', setup() {
    created(); onBeforeUnmount(stopped);
    return () => h('audio', { 'data-test': 'persistent-audio' });
  } });
  const Other = defineComponent({ setup() { onBeforeUnmount(otherStopped); return () => h('div', 'Map'); } });
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/apps', component: AppView, children: [
      { path: 'qqmusic', component: Music }, { path: 'amap', component: Other }, { path: 'home', component: Other },
    ] }, { path: '/login', component: { render: () => h('div', 'Login') } },
  ] });
  await router.push('/apps/qqmusic'); await router.isReady();
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs: { 'el-icon': true } } });
  const audio = wrapper.get('audio').element;
  await router.push('/apps/amap'); await flushPromises();
  expect(stopped).not.toHaveBeenCalled();
  expect(wrapper.find('audio').exists()).toBe(false);
  await router.push('/apps/qqmusic'); await flushPromises();
  expect(wrapper.get('audio').element).toBe(audio);
  expect(created).toHaveBeenCalledTimes(1);
  expect(otherStopped).toHaveBeenCalledTimes(1);
  await router.push('/login'); await flushPromises();
  expect(stopped).toHaveBeenCalledTimes(1);
  wrapper.unmount();
});
