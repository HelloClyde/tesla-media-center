import { ref } from 'vue';
const key = 'tmc:navigation-voice-volume';
export const DEFAULT_NAVIGATION_VOLUME = 150;
const clamp = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(300, Math.round(value))) : DEFAULT_NAVIGATION_VOLUME;
function read() {
  try { const value = localStorage.getItem(key); return value === null ? DEFAULT_NAVIGATION_VOLUME : clamp(Number(value)); }
  catch { return DEFAULT_NAVIGATION_VOLUME; }
}
export const navigationVoiceVolume = ref(read());
export function setNavigationVoiceVolume(value: number) {
  navigationVoiceVolume.value = clamp(value);
  try { localStorage.setItem(key, String(navigationVoiceVolume.value)); } catch { /* Keep session value. */ }
}
