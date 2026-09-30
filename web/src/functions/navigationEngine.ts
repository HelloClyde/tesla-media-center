import { computed, ref } from 'vue';

export type NavigationEngine = 'browser' | 'route-fusion';
const key = 'tmc:navigation-engine';
function readEngine(): NavigationEngine {
  try {
    const value = localStorage.getItem(key);
    if (value === 'amap-vdr') {
      try { localStorage.setItem(key, 'route-fusion'); } catch { /* Use migrated value for this session. */ }
      return 'route-fusion';
    }
    return value === 'route-fusion' ? value : 'browser';
  } catch { return 'browser'; }
}
export const navigationEngine = ref<NavigationEngine>(readEngine());
export function setNavigationEngine(value: NavigationEngine) {
  navigationEngine.value = value === 'route-fusion' ? value : 'browser';
  try { localStorage.setItem(key, navigationEngine.value); } catch { /* Session preference remains available. */ }
}
export const navigationEngineNotice = computed(() => navigationEngine.value === 'route-fusion'
  ? '路线融合：定位精度下降时沿路线推算，速度持续可信时支持长隧道，定位恢复后平滑校正。'
  : '当前使用浏览器定位。');
