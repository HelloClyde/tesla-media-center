import { mount } from '@vue/test-utils';
import { expect, it } from 'vitest';
import AmapRoutePreviewBubbles from './AmapRoutePreviewBubbles.vue';
import type { AppRoute } from './amapNavigation';

const route: AppRoute = { id: 0, path: [], steps: [], breaks: [], labels: [], distance: 100,
  duration: 1200, tolls: 0, tollCurrency: 'CNY' };

it('shows each route cost, selects by bubble, and survives replacement by fewer routes', async () => {
  const wrapper = mount(AmapRoutePreviewBubbles, { props: {
    routes: [route, { ...route, id: 1, duration: 1860, tolls: 5 }], selected: 0,
    placements: [{ index: 0, x: 160, y: 130, anchor: { x: 160, y: 170 } },
      { index: 1, x: 350, y: 200, anchor: { x: 350, y: 240 } }],
  } });
  try {
    const buttons = wrapper.findAll('button');
    expect(buttons[0].text()).toContain('约 20 分钟');
    expect(buttons[0].text()).toContain('不收费');
    expect(buttons[1].text()).toContain('预计收费 ¥5');
    expect(buttons[0].attributes('aria-pressed')).toBe('true');
    await buttons[1].trigger('click');
    expect(wrapper.emitted('select')).toEqual([[1]]);
    await wrapper.setProps({ selected: 1 });
    expect(wrapper.findAll('button')[1].attributes('aria-pressed')).toBe('true');
    await wrapper.setProps({ routes: [route] });
    expect(wrapper.findAll('button')).toHaveLength(1);
  } finally { wrapper.unmount(); }
});
