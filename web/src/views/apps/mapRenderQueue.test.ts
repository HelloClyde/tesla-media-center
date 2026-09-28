import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createMapRenderQueue } from './mapRenderQueue';
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
it('yields between geometry batches and completes all work', () => {
  const queue = createMapRenderQueue(vi.fn());
  let completed = 0;
  function* work() { for (let i = 0; i < 100; i++) { completed++; yield; } }
  queue.start(work());
  expect(completed).toBe(0);
  vi.advanceTimersToNextTimer();
  expect(completed).toBeGreaterThan(0);
  expect(completed).toBeLessThan(100);
  vi.runAllTimers();
  expect(completed).toBe(100);
});
it('abandons an old viewport when interaction cancels or replaces it', () => {
  const queue = createMapRenderQueue(vi.fn());
  let old = 0, fresh = 0;
  function* oldWork() { for (let i = 0; i < 100; i++) { old++; yield; } }
  queue.start(oldWork()); vi.advanceTimersToNextTimer();
  queue.cancel(); const count = old;
  vi.runAllTimers(); expect(old).toBe(count);
  queue.start(oldWork());
  queue.start((function* () { fresh++; yield; })());
  vi.runAllTimers(); expect(old).toBe(count); expect(fresh).toBe(1);
});
it('yields on the time budget even before the batch limit', () => {
  let clock = 0, completed = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
  const queue = createMapRenderQueue(vi.fn());
  queue.start((function* () { for (let i = 0; i < 10; i++) { clock += 5; completed++; yield; } })());
  vi.advanceTimersToNextTimer(); expect(completed).toBe(1);
  queue.cancel();
});
it('reports rendering errors without leaving scheduled work behind', () => {
  const error = vi.fn(); const queue = createMapRenderQueue(error);
  queue.start((function* () { throw new Error('broken geometry'); yield; })());
  vi.runAllTimers(); expect(error).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0);
});
