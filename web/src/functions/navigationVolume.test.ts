// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
afterEach(() => { localStorage.clear(); vi.resetModules(); });
it('defaults to boosted volume and persists mute and custom levels', async () => {
  let m = await import('./navigationVolume');
  expect(m.navigationVoiceVolume.value).toBe(150);
  m.setNavigationVoiceVolume(220);
  vi.resetModules(); m = await import('./navigationVolume');
  expect(m.navigationVoiceVolume.value).toBe(220);
  m.setNavigationVoiceVolume(0);
  vi.resetModules(); m = await import('./navigationVolume');
  expect(m.navigationVoiceVolume.value).toBe(0);
});
it('bounds gain and handles invalid saved values', async () => {
  localStorage.setItem('tmc:navigation-voice-volume', 'invalid');
  const m = await import('./navigationVolume');
  expect(m.navigationVoiceVolume.value).toBe(150);
  m.setNavigationVoiceVolume(999); expect(m.navigationVoiceVolume.value).toBe(300);
  m.setNavigationVoiceVolume(-20); expect(m.navigationVoiceVolume.value).toBe(0);
});
