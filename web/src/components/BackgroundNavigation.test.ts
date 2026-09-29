// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { nextTick } from 'vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import BackgroundNavigation from './BackgroundNavigation.vue';
import { backgroundNavigation as nav, clearBackgroundNavigation } from '@/stores/backgroundNavigation';
let view: VueWrapper;
beforeEach(() => { localStorage.clear(); Object.assign(nav, { active: true, instruction: '200 米后左转', remaining: '2 公里', road: '测试路' }); });
afterEach(() => { view?.unmount(); clearBackgroundNavigation(); vi.useRealTimers(); });
async function setup() {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/apps/qqmusic', '/apps/amap'].map(path => ({ path, component: { template: '<div />' } })) });
  await router.push('/apps/qqmusic'); await router.isReady();
  view = mount(BackgroundNavigation, { global: { plugins: [router] } });
  return router;
}
function pointer(target: EventTarget, type: string, x: number, y: number) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, { pointerId: 1, isPrimary: true, button: 0, clientX: x, clientY: y });
  target.dispatchEvent(event);
}
it('keeps a short tap as return-to-navigation', async () => {
  const router = await setup(); const button = view.get('.guidance');
  pointer(button.element, 'pointerdown', 100, 40); pointer(window, 'pointerup', 100, 40);
  await button.trigger('click'); await flushPromises();
  expect(router.currentRoute.value.path).toBe('/apps/amap');
});
it('moves only after a long press, persists placement and suppresses the release click', async () => {
  const router = await setup(); vi.useFakeTimers();
  const card = view.get('aside'), button = view.get('.guidance');
  pointer(button.element, 'pointerdown', 100, 40);
  vi.advanceTimersByTime(450); await nextTick();
  expect(card.classes()).toContain('dragging');
  pointer(window, 'pointermove', 160, 80); await nextTick();
  expect((card.element as HTMLElement).style.left).toBe('60px');
  pointer(window, 'pointerup', 160, 80); await button.trigger('click');
  expect(router.currentRoute.value.path).toBe('/apps/qqmusic');
  expect(JSON.parse(localStorage.getItem('tmc.navigation-float.v1')!)).toMatchObject({ x: 60, y: 40 });
  expect(card.classes()).not.toContain('dragging');
});
it('folds without stopping navigation and restores the saved preference', async () => {
  await setup();
  await view.get('[aria-label="折叠导航卡片"]').trigger('click'); await nextTick();
  expect(view.get('aside').classes()).toContain('collapsed');
  expect(view.text()).toContain('200 米后左转'); expect(view.find('.actions').exists()).toBe(false);
  expect(nav.active).toBe(true);
  view.unmount(); await setup();
  expect(view.get('aside').classes()).toContain('collapsed');
  await view.get('[aria-label="展开导航卡片"]').trigger('click');
  expect(view.find('.actions').exists()).toBe(true);
});
it('cancels a swipe before the hold threshold without navigation', async () => {
  const router = await setup(); vi.useFakeTimers(); const button = view.get('.guidance');
  pointer(button.element, 'pointerdown', 100, 40); pointer(window, 'pointermove', 140, 40);
  vi.advanceTimersByTime(450); await nextTick();
  expect(view.get('aside').classes()).not.toContain('dragging');
  await button.trigger('click'); expect(router.currentRoute.value.path).toBe('/apps/qqmusic');
});
