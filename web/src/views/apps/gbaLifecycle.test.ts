// @vitest-environment node
import { expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { createGbaLifetime, destroyGba } from './gbaLifecycle';
it('blocks a ROM download completing after unmount or replacement', async () => {
 const life = createGbaLifetime();
 let finish!: () => void;
 const download = new Promise<void>(resolve => { finish = resolve; });
 const token = life.next(), run = vi.fn();
 const pending = download.then(() => { if (life.current(token)) run(); });
 life.dispose(); finish(); await pending;
 expect(run).not.toHaveBeenCalled();
 const next = createGbaLifetime(); const old = next.next(); next.next(); expect(next.current(old)).toBe(false);
});
it('releases audio, worker and keyboard even if pause fails', () => {
 const close = vi.fn().mockResolvedValue(undefined), disconnect = vi.fn(), unregisterHandlers = vi.fn(), terminate = vi.fn();
 const gba = { pause: () => { throw new Error('already stopped'); }, paused: false, keypad: { eatInput: true, currentDown: 0, unregisterHandlers }, audio: { jsAudio: { onaudioprocess: () => {}, disconnect }, context: { state: 'running', close } }, video: { renderPath: { worker: { terminate } } } };
 destroyGba(gba);
 expect(gba.paused).toBe(true); expect(gba.keypad.eatInput).toBe(false); expect(gba.audio.jsAudio.onaudioprocess).toBe(null);
 for (const call of [close, disconnect, unregisterHandlers, terminate]) expect(call).toHaveBeenCalledOnce();
});
it('removes the exact global handlers registered by the vendor keypad', () => {
 const addEventListener = vi.fn(), removeEventListener = vi.fn();
 const code = readFileSync(new URL('../../../public/vendor/gbajs2/js/keypad.js', import.meta.url), 'utf8');
 const keypad = runInNewContext(code + '; new GameBoyAdvanceKeypad()', { window: { addEventListener, removeEventListener } });
 keypad.registerHandlers(); expect(addEventListener).toHaveBeenCalledTimes(8);
 keypad.unregisterHandlers(); expect(removeEventListener.mock.calls).toEqual(addEventListener.mock.calls);
 keypad.unregisterHandlers(); expect(removeEventListener).toHaveBeenCalledTimes(8);
});
