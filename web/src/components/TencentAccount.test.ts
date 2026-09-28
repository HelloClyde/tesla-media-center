// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import TencentAccount from './TencentAccount.vue';
const response = (data: unknown) => ({ ok: true, json: async () => ({ status: 'ok', data }) });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
it('uses one app QR flow for both account types and stops polling on close', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockImplementation(async (url: string) => response(url.endsWith('/qrcode') ? { qrcode: 'data:image/png;base64,AA==' } : { loggedIn: false }));
  vi.stubGlobal('fetch', fetch);
  const view = mount(TencentAccount); await flushPromises();
  await view.get('.account-trigger').trigger('click'); await flushPromises();
  expect(view.text()).toContain('支持微信、QQ 账号');
  expect(view.get('img').attributes('src')).toContain('data:image/png');
  const signal = fetch.mock.calls[1][1].signal;
  await view.get('[aria-label="关闭登录"]').trigger('click');
  await vi.advanceTimersByTimeAsync(10000);
  expect(signal.aborted).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(2);
  view.unmount();
});
it('shows the nickname after confirmed authorization and supports disconnect', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockImplementation(async (url: string) => response(url.endsWith('/poll') ? { state: 'confirmed', nickname: '测试账号' } : url.endsWith('/qrcode') ? { qrcode: 'data:image/png;base64,AA==' } : { loggedIn: false }));
  vi.stubGlobal('fetch', fetch);
  const view = mount(TencentAccount); await flushPromises();
  await view.get('.account-trigger').trigger('click'); await flushPromises();
  await vi.advanceTimersByTimeAsync(2500); await flushPromises();
  expect(view.get('.account-trigger').text()).toBe('测试账号');
  expect(view.find('[role="dialog"]').exists()).toBe(false);
  await view.get('.account-trigger').trigger('click');
  await view.findAll('button').find(b => b.text() === '退出当前连接')!.trigger('click'); await flushPromises();
  expect(fetch.mock.calls[fetch.mock.calls.length - 1][1].method).toBe('DELETE');
  expect(view.get('.account-trigger').text()).toBe('登录账号');
  view.unmount();
});
