import { afterEach, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import { backgroundMusic, clearBackgroundMusic } from '@/stores/backgroundMusic';
import { installMusicTitle, createMediaPresentation } from './musicPresentation';
afterEach(() => { clearBackgroundMusic(); vi.restoreAllMocks(); });
it('changes title once per track, without default-title flashes or progress rewrites', async () => {
  clearBackgroundMusic(); document.title = 'TMC · 车载媒体中心';
  const setTitle = vi.spyOn(document, 'title', 'set');
  const stop = installMusicTitle();
  try {
    backgroundMusic.song = { title: '第一首', singer: '歌手', cover: '' }; backgroundMusic.playing = true;
    await nextTick(); expect(setTitle).toHaveBeenCalledTimes(1);
    backgroundMusic.playing = false; backgroundMusic.loading = true; await nextTick();
    expect(document.title).toBe('第一首 - 歌手 · TMC');
    backgroundMusic.song = { title: '第二首', singer: '歌手', cover: '' }; await nextTick();
    for (let i = 0; i < 5; i++) { backgroundMusic.song = { ...backgroundMusic.song! }; backgroundMusic.elapsed = i; await nextTick(); }
    backgroundMusic.playing = true; backgroundMusic.loading = false; await nextTick();
    expect(setTitle).toHaveBeenCalledTimes(2);
    expect(document.title).toBe('第二首 - 歌手 · TMC');
    clearBackgroundMusic(); await nextTick(); expect(document.title).toBe('TMC · 车载媒体中心');
  } finally { stop(); }
});
it('deduplicates metadata and preserves playback state during automatic advancement', () => {
  const session = { metadata: null, playbackState: 'playing' } as unknown as MediaSession;
  const make = vi.fn(data => data as MediaMetadata);
  const presentation = createMediaPresentation(session, make);
  const song = { title: '曲目', singer: '歌手', album: '', cover: '' };
  presentation.track(song); presentation.track({ ...song });
  expect(make).toHaveBeenCalledTimes(1);
  presentation.state(false, true); expect(session.playbackState).toBe('playing');
  presentation.track({ ...song, title: '下一首' }); presentation.state(true, false);
  expect(make).toHaveBeenCalledTimes(2);
  presentation.state(false, false); expect(session.playbackState).toBe('paused');
  presentation.track(undefined); expect(session.metadata).toBeNull();
});
