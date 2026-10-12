import { mount } from '@vue/test-utils';
import { expect, it } from 'vitest';
import AmapCongestionNotice from './AmapCongestionNotice.vue';

it('distinguishes upcoming pass time from the remaining time in a jam', async () => {
  const notice = { status: 3 as const, active: false, distance: 300, length: 1200, duration: 240 };
  const wrapper = mount(AmapCongestionNotice, { props: { notice } });
  try {
    expect(wrapper.text()).toContain('前方拥堵');
    expect(wrapper.text()).toContain('300 米后');
    expect(wrapper.text()).toContain('预计通过 4 分钟');
    await wrapper.setProps({ notice: { ...notice, active: true, distance: 0, length: 900, duration: 45 } });
    expect(wrapper.text()).toContain('正在拥堵');
    expect(wrapper.text()).toContain('预计还需 不足 1 分钟');
    expect(wrapper.text()).toContain('剩余 900 米');
    expect(wrapper.text()).not.toContain('300 米后');
    await wrapper.setProps({ notice: { ...notice, duration: null } });
    expect(wrapper.text()).toContain('通过时间待更新');
    expect(wrapper.text()).not.toContain('4 分钟');
  } finally { wrapper.unmount(); }
});
