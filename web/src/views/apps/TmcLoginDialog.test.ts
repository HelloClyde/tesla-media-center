import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import TmcLoginDialog from './TmcLoginDialog.vue';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post, isAxiosError: () => false } }));
afterEach(() => { post.mockReset(); document.body.innerHTML = ''; });

it('restores the TMC session without navigating away so the map can resume', async () => {
  post.mockResolvedValue({data:{status:'ok'}});
  const dialog = mount(TmcLoginDialog, {props:{open:true},attachTo:document.body});
  expect(document.querySelector('#tmc-login-title')?.textContent).toContain('登录 TMC');
  expect(document.querySelector('.tmc-login-dialog')?.textContent).toContain('不是高德账号');
  const password = document.querySelector<HTMLInputElement>('#tmc-login-password')!;
  password.value = 'test-password'; password.dispatchEvent(new Event('input', {bubbles:true}));
  document.querySelector<HTMLFormElement>('.tmc-login-dialog form')!.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));
  await flushPromises();
  expect(post).toHaveBeenCalledWith('/api/login',{password:'test-password'},{timeout:15000});
  expect(dialog.emitted('loggedIn')).toHaveLength(1);
  dialog.unmount();
});
