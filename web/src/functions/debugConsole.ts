import { readonly, ref } from 'vue';
import VConsole from 'vconsole';

const storageKey = 'tmc:vconsole-enabled';
function savedPreference() {
  try { return localStorage.getItem(storageKey) === '1'; }
  catch { return false; }
}

const enabled = ref(savedPreference());
let instance: VConsole | undefined;
export const vConsoleEnabled = readonly(enabled);

export function setVConsoleEnabled(value: boolean) {
  if (value) {
    instance ??= new VConsole();
  } else {
    instance?.destroy();
    instance = undefined;
  }
  enabled.value = value;
  try { localStorage.setItem(storageKey, value ? '1' : '0'); }
  catch { /* Still allow switching when browser storage is unavailable. */ }
}

export function initDebugConsole() {
  if (enabled.value) setVConsoleEnabled(true);
}
