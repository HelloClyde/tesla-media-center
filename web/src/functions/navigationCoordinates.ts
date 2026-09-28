import { ref } from 'vue';
import { wgs84togcj02 } from 'coordtransform';

export type NavigationCoordinateMode = 'direct' | 'wgs84';
const key = 'tmc:navigation-coordinate-mode';
function readMode(): NavigationCoordinateMode {
  try { return localStorage.getItem(key) === 'wgs84' ? 'wgs84' : 'direct'; }
  catch { return 'direct'; }
}
export const navigationCoordinateMode = ref<NavigationCoordinateMode>(readMode());
export function setNavigationCoordinateMode(value: NavigationCoordinateMode) {
  navigationCoordinateMode.value = value === 'wgs84' ? 'wgs84' : 'direct';
  try { localStorage.setItem(key, navigationCoordinateMode.value); } catch { /* Keep the session preference. */ }
}
/** Only browser positions enter here; search results and route points are already map coordinates. */
export function browserNavigationPoint(longitude: number, latitude: number): [number, number] {
  return navigationCoordinateMode.value === 'wgs84'
    ? wgs84togcj02(longitude, latitude)
    : [longitude, latitude];
}
