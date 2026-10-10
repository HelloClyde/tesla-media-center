import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {expect, it} from 'vitest';
import {mount} from '@vue/test-utils';
import NavigationTurnIcon from './NavigationTurnIcon.vue';
import {navigationArrowAsset} from './navigationArrow';
import assets from './navigationArrowAssets.json';

it('uses distinct APK arrows for slight turns, forks and normal turns', () => {
  expect(navigationArrowAsset('bear-left')).toBe('/amap/navigation-arrows/action-4.webp');
  expect(navigationArrowAsset('bear-right')).toBe('/amap/navigation-arrows/action-5.webp');
  expect(navigationArrowAsset('fork-left')).toBe('/amap/navigation-arrows/action-65.webp');
  expect(navigationArrowAsset('fork-right')).toBe('/amap/navigation-arrows/action-66.webp');
  expect(navigationArrowAsset('↰')).toBe('/amap/navigation-arrows/action-2.webp');
  expect(navigationArrowAsset('↱')).toBe('/amap/navigation-arrows/action-3.webp');
  expect(navigationArrowAsset('sharp-left')).toBe('/amap/navigation-arrows/action-6.webp');
  expect(navigationArrowAsset('sharp-right')).toBe('/amap/navigation-arrows/action-7.webp');
  expect(navigationArrowAsset('uturn-left')).toBe('/amap/navigation-arrows/action-8.webp');
  expect(navigationArrowAsset('uturn-right')).toBe('/amap/navigation-arrows/action-19.webp');
  expect(navigationArrowAsset('straight')).toBe('/amap/navigation-arrows/action-9.webp');
  expect(navigationArrowAsset('destination')).toBe('/amap/navigation-arrows/action-15.webp');
  expect(navigationArrowAsset('unrecognized')).toBe('/amap/navigation-arrows/action-0.webp');
});
it('switches from the original entry-ring icon to the original exit-ring icon', async () => {
  const icon = mount(NavigationTurnIcon, {props: {arrow: 'roundabout-enter'}});
  try {
    expect(icon.get('image').attributes('href')).toBe('/amap/navigation-arrows/action-11.webp');
    await icon.setProps({arrow: 'roundabout-exit'});
    expect(icon.get('image').attributes('href')).toBe('/amap/navigation-arrows/action-12.webp');
  } finally {icon.unmount();}
});
it('keeps separate mask IDs when the main guide and background cards coexist', () => {
  const view = mount({components: {NavigationTurnIcon}, template: '<div><NavigationTurnIcon arrow="bear-left"/><NavigationTurnIcon arrow="fork-right"/></div>'});
  try {
    const ids = view.findAll('mask').map(mask => mask.attributes('id'));
    expect(new Set(ids).size).toBe(2);
    expect(view.findAll('rect').map(rect => rect.attributes('mask'))).toEqual(ids.map(id => `url(#${id})`));
    expect(view.findAll('rect').every(rect => rect.attributes('fill') === 'currentColor')).toBe(true);
  } finally {view.unmount();}
});
it('ships the original WebP bytes named by the extracted APK resource table', () => {
  const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../public');
  const source = JSON.parse(readFileSync(resolve(publicDir, 'amap/navigation-arrows/source.json'), 'utf8'));
  for (const item of source) {
    const path = (assets as Record<string, string>)[item.icon];
    const bytes = readFileSync(resolve(publicDir, path.slice(1)));
    expect(bytes.subarray(0, 4).toString()).toBe('RIFF');
    expect(bytes.subarray(8, 12).toString()).toBe('WEBP');
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(item.sha256);
  }
});
