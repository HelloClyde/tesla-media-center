// @vitest-environment node
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';

function setup(timeout: typeof setTimeout = setTimeout, interval: typeof setInterval = setInterval) {
  const workerUrls: string[] = [];
  const context = vm.createContext({ URL,
    document: { currentScript: { src: 'https://example.test/player.js?v=build-hash' } },
    Logger: class { logInfo() {} }, kProtoHttp: 0, kProtoStream: 2, kDownloadFileReq: 9,
    kAudioFrame: 4, kVideoFrame: 5,
    Worker: class { constructor(url: string) { workerUrls.push(url); } },
    requestAnimationFrame: vi.fn(), setTimeout: timeout, clearTimeout, setInterval: interval, clearInterval, console,
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
it('also drains ordinary MP4 packets when the display refreshes slowly', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false;
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
it('does not discard future MP4 video frames while the audio clock is at zero', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false; p.pcmPlayer.getTimestamp = () => 0;
  p.frameBuffer = [{ t: 5, s: 0, d: [1] }, { t: 5, s: 0.2, d: [2] }];
  p.displayLoop();
  expect(p.frameBuffer.map((f: any) => f.s)).toEqual([0.2]);
  expect(Array.from(p.renderVideoFrame.mock.calls[0][0])).toEqual([1]);
});
it('bounds Douyin range prefetch when its playback clock is not advancing', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false; p.maxAheadSeconds = 12;
  p.decoderState = 2; p.duration = 379000; p.waitHeaderLength = 1700000;
  p.fileInfo = { offset: 5 * 1024 * 1024, size: 80 * 1024 * 1024, chunkSize: 1024 * 1024 };
  p.downloadWorker.postMessage = vi.fn(); p.downloading = false;
  p.downloadOneChunk();
  expect(p.downloadWorker.postMessage).not.toHaveBeenCalled();
  p.pcmPlayer.getTimestamp = () => 15;
  p.downloadOneChunk();
  expect(p.downloadWorker.postMessage).toHaveBeenCalledOnce();
});
it('continues a bounded range prefetch while buffering has paused the audio clock', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false; p.maxAheadSeconds = 12;
  p.decoderState = 2; p.duration = 379000; p.waitHeaderLength = 1700000;
  p.fileInfo = { offset: 5 * 1024 * 1024, size: 80 * 1024 * 1024, chunkSize: 1024 * 1024 };
  p.pcmPlayer.getTimestamp = () => 0;
  p.downloadWorker.postMessage = vi.fn(); p.downloading = false; p.buffering = true;
  p.downloadOneChunk();
  expect(p.downloadWorker.postMessage).toHaveBeenCalledOnce();
  p.downloading = false; p.fileInfo.offset = 25 * 1024 * 1024;
  p.downloadOneChunk();
  expect(p.downloadWorker.postMessage).toHaveBeenCalledOnce();
});
it('requests a new range as soon as the decoder runs out of input', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false; p.justSeeked = false;
  p.fileInfo = { offset: 2 * 1024 * 1024, size: 10 * 1024 * 1024, chunkSize: 1024 * 1024 };
  p.downloadOneChunk = vi.fn();
  p.onRequestData(-1, 0);
  expect(p.downloadOneChunk).toHaveBeenCalledOnce();
});
it('immediately replenishes ranges when the decoder is ready but playback is buffering', () => {
  const { player: p } = setup();
  p.buffering = true; p.downloadOneChunk = vi.fn();
  p.onFileDataUnderDecoderReady();
  expect(p.downloadOneChunk).toHaveBeenCalledOnce();
  p.buffering = false;
  p.onFileDataUnderDecoderReady();
  expect(p.downloadOneChunk).toHaveBeenCalledOnce();
});
it('prefetches the next range before buffering when a bounded lookahead is enabled', () => {
  const { player: p } = setup();
  p.buffering = false; p.maxAheadSeconds = 24; p.downloadOneChunk = vi.fn();
  p.onFileDataUnderDecoderReady();
  expect(p.downloadOneChunk).toHaveBeenCalledOnce();
});
it('checks a bounded lookahead frequently even when average bitrate sets a slow interval', () => {
  const schedule = vi.fn(() => 1) as unknown as typeof setInterval;
  const { player: p } = setup(setTimeout, schedule);
  p.maxAheadSeconds = 24; p.chunkInterval = 5500;
  p.startDownloadTimer();
  expect(schedule).toHaveBeenCalledWith(expect.any(Function), 500);
  p.stopDownloadTimer();
});
it('does not clear an active range request when an old seek response arrives', () => {
  const { player: p } = setup();
  p.downloadSeqNo = 2; p.downloading = true;
  p.onFileData(new ArrayBuffer(4), 0, 3, 1);
  expect(p.downloading).toBe(true);
});
it('keeps only one download timer for the active range sequence', () => {
  const { player: p } = setup();
  p.downloadOneChunk = vi.fn();
  p.startDownloadTimer();
  const seq = p.downloadSeqNo;
  const timer = p.downloadTimer;
  p.startDownloadTimer();
  expect(p.downloadSeqNo).toBe(seq);
  expect(p.downloadTimer).toBe(timer);
  p.stopDownloadTimer();
});
it('accepts an in-flight range when decoder initialization starts the timer', () => {
  const { player: p } = setup();
  p.downloadSeqNo = 3;
  p.downloading = true;
  p.startDownloadTimer();
  expect(p.downloadSeqNo).toBe(3);
  expect(p.downloading).toBe(true);
  p.stopDownloadTimer();
  expect(p.downloadSeqNo).toBe(4);
  expect(p.downloading).toBe(false);
});
it('pauses downloads until a blocked audio clock is resumed by a click', async () => {
  const { player: p } = setup();
  const state = vi.fn(); p.setAudioBlockedCallback(state);
  const audioCtx = { state: 'suspended', resume: vi.fn(async () => { audioCtx.state = 'running'; }) };
  p.onVideoParam = vi.fn(); p.onAudioParam = vi.fn(() => { p.pcmPlayer = { audioCtx }; });
  p.stopDownloadTimer = vi.fn(); p.startDownloadTimer = vi.fn(); p.startDecoding = vi.fn();
  p.onOpenDecoder({ e: 0, v: {}, a: {} });
  expect(p.audioBlocked).toBe(true);
  expect(p.stopDownloadTimer).toHaveBeenCalledOnce();
  expect(p.startDecoding).not.toHaveBeenCalled();
  expect(await p.resumeBlockedAudio()).toBe(true);
  expect(p.startDecoding).toHaveBeenCalledOnce();
  expect(p.startDownloadTimer).toHaveBeenCalledOnce();
  expect(state.mock.calls.map(([blocked]) => blocked)).toEqual([true, false]);
});
it('keeps decoding incoming ranges while buffering and stops downloads on manual pause', () => {
  const { player: p } = setup();
  p.browserSource = null; p.isStream = false; p.pcmPlayer.pause = vi.fn(); p.pcmPlayer.resume = vi.fn();
  p.startBuffering = Object.getPrototypeOf(p).startBuffering;
  p.showLoading = vi.fn(); p.hideLoading = vi.fn(); p.stopTrackTimer = vi.fn(); p.startTrackTimer = vi.fn();
  p.pauseDecoding = vi.fn(); p.stopDownloadTimer = vi.fn(); p.startDownloadTimer = vi.fn();
  p.fileInfo = { size: 100, offset: 0, chunkSize: 10 }; p.decoderState = 2;
  p.startBuffering();
  expect(p.playerState).toBe(1);
  expect(p.pauseDecoding).not.toHaveBeenCalled();
  expect(p.stopDownloadTimer).not.toHaveBeenCalled();
  p.stopBuffering();
  expect(p.pcmPlayer.resume).toHaveBeenCalledOnce();
  expect(p.startTrackTimer).toHaveBeenCalledOnce();
  p.pause();
  expect(p.stopDownloadTimer).toHaveBeenCalledOnce();
  p.resume();
  expect(p.startDownloadTimer).toHaveBeenCalledOnce();
});
it('reports a sustained buffer stall instead of leaving the loading indicator forever', () => {
  let watchdog: (() => void) | undefined;
  const timeout = ((callback: () => void, delay: number) => {
    expect(delay).toBe(30000);
    watchdog = callback;
    return 1;
  }) as typeof setTimeout;
  const { player: p } = setup(timeout);
  p.browserSource = null; p.isStream = false;
  p.startBuffering = Object.getPrototypeOf(p).startBuffering;
  p.pcmPlayer.pause = vi.fn(); p.showLoading = vi.fn(); p.stopTrackTimer = vi.fn();
  p.reportPlayError = vi.fn();
  p.startBuffering();
  expect(watchdog).toBeTypeOf('function');
  expect(p.buffering).toBe(true);
  expect(p.playerState).toBe(1);
  watchdog?.();
  expect(p.reportPlayError).toHaveBeenCalledWith(-1, 0, '视频缓冲超时，请重试');
  p.pcmPlayer.resume = vi.fn(); p.hideLoading = vi.fn(); p.startTrackTimer = vi.fn();
  p.stopBuffering();
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
