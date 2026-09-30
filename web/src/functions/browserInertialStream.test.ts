import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createBrowserInertialStream } from './browserInertialStream';
import { initialMotionState } from './motionCapture';
beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('DeviceMotionEvent', class {});
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const ok = (data: unknown) => new Response(JSON.stringify({ status: 'ok', data }));
function sensor() {
  window.dispatchEvent(Object.assign(new Event('devicemotion'), {
    accelerationIncludingGravity: { x: .2, y: .3, z: 9.8 },
    rotationRate: { alpha: 0, beta: 0, gamma: 0 }, interval: 40,
  }));
}

it('streams actual motion events with fresh GPS and removes subscriptions on stop', async () => {
  let now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  let gps!: (fix: any) => void;
  const unsubscribe = vi.fn(), subscribe = vi.fn(receive => { gps = receive; return unsubscribe; });
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'live', format: 'browser', nextSequence: 0 }))
    .mockImplementation(async (_url, options) => options.method === 'DELETE' ? ok({ closed: true })
      : ok({ sequence: 0, result: { state: 2, accepted: 1, timestamp: 41, output: null } }));
  const output = vi.fn(), errors = vi.fn();
  const stream = createBrowserInertialStream(initialMotionState(), subscribe, output, errors, request);
  expect(await stream.start()).toBe(true);
  now = 20;
  gps({ longitude: 120, latitude: 30, accuracy: 1, altitude: 5, speed: 8,
    heading: 90, timestamp: 1700000000000, altitudeAccuracy: null, source: 'gps' });
  now = 40; sensor(); await vi.advanceTimersByTimeAsync(200);
  const sent = JSON.parse(request.mock.calls[1][1].body).samples[0];
  expect(sent.elapsed).toBe(40); expect(sent.gps.elapsed).toBe(20);
  expect(sent.angularVelocity).toEqual([0,0,0]);
  expect(output).toHaveBeenCalledOnce(); expect(errors).not.toHaveBeenCalled();
  stream.stop(); await vi.advanceTimersByTimeAsync(0);
  expect(unsubscribe).toHaveBeenCalledOnce();
  const calls = request.mock.calls.length;
  now = 80; sensor(); await vi.advanceTimersByTimeAsync(1000);
  expect(request).toHaveBeenCalledTimes(calls);
});

it('does not open a server session after cancelled permission', async () => {
  let resolve!: (permission: string) => void;
  vi.stubGlobal('DeviceMotionEvent', { requestPermission: () => new Promise<string>(r => { resolve = r; }) });
  const request = vi.fn(), subscribe = vi.fn();
  const stream = createBrowserInertialStream(initialMotionState(), subscribe, vi.fn(), vi.fn(), request);
  const pending = stream.start(); stream.stop(); resolve('granted');
  expect(await pending).toBe(false); expect(request).not.toHaveBeenCalled();
  expect(subscribe).not.toHaveBeenCalled();
});

it('closes and reports an unavailable sensor instead of keeping an idle session', async () => {
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'idle', format: 'browser', nextSequence: 0 }))
    .mockResolvedValue(ok({ closed: true }));
  const unsubscribe = vi.fn(), error = vi.fn();
  const stream = createBrowserInertialStream(initialMotionState(), () => unsubscribe, vi.fn(), error, request);
  await stream.start(); await vi.advanceTimersByTimeAsync(5500);
  expect(error).toHaveBeenCalledOnce(); expect(unsubscribe).toHaveBeenCalledOnce();
  expect(request.mock.calls[1][1].method).toBe('DELETE');
});
