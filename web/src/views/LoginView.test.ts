// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import LoginView from './LoginView.vue';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), replace: vi.fn() }));
vi.mock('axios', () => ({ default: { get: mocks.get, post: mocks.post, isAxiosError: (error: any) => error.isAxiosError } }));
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: mocks.replace }) }));
let view: VueWrapper;
beforeEach(() => { vi.clearAllMocks(); mocks.get.mockResolvedValue({ data: { status: 'need_login' } }); });
afterEach(() => view?.unmount());
it.each([[401, '服务器未接受登录（401）'], [502, 'HTTP 502'], [undefined, '暂时无法连接服务']])('distinguishes login HTTP %s from a network failure', async (status, message) => {
  mocks.post.mockRejectedValue({ isAxiosError: true, response: status ? { status } : undefined });
  view = mount(LoginView); await flushPromises();
  await view.get('input').setValue('test-password'); await view.get('form').trigger('submit'); await flushPromises();
  expect(view.get('[role="status"]').text()).toContain(message);
  expect(mocks.replace).not.toHaveBeenCalled();
});
it('reuses a valid existing session after a refresh', async () => {
  mocks.get.mockResolvedValue({ data: { status: 'ok' } });
  view = mount(LoginView); await flushPromises();
  expect(mocks.replace).toHaveBeenCalledWith('/apps/home');
  expect(mocks.post).not.toHaveBeenCalled();
});
