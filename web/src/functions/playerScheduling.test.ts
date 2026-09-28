// @vitest-environment node
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';

function setup() {
  const workerUrls: string[] = [];
  const context = vm.createContext({ URL,
    document: { currentScript: { src: 'https://example.test/player.js?v=build-hash' } },
    Logger: class { logInfo() {} }, kProtoHttp: 0, kAudioFrame: 4, kVideoFrame: 5,
    Worker: class { constructor(url: string) { workerUrls.push(url); } },
    requestAnimationFrame: vi.fn(), console,
  });
  vm.runInContext(readFileSync(new URL('../../public/player.js', import.meta.url), 'utf8'), context);
  const player = vm.runInContext('new Player()', context);
  Object.assign(player, { browserSource: {}, playerState: 1, isStream: true,
    decoding: true, buffering: false, firstAudioFrame: false, firstVideoFrame: false,
    beginTimeOffset: 0, pcmPlayer: { getTimestamp: () => 0.2, play: vi.fn() },
    renderVideoFrame: vi.fn(), startBuffering: vi.fn(), startDecoding: vi.fn() });
  return { player, workerUrls };
}
it('drains due AAC and video packets at low refresh rates but renders only the latest video', () => {
  const { player: p } = setup();
  p.frameBuffer = [
    { t: 4, s: 0, d: [1] }, { t: 5, s: 0, d: [2] },
    { t: 4, s: 0.023, d: [3] }, { t: 5, s: 0.033, d: [4] },
    { t: 4, s: 0.046, d: [5] }, { t: 5, s: 0.066, d: [6] },
    { t: 5, s: 0.233, d: [7] },
  ];
  p.displayLoop();
  expect(p.pcmPlayer.play).toHaveBeenCalledTimes(3);
  expect(p.renderVideoFrame).toHaveBeenCalledOnce();
  expect(Array.from(p.renderVideoFrame.mock.calls[0][0])).toEqual([6]);
  expect(p.frameBuffer.map((f: any) => f.s)).toEqual([0.233]);
});
it('anchors the first audio timestamp to its actual scheduled start', () => {
  const { player: p } = setup();
  p.firstAudioFrame = true; p.pcmPlayer.startTime = 0.15;
  p.displayAudioFrame({ s: 0, d: [1] });
  expect(p.beginTimeOffset).toBe(-0.2);
});
it('loads workers from the same build as the player entry', () => {
  expect(setup().workerUrls).toEqual(['/downloader.js?v=build-hash', '/decoder.js?v=build-hash']);
});

it('filters repeated probe audio and video packets before posting any playable frame', () => {
  const functions: Function[] = [];
  const self = { importScripts: vi.fn(), postMessage: vi.fn() };
  const context = vm.createContext({ self, console, Logger: class { logInfo() {} },
    kVideoFrame: 5, kAudioFrame: 4,
    Module: { HEAPU8: new Uint8Array(10), addFunction: (fn: Function) => { functions.push(fn); return functions.length; } },
  });
  vm.runInContext(readFileSync(new URL('../../public/decoder.js', import.meta.url), 'utf8'), context);
  vm.runInContext('self.decoder.onWasmLoaded(); self.decoder.probeTime = 6.3;', context);
  for (const callback of functions.slice(0, 2)) {
    for (const time of [0, 2.1, 4.2, 6.299]) callback(0, 1, time);
  }
  expect(self.postMessage).not.toHaveBeenCalled();
  functions[0](0, 1, 6.3); functions[1](0, 1, 6.32);
  expect(self.postMessage.mock.calls.map(([frame]) => frame.s)).toEqual([0, expect.closeTo(0.02)]);
});
