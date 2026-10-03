// @vitest-environment node
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';

it('resumes the audio clock after an in-flight buffer suspension completes', async () => {
  let finishSuspend: (() => void) | undefined;
  const audioContext = {
    state: 'running', currentTime: 0, destination: {},
    createGain: () => ({ gain: { value: 1 }, connect: vi.fn() }),
    suspend: vi.fn(() => new Promise<void>(resolve => {
      finishSuspend = () => { audioContext.state = 'suspended'; resolve(); };
    })),
    resume: vi.fn(async () => { audioContext.state = 'running'; }),
    close: vi.fn(async () => { audioContext.state = 'closed'; }),
  };
  const context = vm.createContext({
    window: { AudioContext: class { constructor() { return audioContext; } } },
    setInterval: vi.fn(() => 1), clearInterval: vi.fn(),
  });
  vm.runInContext(readFileSync(new URL('../../public/pcm-player.js', import.meta.url), 'utf8'), context);
  const player = vm.runInContext('new PCMPlayer({})', context);
  const paused = player.pause();
  const resumed = player.resume();
  await Promise.resolve();
  expect(audioContext.suspend).toHaveBeenCalledOnce();
  expect(audioContext.resume).not.toHaveBeenCalled();
  finishSuspend?.();
  await Promise.all([paused, resumed]);
  expect(audioContext.resume).toHaveBeenCalledOnce();
  expect(audioContext.state).toBe('running');
  player.destroy();
});
