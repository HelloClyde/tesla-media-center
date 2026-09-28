import { afterEach, describe, expect, it, vi } from 'vitest';
import { captureLayout, clearLayoutSamples, layoutSamples, setLayoutRecording, startLayoutDiagnostics } from './viewportDiagnostics';
afterEach(() => { setLayoutRecording(false); document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('viewport diagnostics', () => {
  it('distinguishes viewport resize from player layout shifts and caps history', () => {
    document.body.innerHTML = '<section class="listening"><footer></footer></section>';
    let height = 600;
    vi.spyOn(document.querySelector('.listening')!, 'getBoundingClientRect').mockImplementation(() => ({ top: 0, height }) as DOMRect);
    setLayoutRecording(true);
    height = 550; captureLayout();
    expect(layoutSamples.value[0].change).toBe('播放器布局变化');
    vi.stubGlobal('innerHeight', innerHeight - 25); captureLayout('resize');
    expect(layoutSamples.value[0].change).toBe('布局视口 resize');
    for (let i = 0; i < 100; i++) captureLayout('切歌后', true);
    expect(layoutSamples.value).toHaveLength(80);
    clearLayoutSamples(); expect(layoutSamples.value).toHaveLength(1);
  });
  it('does not record when disabled and removes listeners/timer on disposal', () => {
    vi.useFakeTimers();
    const clear = vi.spyOn(globalThis, 'clearInterval');
    const stop = startLayoutDiagnostics(); setLayoutRecording(true);
    setLayoutRecording(false); const count = layoutSamples.value.length;
    captureLayout('切歌', true); expect(layoutSamples.value).toHaveLength(count);
    stop(); expect(clear).toHaveBeenCalled(); vi.useRealTimers();
  });
});


it('records non-bubbling player events beside viewport changes and removes listeners', () => {
  document.body.innerHTML = '<audio data-qqmusic-player src="https://example.invalid/private-token"></audio><audio id="other"></audio>';
  const stop = startLayoutDiagnostics();
  setLayoutRecording(true);
  const audio = document.querySelector('audio')!;
  audio.dispatchEvent(new Event('emptied'));
  expect(layoutSamples.value[0].reason).toBe('audio：emptied');
  expect(layoutSamples.value[0].media).toContain('src=有');
  expect(JSON.stringify(layoutSamples.value)).not.toContain('private-token');
  vi.stubGlobal('innerHeight', innerHeight - 30);
  window.dispatchEvent(new Event('resize'));
  expect(layoutSamples.value[0].change).toContain('布局视口 resize');
  const count = layoutSamples.value.length;
  document.querySelector('#other')!.dispatchEvent(new Event('pause'));
  expect(layoutSamples.value).toHaveLength(count);
  stop();
  audio.dispatchEvent(new Event('playing'));
  expect(layoutSamples.value).toHaveLength(count);
});
