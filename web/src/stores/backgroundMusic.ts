import { reactive } from 'vue';

// Playback stays owned by the cached QQ Music view; the shell only exposes
// its current state and commands. Leaving /apps still tears playback down.
export const backgroundMusic = reactive({
  song: null as null | { title: string; singer: string; cover: string },
  playing: false, loading: false, elapsed: 0, duration: 0, error: '',
  previousDisabled: true, nextDisabled: true,
});
export const musicCommands: { toggle?: () => void; previous?: () => void; next?: () => void; open?: () => void } = {};
export function clearBackgroundMusic() {
  Object.assign(backgroundMusic, { song: null, playing: false, loading: false, elapsed: 0, duration: 0, error: '', previousDisabled: true, nextDisabled: true });
  for (const key of Object.keys(musicCommands) as (keyof typeof musicCommands)[]) delete musicCommands[key];
}
