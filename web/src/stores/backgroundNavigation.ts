import { reactive } from 'vue';
import { removeBackgroundApp, updateBackgroundApp } from './backgroundApps';
export const backgroundNavigation = reactive({ active: false, simulated: false, muted: false, arrow: '↑', instruction: '', road: '', remaining: '', remainingDuration: '', status: '' });
export const navigationCommands: { stop?: () => void; toggleVoice?: () => void } = {};
export function clearBackgroundNavigation() {
  backgroundNavigation.active = false;
  removeBackgroundApp('amap');
  delete navigationCommands.stop; delete navigationCommands.toggleVoice;
}
export function publishBackgroundNavigation(value: Omit<typeof backgroundNavigation, 'active'>, commands: typeof navigationCommands) {
  Object.assign(backgroundNavigation, value, { active: true });
  Object.assign(navigationCommands, commands);
  updateBackgroundApp({ id: 'amap', name: '高德导航', route: '/apps/amap', icon: '/icon/AMAP_LOGO.ico', running: true,
    detail: `${value.simulated ? '模拟导航 · ' : ''}${value.instruction} · 剩余 ${value.remaining} · ${value.remainingDuration}` });
}
