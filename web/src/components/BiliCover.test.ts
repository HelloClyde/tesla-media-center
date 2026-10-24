import { expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import BiliCover from './BiliCover.vue';

it('displays untrusted titles as text while removing search highlight tags', () => {
  const container = { template: '<div><slot name="header"/><slot/></div>' };
  const title = '<em class="keyword">title</em><img src=x onerror="alert(1)"><script>alert(2)</script>';
  const wrapper = mount(BiliCover, {
    props: { video: { title }, onClick: () => {} },
    global: { stubs: { ElCard: container, ElText: container, ElRow: container, ElCol: container, ElIcon: container, User: true } },
  });
  expect(wrapper.find('.video-title').text()).toBe('title<img src=x onerror="alert(1)"><script>alert(2)</script>');
  expect(wrapper.find('.video-title img').exists()).toBe(false);
  expect(wrapper.find('script').exists()).toBe(false);
  wrapper.unmount();
});
