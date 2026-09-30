// @vitest-environment node
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { expect, it, vi } from 'vitest';

it('ends finite input on the legacy needs-data result, but waits for incomplete input', () => {
  const self: any = { importScripts() {}, postMessage: vi.fn() };
  const context = vm.createContext({ self, Logger: class { logInfo() {} }, console,
    kDecodeFinishedEvt: 7, kSeekToRsp: 8, kFeedDataReq: 9,
    clearInterval: vi.fn(), Uint8Array });
  vm.runInContext(readFileSync(new URL('../../public/decoder.js', import.meta.url), 'utf8'), context);
  const decoder = self.decoder;
  context.Module = { _decodeOnePacket: () => 2, _seekTo: () => 0 };
  decoder.decode(); expect(self.postMessage).not.toHaveBeenCalled();
  decoder.inputEnded = true; decoder.decodeTimer = 123;
  decoder.decode(); expect(self.postMessage).toHaveBeenCalledWith({ t: 7 });
  expect(context.clearInterval).toHaveBeenCalledWith(123);
  decoder.inputEnded = false; self.postMessage.mockClear(); decoder.decode();
  expect(self.postMessage).not.toHaveBeenCalled();
});

it('releases buffering at EOF so the final frames can drain, and never restarts the finished decoder', () => {
  const context = vm.createContext({ Logger: class { logInfo() {} }, kProtoHttp: 0,
    Worker: class {}, URL, console });
  vm.runInContext(readFileSync(new URL('../../public/player.js', import.meta.url), 'utf8'), context);
  const player = vm.runInContext('new Player()', context);
  Object.assign(player, { buffering: true, pauseDecoding: vi.fn(), stopBuffering: vi.fn(), decodeWorker: { postMessage: vi.fn() } });
  player.onDecodeFinished({}); expect(player.stopBuffering).toHaveBeenCalledOnce();
  player.startDecoding(); expect(player.decodeWorker.postMessage).not.toHaveBeenCalled();
});

it('retains EOF when seeking cached bytes but waits when the decoder requests a new range', () => {
  const callbacks: Function[] = [];
  const self: any = { importScripts() {}, postMessage: vi.fn() };
  const context = vm.createContext({ self, Logger: class { logInfo() {} }, console,
    kRequestDataEvt: 10, Module: { addFunction: (fn: Function) => { callbacks.push(fn); return callbacks.length; } } });
  vm.runInContext(readFileSync(new URL('../../public/decoder.js', import.meta.url), 'utf8'), context);
  self.decoder.onWasmLoaded(); self.decoder.inputEnded = true;
  callbacks[3](-1, 1000); expect(self.decoder.inputEnded).toBe(true);
  callbacks[3](123, 0); expect(self.decoder.inputEnded).toBe(false);
});
