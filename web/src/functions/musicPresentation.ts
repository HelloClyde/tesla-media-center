import { watch } from 'vue';
import { backgroundMusic } from '@/stores/backgroundMusic';
import { captureLayout } from './viewportDiagnostics';

// The browser chrome should only be notified when track information changes.
// Pausing/buffering and progress ticks do not clear or rewrite the title.
export function installMusicTitle() {
  return watch(() => [backgroundMusic.song?.title, backgroundMusic.song?.singer], () => {
    const song = backgroundMusic.song;
    const title = song ? `${[song.title, song.singer].filter(Boolean).join(' - ')} · TMC` : 'TMC · 车载媒体中心';
    if (document.title !== title) {
      document.title = title;
      captureLayout('网页标题更新', true);
    }
  }, { immediate: true });
}

export function createMediaPresentation(session: MediaSession, makeMetadata: (data: MediaMetadataInit) => MediaMetadata) {
  let previous = '';
  return {
    track(song: { title: string; singer: string; album: string; cover: string } | undefined) {
      const key = song ? JSON.stringify([song.title, song.singer, song.album, song.cover]) : '';
      if (key === previous) return;
      session.metadata = song ? makeMetadata({ title: song.title, artist: song.singer, album: song.album, artwork: song.cover ? [{ src: song.cover }] : [] }) : null;
      previous = key;
      captureLayout('系统媒体信息更新', true);
    },
    state(playing: boolean, transitioning: boolean) {
      if (transitioning) return; // Keep the prior media state while replacing the source.
      const next = playing ? 'playing' : 'paused';
      if (session.playbackState !== next) {
        session.playbackState = next;
        captureLayout('系统播放状态：' + next, true);
      }
    },
  };
}
