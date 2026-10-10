import {afterEach, expect, it, vi} from 'vitest';
import {createMapInteraction, waitForMapIdle} from './amapMapWork';
afterEach(() => vi.useRealTimers());
it('waits for every interacting surface and a quiet interval without resetting on repeated idle notifications', async () => {
  vi.useFakeTimers();
  const first = createMapInteraction(), second = createMapInteraction(), resumed = vi.fn();
  first.set(true); second.set(true);
  void waitForMapIdle().then(resumed);
  first.set(false); await vi.advanceTimersByTimeAsync(200);
  expect(resumed).not.toHaveBeenCalled();
  second.set(false); await vi.advanceTimersByTimeAsync(100);
  second.set(false); // following pans must not keep the idle deadline alive
  await vi.advanceTimersByTimeAsync(40);
  expect(resumed).toHaveBeenCalledOnce();
  first.dispose(); second.dispose();
});
it('restarts the quiet interval if another gesture begins and releases on disposal', async () => {
  vi.useFakeTimers();
  const input = createMapInteraction(), resumed = vi.fn();
  input.set(true); void waitForMapIdle().then(resumed);
  input.set(false); await vi.advanceTimersByTimeAsync(100);
  input.set(true); await vi.advanceTimersByTimeAsync(100);
  expect(resumed).not.toHaveBeenCalled();
  input.dispose(); await vi.advanceTimersByTimeAsync(0);
  expect(resumed).toHaveBeenCalledOnce();
});
