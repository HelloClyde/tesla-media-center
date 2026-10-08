// @vitest-environment node
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it, vi } from 'vitest';

function setup() {
  const workers: any[] = [];
  const context = vm.createContext({
    Logger: class { logInfo() {} }, kProtoHttp: 0,
    Worker: class { terminate = vi.fn(); constructor() { workers.push(this); } },
    clearInterval: vi.fn(), clearTimeout: vi.fn(), cancelAnimationFrame: vi.fn(),
  });
  vm.runInContext(readFileSync(new URL('../../public/player.js', import.meta.url), 'utf8'), context);
  return { player: vm.runInContext('new Player()', context), workers, context };
}

it('destroys idle resources without recreating workers and ignores queued worker events', () => {
  const { player, workers, context } = setup();
  const pcm = { destroy: vi.fn() }, controller = { abort: vi.fn() }, source = { cancel: vi.fn() };
  player.pcmPlayer = pcm; player.fetchController = controller; player.browserSource = source;
  player.frameBuffer = [{}]; player.displayAnimationFrame = 42; player.liveAudioTimer = 77;
  player.finishCallback = vi.fn(); player.timeCallback = vi.fn();
  const lateMessage = workers[1].onmessage;
  player.destroy(); player.destroy();
  expect(workers).toHaveLength(2);
  workers.forEach(worker => expect(worker.terminate).toHaveBeenCalledTimes(1));
  expect(pcm.destroy).toHaveBeenCalledOnce();
  expect(controller.abort).toHaveBeenCalledOnce();
  expect(source.cancel).toHaveBeenCalledOnce();
  expect(context.cancelAnimationFrame).toHaveBeenCalledWith(42);
  expect(context.clearInterval).toHaveBeenCalledWith(77);
  expect(player.frameBuffer).toEqual([]);
  expect(player.finishCallback).toBeNull();
  expect(player.timeCallback).toBeNull();
  expect(() => lateMessage({ data: { t: 'late' } })).not.toThrow();
  expect(player.play('test', {})).toMatchObject({ e: -1 });
});

it('stop remains reusable but old worker callbacks cannot affect the next session', () => {
  const { player, workers } = setup();
  const oldMessage = workers[1].onmessage;
  player.stop();
  expect(workers).toHaveLength(4);
  expect(player.destroyed).toBe(false);
  expect(() => oldMessage({ data: { t: 'late' } })).not.toThrow();
  player.destroy();
});
